"""Die Lampe als RGBW-Licht.

Lampe: Weiß/Blau/Grün/Rot je 0–100 %. Home Assistant: rgbw_color (R, G, B, W) je 0–255.
`rgbw_color` ist der absolute Kanalwert (wie bei der alten Integration – bestehende Automationen
schicken absolute Werte), `brightness` ist der hellste Kanal.

- nur `rgbw_color`            → genau diese Kanalwerte
- `rgbw_color` + `brightness` → Farbe so skaliert, dass der hellste Kanal `brightness` hat
- nur `brightness`            → aktuelle (oder zuletzt eingeschaltete) Mischung heller/dunkler
- nichts                      → bleibt, wie es ist; war sie aus: letzte eingeschaltete Mischung
- `transition`                → Übergang in kleinen Schritten (die Lampe selbst kann nicht überblenden)
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGBW_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .api import HeliaLuxProfile
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([HeliaLuxLight(entry.runtime_data, "light_name", f"{entry.runtime_data.slug}_light", "light")])


def to_rgbw(levels: tuple[int, ...]) -> tuple[int, int, int, int]:
    """Lampe (W, B, G, R) in % → HA (R, G, B, W) 0–255. Zweikanal-Lampen: Weiß + Blau."""
    w, b, g, r = (*levels, 0, 0, 0, 0)[:4]
    return (round(r * 2.55), round(g * 2.55), round(b * 2.55), round(w * 2.55))


def to_levels(rgbw: tuple[float, ...], channels: int) -> tuple[int, ...]:
    """HA (R, G, B, W) 0–255 → Lampe (W, B, G, R) in %."""
    r, g, b, w = (min(255.0, max(0.0, float(v))) / 2.55 for v in rgbw)
    return tuple(round(v) for v in (w, b, g, r)[:channels])


def scaled(levels: tuple[int, ...], brightness: int) -> tuple[int, ...]:
    """Mischung beibehalten, hellster Kanal = brightness (0–255)."""
    top = max(levels, default=0)
    target = brightness / 2.55
    if top == 0:
        return tuple(round(target) for _ in levels)
    return tuple(round(v * target / top) for v in levels)


def profile_response(profile: HeliaLuxProfile) -> dict[str, Any]:
    colors = ("white", "blue", "green", "red")
    return {
        "profile": profile.name,
        "slot": f"P{profile.index + 1}",
        "points": [
            {
                "time": f"{t // 60:02d}:{t % 60:02d}",
                **{c: ch[n] for c, ch in zip(colors, profile.channels, strict=False)},
                "clouds": profile.cloud_intensity[n],
                "cloud_motion": profile.cloud_motion[n],
            }
            for n, t in enumerate(profile.times)
        ],
    }


class HeliaLuxLight(HeliaLuxEntity, LightEntity):
    _platform = "light"
    _attr_supported_color_modes = {ColorMode.RGBW}  # noqa: RUF012 (HA-Konvention)
    _attr_color_mode = ColorMode.RGBW
    _attr_supported_features = LightEntityFeature.TRANSITION

    @property
    def _levels(self) -> tuple[int, ...]:
        return self.coordinator.data.status.levels

    @property
    def is_on(self) -> bool:
        return any(self._levels)

    @property
    def brightness(self) -> int:
        return round(max(self._levels, default=0) * 2.55)

    @property
    def rgbw_color(self) -> tuple[int, int, int, int]:
        return to_rgbw(self._levels)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"manual": self.coordinator.data.status.color_simulation}

    async def async_turn_on(self, **kwargs: Any) -> None:
        channels = self.coordinator.channels
        rgbw = kwargs.get(ATTR_RGBW_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        base = self._levels if self.is_on else (self.coordinator.desired.last_on or (100,) * channels)
        if rgbw is not None:
            levels = to_levels(rgbw, channels)
            if brightness is not None:
                levels = scaled(levels, brightness)
        elif brightness is not None:
            levels = scaled(base, brightness)
        else:
            levels = base
        await self.coordinator.async_set_levels(levels, kwargs.get(ATTR_TRANSITION))

    async def async_set_channels(self, transition: float | None = None, **channels: int) -> None:
        """Dienst juwel_helialux.set_channels: Kanäle in %, nicht genannte bleiben wie sie sind."""
        levels = list(self._levels)
        for index, color in enumerate(("white", "blue", "green", "red")[: len(levels)]):
            if color in channels:
                levels[index] = channels[color]
        await self.coordinator.async_set_levels(tuple(levels), transition)

    async def async_get_profile(self, profile: str | None = None) -> dict[str, Any]:
        """Dienst juwel_helialux.get_profile: ein Profil im Format von set_profile."""
        return profile_response(await self.coordinator.async_get_profile(profile))

    async def async_set_profile(
        self, points: list[dict[str, Any]], profile: str | None = None, name: str | None = None
    ) -> None:
        """Dienst juwel_helialux.set_profile: Stützpunkte eines Profils neu setzen."""
        await self.coordinator.async_save_profile(profile, points, name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_levels((0,) * self.coordinator.channels, kwargs.get(ATTR_TRANSITION))
