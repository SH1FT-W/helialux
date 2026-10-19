"""Abfrage der Lampe und Halten des gewünschten Zustands.

Die Lampe vergisst die manuelle Farbe bei jedem Stromausfall/Neustart und wenn die Laufzeit der
manuellen Farbsimulation abläuft – dann übernimmt wieder ihr eigenes Profil. Der Koordinator merkt
sich deshalb, was Home Assistant zuletzt eingestellt hat (`desired`), und stellt es wieder her.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util, slugify

from .api import (
    HeliaLuxClient,
    HeliaLuxDevice,
    HeliaLuxError,
    HeliaLuxProfile,
    HeliaLuxProfiles,
    HeliaLuxReply,
    HeliaLuxStatus,
)
from .const import (
    CLOCK_DRIFT_ISSUE_MIN,
    CONF_SCAN_INTERVAL,
    CONF_TANK_NAME,
    CONF_WEATHER,
    DEFAULT_COLOR_DURATION_H,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FAILURES_BEFORE_UNAVAILABLE,
    MAX_PROFILE_POINTS,
    PROFILE_REFRESH,
    RENEW_BELOW_MIN,
    STORAGE_VERSION,
    WEATHER_MIN_GAP,
)
from .weather import clouds_for

_LOGGER = logging.getLogger(__name__)

MODE_MANUAL = "manual"  # HA bestimmt die Kanäle (manuelle Farbsimulation)
MODE_AUTO = "auto"  # Profil oder Tagsimulation der Lampe
# Nach einem eigenen Befehl so lange keine abweichenden Werte der Lampe als „von außen geändert“ werten.
ADOPT_GRACE = timedelta(seconds=45)
# Höchstens so oft wiederherstellen – falls die Lampe den Befehl annimmt, aber nicht umsetzt.
RESTORE_BACKOFF = timedelta(minutes=2)
FADE_MIN_GAP = 2.0


@dataclass(slots=True)
class HeliaLuxData:
    status: HeliaLuxStatus
    profiles: HeliaLuxProfiles | None
    clock_offset_min: int | None
    color_remaining_min: int | None
    profile: HeliaLuxProfile | None = None  # das heute aktive Profil komplett (Kurve, Wolken)


@dataclass(slots=True)
class Desired:
    mode: str = MODE_AUTO
    levels: tuple[int, ...] | None = None
    last_on: tuple[int, ...] | None = None
    expires: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "levels": list(self.levels) if self.levels is not None else None,
            "last_on": list(self.last_on) if self.last_on is not None else None,
            "expires": self.expires.isoformat() if self.expires else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Desired:
        def tup(v: Any) -> tuple[int, ...] | None:
            return tuple(int(x) for x in v) if isinstance(v, list) else None

        return cls(
            mode=MODE_MANUAL if data.get("mode") == MODE_MANUAL else MODE_AUTO,
            levels=tup(data.get("levels")),
            last_on=tup(data.get("last_on")),
            expires=dt_util.parse_datetime(data["expires"]) if data.get("expires") else None,
        )


@dataclass(slots=True)
class ProgramSettings:
    """Was HA zusätzlich mit dem Profil der Lampe macht: Wolken-Fenster, Sonnenverlauf, Eingewöhnung."""

    cloud_from: int = 0
    cloud_to: int = 1439
    sun_on: bool = False
    sun_earliest: int = 8 * 60
    sun_latest: int = 22 * 60
    acclim_on: bool = False
    acclim_start: int = 50
    acclim_weeks: int = 4
    acclim_since: str | None = None
    template: dict[str, Any] | None = None  # Original-Profil, aus dem Sonne/Eingewöhnung täglich rechnen
    weather_on: bool = False  # Wolken nach echtem Wetter

    def as_dict(self) -> dict[str, Any]:
        return {s: getattr(self, s) for s in self.__slots__}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgramSettings:
        return cls(**{k: v for k, v in data.items() if k in cls.__slots__})


def _profile_to_dict(p: HeliaLuxProfile) -> dict[str, Any]:
    return {
        "index": p.index,
        "name": p.name,
        "times": list(p.times),
        "channels": [list(c) for c in p.channels],
        "ci": list(p.cloud_intensity),
        "cm": list(p.cloud_motion),
    }


def _profile_from_dict(d: dict[str, Any]) -> HeliaLuxProfile:
    return HeliaLuxProfile(
        int(d["index"]),
        str(d["name"]),
        tuple(d["times"]),
        tuple(tuple(c) for c in d["channels"]),
        tuple(d["ci"]),
        tuple(d["cm"]),
    )


@dataclass(slots=True)
class Stats:
    restores: int = 0
    failures_in_row: int = 0
    last_error: str | None = None
    last_success: datetime | None = None
    log: list[str] = field(default_factory=list)


class HeliaLuxCoordinator(DataUpdateCoordinator[HeliaLuxData]):
    """Fragt die Lampe ab und führt alle Schaltbefehle aus."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: HeliaLuxClient) -> None:
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )
        self.client = client
        self.tank_name: str = entry.data.get(CONF_TANK_NAME) or entry.title
        self.slug = slugify(self.tank_name)
        self.device: HeliaLuxDevice | None = None
        self.desired = Desired()
        self.color_duration_h = DEFAULT_COLOR_DURATION_H
        self.daytime_position_h = 12.0
        self.daytime_duration_h = 1.0
        self.keep_manual = True
        self.program = ProgramSettings()
        self.stats = Stats()
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._profiles_at: datetime | None = None
        self._last_command: datetime | None = None
        self._fade: asyncio.Task[None] | None = None
        self._maintaining = False
        self._last_restore: datetime | None = None
        self._adopt_on_first_status = False
        self._weather_written: datetime | None = None

    # --- Start ---------------------------------------------------------------------------------------

    async def _async_setup(self) -> None:
        stored = await self._store.async_load()
        # Erster Start (auch nach dem Umstieg von der alten Integration): Zustand der Lampe übernehmen.
        self._adopt_on_first_status = stored is None
        if stored is None:
            stored = await self._import_old_numbers()
        self.desired = Desired.from_dict(stored.get("desired") or {})
        self.color_duration_h = float(stored.get("color_duration_h", DEFAULT_COLOR_DURATION_H))
        self.daytime_position_h = float(stored.get("daytime_position_h", 12.0))
        self.daytime_duration_h = float(stored.get("daytime_duration_h", 1.0))
        self.keep_manual = bool(stored.get("keep_manual", True))
        self.program = ProgramSettings.from_dict(stored.get("program") or {})
        self.config_entry.async_on_unload(async_track_time_change(self.hass, self._nightly, hour=3, minute=5, second=0))
        if weather := self.config_entry.options.get(CONF_WEATHER):
            # Rückrufe müssen @callback sein – sonst führt HA sie in einem Hilfs-Thread aus
            self.config_entry.async_on_unload(async_track_state_change_event(self.hass, weather, self._weather_event))
            self.config_entry.async_on_unload(
                async_track_time_interval(self.hass, self._weather_event, WEATHER_MIN_GAP)
            )
        try:
            self.device = await self.client.device()
        except HeliaLuxError as err:
            _LOGGER.debug("Gerätedaten nicht lesbar: %s", err)

    async def _import_old_numbers(self) -> dict[str, Any]:
        """Einmalig die Regler-Werte der alten Integration übernehmen (je Regler eine eigene Datei)."""
        out: dict[str, Any] = {}
        entry_id = self.config_entry.entry_id
        for key, attr in (
            ("color_duration_h", "manual_color_simulation_duration"),
            ("daytime_duration_h", "manual_daytime_simulation_duration"),
            ("daytime_position_h", "daytime_simulation_position"),
        ):
            old: Store[dict[str, Any]] = Store(self.hass, 1, f"{DOMAIN}_{entry_id}_{attr}.json")
            data = await old.async_load()
            if data and isinstance(data.get("value"), int | float):
                out[key] = float(data["value"])
        return out

    def _save(self) -> None:
        self._store.async_delay_save(self._snapshot, 2)

    def _snapshot(self) -> dict[str, Any]:
        return {
            "desired": self.desired.as_dict(),
            "color_duration_h": self.color_duration_h,
            "daytime_position_h": self.daytime_position_h,
            "daytime_duration_h": self.daytime_duration_h,
            "keep_manual": self.keep_manual,
            "program": self.program.as_dict(),
        }

    # --- Abfrage -------------------------------------------------------------------------------------

    async def _async_update_data(self) -> HeliaLuxData:
        try:
            status = await self.client.status()
            profiles = self.data.profiles if self.data else None
            profile = self.data.profile if self.data else None
            now = dt_util.utcnow()
            stale = profiles is None or self._profiles_at is None or now - self._profiles_at > PROFILE_REFRESH
            if stale:
                profiles = await self.client.profiles()
                self._profiles_at = now
            if stale or profile is None or profile.index != status.profile_index:
                profile = await self._read_profile(status.profile_index) or profile
        except HeliaLuxError as err:
            self.stats.failures_in_row += 1
            self.stats.last_error = str(err)
            if self.data is not None and self.stats.failures_in_row < FAILURES_BEFORE_UNAVAILABLE:
                _LOGGER.debug("Abfrage %s gescheitert, behalte letzten Stand: %s", self.stats.failures_in_row, err)
                return self.data
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="unreachable", translation_placeholders={"error": str(err)}
            ) from err

        if self.stats.failures_in_row >= FAILURES_BEFORE_UNAVAILABLE:
            self._note(f"wieder erreichbar nach {self.stats.failures_in_row} gescheiterten Abfragen")
        self.stats.failures_in_row = 0
        self.stats.last_success = dt_util.utcnow()
        if self.desired.last_on is None and any(status.levels):
            self.desired.last_on = status.levels
        if self._adopt_on_first_status:
            self._adopt_on_first_status = False
            if status.color_simulation:
                # Läuft die manuelle Farbe schon, gehört sie ab jetzt HA (Ablauf unbekannt → wird gleich verlängert).
                self.desired.mode = MODE_MANUAL
                self.desired.levels = status.levels
                self._note(f"manuelle Farbe {list(status.levels)} der Lampe übernommen")
            self._save()
        data = HeliaLuxData(status, profiles, self._clock_offset(status), self._remaining(), profile)
        self._check_clock_issue(data.clock_offset_min)
        self.hass.loop.call_soon(self._schedule_maintain, data)
        return data

    async def _read_profile(self, index: int) -> HeliaLuxProfile | None:
        """Aktives Profil lesen; scheitert das, bleibt die Abfrage trotzdem gültig."""
        if index < 0:
            return None
        try:
            return await self.client.profile(index)
        except HeliaLuxError as err:
            _LOGGER.debug("Profil P%s nicht lesbar: %s", index + 1, err)
            return None

    @staticmethod
    def _clock_offset(status: HeliaLuxStatus) -> int | None:
        """Wie viele Minuten die Uhr der Lampe vorgeht (negativ = nach). Nur ohne Tagsimulation messbar."""
        if status.daytime_simulation:
            return None
        now = dt_util.now()
        diff = status.device_minutes - (now.hour * 60 + now.minute)
        return (diff + 720) % 1440 - 720

    def _remaining(self) -> int | None:
        if self.desired.mode != MODE_MANUAL or self.desired.expires is None:
            return None
        return max(0, round((self.desired.expires - dt_util.utcnow()).total_seconds() / 60))

    def _check_clock_issue(self, offset: int | None) -> None:
        issue_id = f"clock_drift_{self.config_entry.entry_id}"
        if offset is not None and abs(offset) >= CLOCK_DRIFT_ISSUE_MIN:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="clock_drift",
                translation_placeholders={"name": self.tank_name, "minutes": str(offset)},
            )
        elif offset is not None and abs(offset) < CLOCK_DRIFT_ISSUE_MIN // 2:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    # --- Zustand halten ------------------------------------------------------------------------------

    @callback
    def _schedule_maintain(self, data: HeliaLuxData) -> None:
        if self._maintaining or (self._fade and not self._fade.done()):
            return
        # Schon hier belegen: zwei Abfragen kurz nacheinander starten sonst zwei Halte-Läufe, bevor einer läuft.
        self._maintaining = True
        self.config_entry.async_create_background_task(self.hass, self._maintain(data), f"{DOMAIN} halten")

    async def _maintain(self, data: HeliaLuxData) -> None:
        self._maintaining = True
        try:
            await self._maintain_inner(data)
        except HeliaLuxError as err:
            _LOGGER.warning("%s: Zustand konnte nicht gehalten werden: %s", self.tank_name, err)
        finally:
            self._maintaining = False

    async def _maintain_inner(self, data: HeliaLuxData) -> None:
        status, want = data.status, self.desired
        if want.mode != MODE_MANUAL:
            return
        if status.daytime_simulation:
            # Tagsimulation wurde an der Lampe/App gestartet – das ist eine bewusste Entscheidung.
            self._note("Tagsimulation an der Lampe gestartet, HA gibt die Kontrolle ab")
            self.desired.mode = MODE_AUTO
            self._save()
            return
        if not status.color_simulation and not self.keep_manual:
            # „Manuelle Farbe halten“ ist aus: Laufzeit abgelaufen → das Profil der Lampe darf übernehmen.
            self._note("manuelle Farbe beendet, Profil der Lampe läuft wieder")
            self.desired.mode = MODE_AUTO
            self.desired.expires = None
            self._save()
            return
        if not status.color_simulation:
            now = dt_util.utcnow()
            if want.levels is None or (self._last_restore and now - self._last_restore < RESTORE_BACKOFF):
                return
            self._last_restore = now
            self.stats.restores += 1
            self._note(
                f"manuelle Farbe verloren (Neustart oder abgelaufen), stelle {list(want.levels)} wieder her",
                logging.WARNING,  # eine Zeile im Log statt Info + Warnung mit demselben Inhalt
            )
            await self._write(want.levels, force_start=True)
            return
        recent = self._last_command and dt_util.utcnow() - self._last_command < ADOPT_GRACE
        if want.levels is not None and status.levels != want.levels and not recent:
            # Jemand hat in der Juwel-App/Weboberfläche nachgeregelt – übernehmen statt dagegen zu kämpfen.
            self._note(f"Werte an der Lampe geändert ({list(status.levels)}), übernommen")
            self.desired.levels = status.levels
            if any(status.levels):
                self.desired.last_on = status.levels
            self._save()
        remaining = self._remaining()
        if self.keep_manual and (remaining is None or remaining < RENEW_BELOW_MIN):
            await self._write(want.levels or status.levels, force_start=True)

    def _note(self, text: str, level: int = logging.INFO) -> None:
        """Eintrag ins Diagnose-Protokoll (letzte 20) und ins HA-Log mit der angegebenen Stufe."""
        stamp = dt_util.now().strftime("%d.%m. %H:%M:%S")
        self.stats.log = [*self.stats.log[-19:], f"{stamp} {text}"]
        _LOGGER.log(level, "%s: %s", self.tank_name, text)

    # --- Befehle -------------------------------------------------------------------------------------

    @property
    def channels(self) -> int:
        return self.data.status.channels if self.data else 4

    async def _write(self, levels: tuple[int, ...], *, force_start: bool = False) -> None:
        levels = tuple(max(0, min(100, round(v))) for v in levels[: self.channels])
        status = self.data.status if self.data else None
        remaining = self._remaining()
        start = (
            force_start
            or status is None
            or not status.color_simulation
            or self.desired.mode != MODE_MANUAL
            or remaining is None
            or (self.keep_manual and remaining < RENEW_BELOW_MIN)
        )
        duration = round(self.color_duration_h * 60)
        reply = await self.client.set_levels(levels, duration if start else None)
        self._last_command = dt_util.utcnow()
        self.desired.mode = MODE_MANUAL
        self.desired.levels = levels
        if any(levels):
            self.desired.last_on = levels
        if start or reply.color_remaining_min is not None:
            minutes = reply.color_remaining_min if reply.color_remaining_min is not None else duration
            self.desired.expires = dt_util.utcnow() + timedelta(minutes=minutes)
        self._save()
        self._apply_reply(reply, levels=levels, color=True)

    def _apply_reply(
        self, reply: HeliaLuxReply, *, levels: tuple[int, ...] | None = None, color: bool | None = None
    ) -> None:
        """Antwort der Lampe sofort übernehmen, statt auf die nächste Abfrage zu warten."""
        if self.data is None:
            return
        status = replace(
            self.data.status,
            levels=reply.levels[: self.channels] if reply.levels else (levels or self.data.status.levels),
            color_simulation=reply.color_simulation if reply.color_simulation is not None else bool(color),
            daytime_simulation=bool(reply.daytime_simulation) if reply.daytime_simulation is not None else False,
        )
        self.async_set_updated_data(replace(self.data, status=status, color_remaining_min=self._remaining()))

    def _cancel_fade(self) -> None:
        if self._fade and not self._fade.done():
            self._fade.cancel()
        self._fade = None

    async def async_set_levels(self, levels: tuple[int, ...], transition: float | None = None) -> None:
        """Kanäle (0–100 %) setzen, optional weich über `transition` Sekunden."""
        self._cancel_fade()
        current = self.data.status.levels if self.data else None
        if not transition or transition < 1 or current is None or current == levels[: len(current)]:
            await self._command(self._write(levels))
            return
        # Erster Schritt sofort (startet ggf. die Farbsimulation und meldet Fehler direkt an den Aufrufer).
        # Höchstens alle FADE_MIN_GAP Sekunden ein Schritt – die Lampe verschluckt sonst Befehle.
        largest = max(abs(t - c) for t, c in zip(levels, current, strict=False))
        steps = max(1, min(int(transition / FADE_MIN_GAP), largest))
        first = _mix(current, levels, 1 / steps)
        await self._command(self._write(first))
        if steps > 1:
            self._fade = self.config_entry.async_create_background_task(
                self.hass, self._run_fade(current, levels, steps, transition / steps), f"{DOMAIN} Übergang"
            )

    async def _run_fade(self, start: tuple[int, ...], target: tuple[int, ...], steps: int, gap: float) -> None:
        last = _mix(start, target, 1 / steps)
        for i in range(2, steps + 1):
            await self._sleep(gap)
            step = _mix(start, target, i / steps)
            if step == last:
                continue
            try:
                await self._write(step)
                last = step
            except HeliaLuxError as err:
                _LOGGER.debug("Übergangsschritt %s/%s gescheitert: %s", i, steps, err)
        if last != target:
            try:
                await self._write(target)
            except HeliaLuxError as err:
                _LOGGER.warning("%s: Zielwert des Übergangs nicht gesetzt: %s", self.tank_name, err)

    async def async_set_channel(self, index: int, value: int) -> None:
        """Einen Kanal (0 = Weiß, 1 = Blau, 2 = Grün, 3 = Rot) setzen, die anderen bleiben."""
        levels = list(self.data.status.levels) if self.data else [0] * self.channels
        levels[index] = value
        await self.async_set_levels(tuple(levels))

    async def _sleep(self, seconds: float) -> None:
        """Warten über den HA-Zeitplaner (in Tests per Zeitsprung steuerbar)."""
        done: asyncio.Future[None] = self.hass.loop.create_future()

        @callback
        def wake(_now: datetime) -> None:
            if not done.done():
                done.set_result(None)

        cancel = async_call_later(self.hass, seconds, wake)
        try:
            await done
        finally:
            cancel()

    async def async_set_color_simulation(self, on: bool) -> None:
        self._cancel_fade()
        if on:
            levels = self.desired.levels or (self.data.status.levels if self.data else (0,) * self.channels)
            await self._command(self._write(levels, force_start=True))
            return
        reply = await self._command(self.client.stop_color_simulation())
        self._set_auto()
        self._apply_reply(reply, color=False)
        await self.async_request_refresh()

    async def async_select_profile(self, index: int) -> None:
        if not self.data or not self.data.profiles:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_profiles")
        self._cancel_fade()
        await self._command(self.client.set_week_profile(index, self.data.profiles.names))
        if self.data.status.color_simulation:
            await self._command(self.client.stop_color_simulation())
        self._set_auto()
        self._profiles_at = None
        await self.async_refresh()

    async def async_set_daytime_simulation(self, on: bool, position_min: int, duration_min: int) -> None:
        self._cancel_fade()
        if on:
            reply = await self._command(self.client.start_daytime_simulation(position_min, duration_min))
        else:
            reply = await self._command(self.client.stop_daytime_simulation())
        self._set_auto()
        self._apply_reply(reply, color=False)
        await self.async_request_refresh()

    def _set_auto(self) -> None:
        self._last_command = dt_util.utcnow()
        self.desired.mode = MODE_AUTO
        self.desired.expires = None
        self._save()

    async def async_set_week_day(self, day: int, index: int) -> None:
        """Profil eines Wochentags (0 = Montag) setzen, die anderen Tage bleiben."""
        if not self.data or not self.data.profiles:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_profiles")
        profiles = self.data.profiles
        week = list(profiles.week) if len(profiles.week) == 7 else [self.data.status.profile_index] * 7
        week[day] = index
        await self._command(self.client.set_week(tuple(week), profiles.names))
        self._profiles_at = None
        await self.async_refresh()

    async def async_set_clouds(self, intensity: int | None = None, motion: int | None = None) -> None:
        """Wolken (0–3) im heute aktiven Profil – nur im Wolken-Fenster (von/bis), nur wo Licht brennt."""
        if not self.data:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_profiles")
        index = self.data.status.profile_index
        current = await self._command(self.client.profile(index))
        base = self._template(index) or current
        cur_i, cur_m = current.clouds
        i = cur_i if intensity is None else max(0, min(3, intensity))
        m = cur_m if motion is None else max(0, min(3, motion))
        if i > 0 and m == 0:
            m = 2  # Wolken ohne Zug stehen still – mittlerer Zug als sinnvoller Start
        prog = self.program
        clouded = base.with_clouds(i, m, prog.cloud_from, prog.cloud_to)
        if prog.template is not None:
            prog.template = _profile_to_dict(clouded)
            self._save()
            await self._apply_program(current)
        else:
            await self._command(self.client.save_profile(clouded, expected_times=current.times))
            self.async_set_updated_data(replace(self.data, profile=clouded))
        window = f"{_hhmm(prog.cloud_from)}–{_hhmm(prog.cloud_to)}"
        self._note(f"Wolken in {current.name}: Stärke {i}, Zug {m if i else 0}, {window}")

    # --- Sonnenverlauf und Eingewöhnung (rechnen täglich aus einer Vorlage) -----------------------

    def acclimatization_factor(self, today: date | None = None) -> float:
        prog = self.program
        if not prog.acclim_on or not prog.acclim_since:
            return 1.0
        days = ((today or dt_util.now().date()) - date.fromisoformat(prog.acclim_since)).days
        share = min(1.0, max(0.0, days / max(1, prog.acclim_weeks * 7)))
        return (prog.acclim_start + (100 - prog.acclim_start) * share) / 100

    def _template(self, index: int) -> HeliaLuxProfile | None:
        tpl = self.program.template
        return _profile_from_dict(tpl) if tpl and tpl.get("index") == index else None

    async def async_set_program(self, key: str, value: Any) -> None:
        """Einstellung ändern und das Profil der Lampe sofort neu rechnen."""
        prog = self.program
        if key == "acclim_on" and value and not prog.acclim_on:
            prog.acclim_since = dt_util.now().date().isoformat()
        setattr(prog, key, value)
        self._save()
        self.async_update_listeners()
        if not self.data:
            return
        if key == "weather_on":
            if value:
                self._weather_written = None
                self._weather_check()
            return
        if key in ("cloud_from", "cloud_to"):
            i, m = self.data.profile.clouds if self.data.profile else (0, 0)
            if i:
                await self.async_set_clouds(i, m)
            return
        await self._apply_program()

    async def _apply_program(self, read: HeliaLuxProfile | None = None) -> None:
        """Aktives Profil aus der Vorlage neu rechnen (Sonne, Eingewöhnung) – oder Vorlage zurückschreiben."""
        if not self.data:
            return
        prog = self.program
        index = self.data.status.profile_index
        if read is None:
            fetched: HeliaLuxProfile = await self._command(self.client.profile(index))
            read = fetched
        current = read
        template = self._template(index)
        if not (prog.sun_on or prog.acclim_on):
            if template is not None:
                await self._command(self.client.save_profile(template, expected_times=current.times))
                self._note(f"Profil {template.name} wieder im Original")
                prog.template = None
                self._save()
                self.async_set_updated_data(replace(self.data, profile=template))
            return
        base = template or current
        if template is None:
            prog.template = _profile_to_dict(current)
            self._save()
        result = base
        if prog.sun_on:
            today = dt_util.now().date()
            rise = get_astral_event_date(self.hass, "sunrise", today)
            dusk = get_astral_event_date(self.hass, "sunset", today)
            if rise and dusk:
                result = result.shifted_to_sun(_minutes(rise), _minutes(dusk), prog.sun_earliest, prog.sun_latest)
        if prog.acclim_on:
            result = result.scaled(self.acclimatization_factor())
        await self._command(self.client.save_profile(result, expected_times=current.times))
        self._note(f"Profil {result.name} neu gerechnet (Sonne: {prog.sun_on}, Eingewöhnung: {prog.acclim_on})")
        self.async_set_updated_data(replace(self.data, profile=result))

    # --- Wolken nach Wetter --------------------------------------------------------------------------

    def weather_clouds(self) -> tuple[int, int] | None:
        entity = self.config_entry.options.get(CONF_WEATHER)
        state = self.hass.states.get(entity) if entity else None
        if state is None:
            return None
        return clouds_for(state.state, dict(state.attributes))

    @callback
    def _weather_event(self, _event: Any) -> None:
        self._weather_check()

    @callback
    def _weather_check(self) -> None:
        """Bei Wetteränderung die Wolken im Profil anpassen – nur wenn sich die Stufe ändert, höchstens alle 30 Min."""
        if not self.program.weather_on or not self.data or self.data.status.color_simulation:
            return
        wanted = self.weather_clouds()
        current = self.data.profile.clouds if self.data.profile else None
        if wanted is None or wanted == current:
            return
        now = dt_util.utcnow()
        if self._weather_written and now - self._weather_written < WEATHER_MIN_GAP:
            return
        self._weather_written = now
        self.config_entry.async_create_background_task(
            self.hass, self._weather_apply(*wanted), f"{DOMAIN} Wolken nach Wetter"
        )

    async def _weather_apply(self, intensity: int, motion: int) -> None:
        try:
            await self.async_set_clouds(intensity, motion)
            self._note(f"Wolken nach Wetter: Stärke {intensity}, Zug {motion}")
        except HomeAssistantError as err:
            _LOGGER.warning("%s: Wolken nach Wetter nicht gesetzt: %s", self.tank_name, err)

    @callback
    def _nightly(self, _now: datetime) -> None:

        prog = self.program
        finished = prog.acclim_on and self.acclimatization_factor() >= 1
        if finished:
            prog.acclim_on = False
            self._note("Eingewöhnung abgeschlossen – volle Helligkeit")
            self._save()
        if prog.sun_on or prog.acclim_on or finished:
            self.config_entry.async_create_background_task(self.hass, self._safe_program(), f"{DOMAIN} nachts")

    async def _safe_program(self) -> None:
        try:
            await self._apply_program()
        except HomeAssistantError as err:
            _LOGGER.warning("%s: Profil nachts nicht neu gerechnet: %s", self.tank_name, err)

    def profile_index(self, profile: str | None) -> int:
        """Profil per Name („My_Profile“, „Standard (P8)“) oder Platz („P8“, „8“); leer = heute aktives."""
        if not self.data or not self.data.profiles:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_profiles")
        if not profile:
            return self.data.status.profile_index
        names = self.data.profiles.names
        text = profile.strip()
        slot = text[1:] if text[:1] in "Pp" else text
        if slot.isdigit() and 1 <= int(slot) <= len(names):
            return int(slot) - 1
        labels = [f"{n} (P{i + 1})" if names.count(n) > 1 and names.index(n) != i else n for i, n in enumerate(names)]
        for candidates in (labels, list(names)):
            if text in candidates:
                return candidates.index(text)
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="unknown_profile", translation_placeholders={"profile": text}
        )

    async def async_get_profile(self, profile: str | None) -> HeliaLuxProfile:
        return await self._command(self.client.profile(self.profile_index(profile)))

    async def async_save_profile(
        self, profile: str | None, points: list[dict[str, Any]], name: str | None = None
    ) -> HeliaLuxProfile:
        """Profil komplett neu setzen. Fehlt 00:00 oder 23:59, wird der letzte Punkt dorthin fortgesetzt.

        Wolken: pro Punkt `clouds`/`cloud_motion` (0–3); fehlen sie überall, bleibt die bisherige Wolken-Einstellung
        des Profils auf allen Punkten mit Licht.
        """
        index = self.profile_index(profile)
        current = await self._command(self.client.profile(index))
        rows = sorted(points, key=lambda p: p["time"])
        if rows and rows[0]["time"] != 0:
            rows.insert(0, {**rows[-1], "time": 0})
        if rows and rows[-1]["time"] != 1439:
            rows.append({**rows[-1], "time": 1439})
        times = [r["time"] for r in rows]
        if len(set(times)) != len(times) or not 2 <= len(rows) <= MAX_PROFILE_POINTS:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="bad_points",
                translation_placeholders={"max": str(MAX_PROFILE_POINTS)},
            )
        colors = ("white", "blue", "green", "red")[: len(current.channels)]
        channels = tuple(tuple(int(r.get(c, 0)) for r in rows) for c in colors)
        lit = [any(ch[n] for ch in channels) for n in range(len(rows))]
        cur_i, cur_m = current.clouds
        if any("clouds" in r or "cloud_motion" in r for r in rows):
            ci = tuple(int(r.get("clouds", 0)) for r in rows)
            cm = tuple(int(r.get("cloud_motion", 0)) if ci[n] else 0 for n, r in enumerate(rows))
        else:
            ci = tuple(cur_i if on else 0 for on in lit)
            cm = tuple(cur_m if on and cur_i else 0 for on in lit)
        new = HeliaLuxProfile(index, name or current.name, tuple(times), channels, ci, cm)
        await self._command(self.client.save_profile(new, expected_times=current.times))
        self._note(f"Profil P{index + 1} „{new.name}“ gespeichert ({len(times)} Stützpunkte)")
        self._profiles_at = None
        await self.async_refresh()
        return new

    def set_keep_manual(self, on: bool) -> None:
        self.keep_manual = on
        self._save()

    def set_number(self, key: str, value: float) -> None:
        setattr(self, key, value)
        self._save()

    async def _command[T](self, aw: Awaitable[T]) -> T:
        try:
            return await aw
        except HeliaLuxError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_shutdown(self) -> None:
        self._cancel_fade()
        await self._store.async_save(self._snapshot())  # nicht auf das verzögerte Speichern warten (Neuladen)
        await super().async_shutdown()


def _minutes(when: datetime) -> int:
    local = dt_util.as_local(when)
    return local.hour * 60 + local.minute


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _mix(a: tuple[int, ...], b: tuple[int, ...], f: float) -> tuple[int, ...]:
    return tuple(round(x + (y - x) * f) for x, y in zip(a, b, strict=False))
