"""Zugriff auf den Webserver der HeliaLux SmartControl (lokal, HTTP).

Die Lampe hat keine richtige API, nur die Dateien ihrer Weboberfläche:

- `statusvars.js`  Zustand: Profil, Gerätezeit, Kanalwerte, Simulationen (nur lesen)
- `wpvars.js`      Profilnamen und Wochenplan (nur lesen)
- `devvars.js`     Modell, Hardware/Firmware, MAC (nur lesen)
- `POST /stat`     Schalten (action 10 = Kanäle, 12 = Tagsimulation, 14 = Farbsimulation)
- `POST /week.html` Wochenplan speichern (key=BU, s0–s6 = Montag–Sonntag)
- `POST /profedit.html` (profNum) wählt das Profil im Editor, `profeditvars.js` liest es dann komplett
  (Stützpunkte, Kanäle, Wolken), `POST /pedit` speichert es: action 30 = „OK“ im Editor (dauerhaft,
  inkl. Name), 31 übernimmt nur einen Stützpunkt in den Zwischenstand. Nichts davon ändert das Licht.
  Höchstens 16 Stützpunkte.

Kanalreihenfolge der Lampe: CH1 Weiß, CH2 Blau, CH3 Grün, CH4 Rot – Werte 0–100 %.
`setvars.js` (WLAN-Zugangsdaten im Klartext) wird absichtlich nie gelesen.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import MAX_PROFILE_NAME

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=8)
# Die Lampe verarbeitet nur eine Anfrage gleichzeitig; die Weboberfläche schickt höchstens eine pro Sekunde.
MIN_REQUEST_GAP = 0.15
RETRY_DELAY = 0.5

MAX_POINTS = 16  # mehr Stützpunkte nimmt der Editor der Lampe nicht an
# Das Speicherformat der Lampe trennt Felder mit & und = und Listen mit [ ]; solche Zeichen (und Anführungszeichen,
# die in den JS-Dateien den Namen begrenzen) dürfen im Profilnamen nicht vorkommen.
PROFILE_NAME_RE = re.compile(rf"^[^&=\[\];'\"]{{1,{MAX_PROFILE_NAME}}}$")

_VAR_RE = re.compile(r"(?P<name>[A-Za-z0-9_]+)=(?:(?P<number>-?\d+)|'(?P<string>[^']*)'|\[(?P<list>[^\]]*)\]);")


class HeliaLuxError(Exception):
    """Lampe nicht erreichbar oder Antwort unbrauchbar."""


@dataclass(frozen=True, slots=True)
class HeliaLuxStatus:
    """Zustand aus statusvars.js."""

    lamp: str
    profile: str
    profile_index: int
    device_minutes: int
    daytime_simulation: bool
    color_simulation: bool
    levels: tuple[int, ...]

    @property
    def channels(self) -> int:
        return len(self.levels)


@dataclass(frozen=True, slots=True)
class HeliaLuxProfiles:
    """Profile aus wpvars.js; `week` = Profilindex je Wochentag."""

    names: tuple[str, ...]
    week: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class HeliaLuxProfile:
    """Ein Profil: Stützpunkte (Minuten), Kanäle W/B/G/R je Stützpunkt in %, Wolken 0–3 je Stützpunkt."""

    index: int
    name: str
    times: tuple[int, ...]
    channels: tuple[tuple[int, ...], ...]
    cloud_intensity: tuple[int, ...]
    cloud_motion: tuple[int, ...]

    def levels_at(self, minute: int) -> tuple[int, ...]:
        """Was das Profil zu dieser Uhrzeit zeigt (linear zwischen den Stützpunkten, wie die Lampe)."""
        times = self.times
        if not times:
            return tuple(0 for _ in self.channels)
        if minute <= times[0]:
            return tuple(ch[0] for ch in self.channels)  # vor dem ersten Punkt gilt der erste, nichts extrapolieren
        for i in range(1, len(times)):
            if minute <= times[i]:
                a, b = times[i - 1], times[i]
                f = 0.0 if b == a else (minute - a) / (b - a)
                return tuple(round(ch[i - 1] + (ch[i] - ch[i - 1]) * f) for ch in self.channels)
        return tuple(ch[-1] for ch in self.channels)

    @property
    def clouds(self) -> tuple[int, int]:
        """(Stärke, Zug) – der höchste Wert über alle Stützpunkte."""
        return max(self.cloud_intensity, default=0), max(self.cloud_motion, default=0)

    # --- Umbauten (geben ein neues Profil zurück) --------------------------------------------------

    def _rows(self) -> list[tuple[int, tuple[int, ...], int, int]]:
        return [
            (t, tuple(ch[n] for ch in self.channels), self.cloud_intensity[n], self.cloud_motion[n])
            for n, t in enumerate(self.times)
        ]

    def _from_rows(self, rows: list[tuple[int, tuple[int, ...], int, int]]) -> HeliaLuxProfile:
        rows = sorted(rows)
        return HeliaLuxProfile(
            self.index,
            self.name,
            tuple(r[0] for r in rows),
            tuple(tuple(r[1][c] for r in rows) for c in range(len(self.channels))),
            tuple(r[2] for r in rows),
            tuple(r[3] for r in rows),
        )

    def with_point(self, minute: int) -> HeliaLuxProfile:
        """Zwischenpunkt einfügen (Werte wie die Lampe sie dort zeigt, Wolken vom vorigen Punkt)."""
        if minute in self.times or len(self.times) >= MAX_POINTS:
            return self
        prev = max((n for n, t in enumerate(self.times) if t < minute), default=0)
        rows = [*self._rows(), (minute, self.levels_at(minute), self.cloud_intensity[prev], self.cloud_motion[prev])]
        return self._from_rows(rows)

    def with_clouds(self, intensity: int, motion: int, start: int = 0, end: int = 1439) -> HeliaLuxProfile:
        """Wolken nur zwischen `start` und `end` – auf Stützpunkten mit Licht; Grenzpunkte werden ergänzt.

        Die Lampe nimmt die Wolken eines Stützpunkts bis zum nächsten Punkt.
        """
        profile = self
        if intensity and (start, end) != (0, 1439):
            profile = profile.with_point(start).with_point(end)
        rows = []
        for t, levels, _ci, _cm in profile._rows():
            on = intensity > 0 and any(levels) and start <= t < end
            rows.append((t, levels, intensity if on else 0, motion if on else 0))
        return profile._from_rows(rows)

    def scaled(self, factor: float) -> HeliaLuxProfile:
        """Alle Kanäle mit `factor` (0–1) dämpfen – für die Eingewöhnung."""
        rows = [(t, tuple(max(0, min(100, round(v * factor))) for v in lv), ci, cm) for t, lv, ci, cm in self._rows()]
        return self._from_rows(rows)

    def shifted_to_sun(self, sunrise: int, sunset: int, earliest: int, latest: int) -> HeliaLuxProfile:
        """Form behalten, aber den Morgen an den Sonnenaufgang und den Abend an den Sonnenuntergang schieben.

        Morgen = vom letzten dunklen Punkt bis zum ersten Punkt mit voller Tageshelligkeit,
        Abend = vom letzten Punkt mit voller Tageshelligkeit bis zum ersten dunklen Punkt danach.
        Begrenzung: frühestens `earliest` hell, spätestens `latest` dunkel.
        """
        rows = self._rows()
        peak = max(max(r[1]) for r in rows) if rows else 0
        # „hell“ = mehr als 10 % der Tageshelligkeit – ein schwaches Nachtlicht zählt als Nacht
        lit = [n for n, r in enumerate(rows) if max(r[1]) > peak * 0.1]
        if not lit:
            return self
        day = [n for n, r in enumerate(rows) if max(r[1]) == peak]
        m_from, m_to = max(lit[0] - 1, 0), day[0]
        e_from, e_to = day[-1], min(lit[-1] + 1, len(rows) - 1)
        t_on, t_off = rows[m_from][0], rows[e_to][0]
        shift_m = max(sunrise - t_on, earliest - t_on)
        shift_e = min(sunset - rows[e_from][0], latest - t_off)
        morning = [(t + shift_m, lv, ci, cm) for t, lv, ci, cm in rows[m_from : m_to + 1]]
        evening = [(t + shift_e, lv, ci, cm) for t, lv, ci, cm in rows[e_from : e_to + 1]]
        if morning[0][0] < 1 or evening[-1][0] > 1438 or morning[-1][0] >= evening[0][0]:
            return self  # passt nicht in den Tag – lieber unverändert lassen
        before = [r for r in rows[:m_from] if r[0] < morning[0][0]]
        after = [r for r in rows[e_to + 1 :] if r[0] > evening[-1][0]]
        return self._from_rows(before + morning + evening + after)


@dataclass(frozen=True, slots=True)
class HeliaLuxDevice:
    """Gerätedaten aus devvars.js."""

    model: str
    hardware: str | None
    firmware: str | None
    mac: str | None


@dataclass(frozen=True, slots=True)
class HeliaLuxReply:
    """Antwort auf POST /stat (JSON): Simulationen, Restlaufzeiten und Kanalwerte."""

    color_simulation: bool | None
    daytime_simulation: bool | None
    color_remaining_min: int | None
    levels: tuple[int, ...] | None


def parse_vars(text: str) -> dict[str, Any]:
    """`name=wert;`-Zuweisungen einer der .js-Dateien in ein Dict lesen."""
    out: dict[str, Any] = {}
    for m in _VAR_RE.finditer(text):
        if m["number"] is not None:
            out[m["name"]] = int(m["number"])
        elif m["string"] is not None:
            out[m["name"]] = m["string"]
        else:
            items = [i.strip() for i in (m["list"] or "").split(",") if i.strip()]
            out[m["name"]] = [int(i) if re.fullmatch(r"-?\d+", i) else i.strip("'\"") for i in items]
    return out


def parse_status(text: str) -> HeliaLuxStatus:
    v = parse_vars(text)
    try:
        levels = tuple(max(0, min(100, int(x))) for x in v["brightness"])
        channels = 2 if v.get("lamp") == "2Ch" else 4
        return HeliaLuxStatus(
            lamp=str(v.get("lamp", "4Ch")),
            profile=str(v.get("profile", "")),
            profile_index=int(v.get("profNum", -1)),
            device_minutes=int(v["tsimtime"]),
            daytime_simulation=v.get("tsimact") == 1,
            color_simulation=v.get("csimact") == 1,
            levels=levels[:channels],
        )
    except (KeyError, TypeError, ValueError) as err:
        raise HeliaLuxError(f"statusvars.js unvollständig: {err}") from err


def parse_profiles(text: str) -> HeliaLuxProfiles:
    v = parse_vars(text)
    names = v.get("profnames")
    if not isinstance(names, list) or not names:
        raise HeliaLuxError("wpvars.js ohne Profilnamen")
    try:
        week = tuple(int(i) for i in v.get("profsel") or [])
    except (TypeError, ValueError) as err:
        raise HeliaLuxError(f"wpvars.js: Wochenplan unlesbar: {err}") from err
    return HeliaLuxProfiles(names=tuple(str(n) for n in names), week=week)


def parse_profile(text: str) -> HeliaLuxProfile:
    v = parse_vars(text)
    try:
        times = tuple(int(t) for t in v["times"])
        channels = tuple(tuple(int(x) for x in v[f"CH{i}"]) for i in range(1, 5) if f"CH{i}" in v)
        n = len(times)
        if not channels or any(len(ch) != n for ch in channels):
            raise HeliaLuxError("profeditvars.js: Kanäle passen nicht zu den Stützpunkten")
        ci = tuple(int(x) for x in v.get("cI") or [0] * n)
        cm = tuple(int(x) for x in v.get("cM") or [0] * n)
        if v.get("lamp") == "2Ch":
            channels = channels[:2]
        return HeliaLuxProfile(int(v["profNum"]), str(v.get("profile", "")), times, channels, ci, cm)
    except (KeyError, TypeError, ValueError) as err:
        raise HeliaLuxError(f"profeditvars.js unvollständig: {err}") from err


def profile_body(profile: HeliaLuxProfile) -> str:
    """Speichern wie der Editor der Lampe: Klartext-Felder, mit encodeURI kodiert (Leerzeichen = %20)."""

    def arr(values: tuple[int, ...]) -> str:
        return "[" + ",".join(str(int(x)) for x in values) + "]"

    if not PROFILE_NAME_RE.match(profile.name):
        # Der Name kommt roh in den Body; mit & = [ ] würde die Lampe die Felder falsch trennen.
        raise HeliaLuxError(f"Profilname „{profile.name}“ enthält Zeichen, die die Lampe nicht speichern kann")
    channels = list(profile.channels) + [tuple(0 for _ in profile.times)] * (4 - len(profile.channels))
    text = (
        f"action=30&PNAME={profile.name}&TIMES={arr(profile.times)}"
        + "".join(f"&CH{i}={arr(ch)}" for i, ch in enumerate(channels, start=1))
        + f"&CINT={arr(profile.cloud_intensity)}&CMOT={arr(profile.cloud_motion)}"
    )
    return quote(text, safe=";,/?:@&=+$-_.!~*'()#")


def parse_device(text: str) -> HeliaLuxDevice:
    v = parse_vars(text)
    info = [str(i) for i in v.get("info") or []]
    if not info:
        raise HeliaLuxError("devvars.js ohne info")

    def at(i: int) -> str | None:
        return info[i] if len(info) > i and info[i] else None

    return HeliaLuxDevice(
        model=info[0],
        hardware=(at(1) or "").lstrip("Vv") or None,
        firmware=(at(2) or "").lstrip("Vv") or None,
        mac=at(4),
    )


def parse_reply(text: str) -> HeliaLuxReply:
    """Antwort auf POST /stat; Unlesbares heißt „nichts bekannt“ (der Befehl selbst ist angekommen)."""
    try:
        return _parse_reply(json.loads(text))
    except (ValueError, TypeError, AttributeError):
        return HeliaLuxReply(None, None, None, None)


def _parse_reply(data: Any) -> HeliaLuxReply:
    s = data.get("S") or {}
    c = data.get("C") or {}

    def flag(key: str) -> bool | None:
        return str(s[key]).lower() == "true" if key in s else None

    remaining = None
    if isinstance(s.get("ctime"), str) and re.fullmatch(r"\d{1,2}:\d{2}", s["ctime"]):
        h, m = s["ctime"].split(":")
        remaining = int(h) * 60 + int(m)
    levels = None
    if isinstance(c.get("ch"), list):
        levels = tuple(max(0, min(100, int(x))) for x in c["ch"][: int(c.get("no", len(c["ch"])))])
    return HeliaLuxReply(flag("cswi"), flag("tswi"), remaining, levels)


def hhmm(minutes: int) -> str:
    """Minuten als HH:MM, begrenzt auf 00:01–23:59 (Eingabefeld der Lampe)."""
    minutes = max(1, min(23 * 60 + 59, int(minutes)))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class HeliaLuxClient:
    """Eine Lampe. Alle Anfragen laufen nacheinander (die Lampe kann nur eine)."""

    def __init__(self, session: aiohttp.ClientSession, host: str, protocol: str = "http") -> None:
        self._session = session
        self.base = f"{protocol}://{host}"
        self._lock = asyncio.Lock()
        self._profile_lock = asyncio.Lock()
        self._last = 0.0

    async def _request(self, method: str, path: str, data: dict[str, Any] | str | None = None) -> str:
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if isinstance(data, str) else None
        async with self._lock:
            loop = asyncio.get_running_loop()
            wait = MIN_REQUEST_GAP - (loop.time() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with self._session.request(
                    method, f"{self.base}/{path}", data=data, headers=headers, timeout=REQUEST_TIMEOUT
                ) as resp:
                    if resp.status != 200:
                        raise HeliaLuxError(f"{path}: HTTP {resp.status}")
                    raw = await resp.read()
            except (TimeoutError, aiohttp.ClientError) as err:
                raise HeliaLuxError(f"{path}: {type(err).__name__} {err}".strip()) from err
            finally:
                self._last = loop.time()
        return raw.decode("utf-8", errors="replace")

    async def _post_stat(self, data: dict[str, Any]) -> HeliaLuxReply:
        _LOGGER.debug("POST /stat %s", data)
        try:
            text = await self._request("POST", "stat", data)
        except HeliaLuxError:
            # Einmal wiederholen: alle Befehle sind idempotent, der Webserver verschluckt gelegentlich einen.
            await asyncio.sleep(RETRY_DELAY)
            text = await self._request("POST", "stat", data)
        return parse_reply(text)

    async def status(self) -> HeliaLuxStatus:
        return parse_status(await self._request("GET", "statusvars.js"))

    async def profiles(self) -> HeliaLuxProfiles:
        return parse_profiles(await self._request("GET", "wpvars.js"))

    async def device(self) -> HeliaLuxDevice:
        return parse_device(await self._request("GET", "devvars.js"))

    async def set_levels(self, levels: tuple[int, ...], start_minutes: int | None = None) -> HeliaLuxReply:
        """Kanäle setzen. Mit `start_minutes` wird die manuelle Farbsimulation (neu) gestartet."""
        data: dict[str, Any] = {"action": 10}
        if start_minutes is not None:
            data = {"action": 14, "cswi": "true", "ctime": hhmm(start_minutes), "tswi": "false"}
        for i, value in enumerate(levels, start=1):
            data[f"ch{i}"] = max(0, min(100, round(value)))
        return await self._post_stat(data)

    async def stop_color_simulation(self) -> HeliaLuxReply:
        return await self._post_stat({"action": 14, "cswi": "false"})

    async def start_daytime_simulation(self, position_min: int, duration_min: int) -> HeliaLuxReply:
        return await self._post_stat(
            {
                "action": 12,
                "ch5": max(0, min(1439, int(position_min))),
                "tswi": "true",
                "ttime": hhmm(duration_min),
                "cswi": "false",
            }
        )

    async def stop_daytime_simulation(self) -> HeliaLuxReply:
        return await self._post_stat({"action": 12, "tswi": "false", "cswi": "false"})

    async def set_week(self, week: tuple[int, ...], names: tuple[str, ...]) -> None:
        """Wochenplan speichern: Profilindex je Tag, Montag zuerst (wie „OK“ auf der Wochenplan-Seite)."""
        data = {"key": "BU", **{f"s{day}": f"P{index + 1} | {names[index]}" for day, index in enumerate(week)}}
        await self._request("POST", "week.html", data)

    async def set_week_profile(self, index: int, names: tuple[str, ...]) -> None:
        """Ein Profil für alle sieben Wochentage."""
        await self.set_week((index,) * 7, names)

    async def profile(self, index: int) -> HeliaLuxProfile:
        """Ein Profil komplett lesen (wählt es dafür im Editor der Lampe aus)."""
        async with self._profile_lock:
            await self._request("POST", "profedit.html", {"profNum": index})
            profile = parse_profile(await self._request("GET", "profeditvars.js"))
        if profile.index != index:
            raise HeliaLuxError(f"profeditvars.js zeigt P{profile.index + 1} statt P{index + 1}")
        return profile

    async def save_profile(self, profile: HeliaLuxProfile, expected_times: tuple[int, ...] | None = None) -> None:
        """Profil zurückschreiben. Vorher genau dieses Profil auswählen – die Lampe speichert ins gewählte.

        Schutz gegen gleichzeitiges Bearbeiten (App): die Stützpunkte in der Lampe müssen noch so sein wie beim
        Lesen – `expected_times`, sonst die Zeiten des neuen Profils.
        """
        expected = profile.times if expected_times is None else expected_times
        async with self._profile_lock:
            await self._request("POST", "profedit.html", {"profNum": profile.index})
            check = parse_profile(await self._request("GET", "profeditvars.js"))
            if check.index != profile.index or check.times != expected:
                raise HeliaLuxError("Profil hat sich in der Lampe geändert – nicht gespeichert")
            await self._request("POST", "pedit", profile_body(profile))
