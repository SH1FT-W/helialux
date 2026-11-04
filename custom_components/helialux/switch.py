"""Schalter: manuelle Farbsimulation (HA steuert) und Tagsimulation (Zeitraffer der Lampe)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .coordinator import HeliaLuxCoordinator
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ColorSimulationSwitch(coordinator, "manual_color_simulation"),
            DaytimeSimulationSwitch(coordinator, "manual_daytime_simulation"),
            KeepManualSwitch(coordinator, "keep_manual"),
            ProgramSwitch(coordinator, "sun_cycle", "sun_on"),
            ProgramSwitch(coordinator, "acclimatization", "acclim_on"),
            ProgramSwitch(coordinator, "weather_clouds", "weather_on"),
        ]
    )


class ColorSimulationSwitch(HeliaLuxEntity, SwitchEntity):
    """An = Home Assistant bestimmt die Farbe, aus = das Profil der Lampe läuft."""

    _platform = "switch"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.status.color_simulation

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_color_simulation(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_color_simulation(False)


class DaytimeSimulationSwitch(HeliaLuxEntity, SwitchEntity):
    """Spielt das Profil ab der eingestellten Uhrzeit für die eingestellte Dauer ab."""

    _platform = "switch"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.status.daytime_simulation

    async def async_turn_on(self, **kwargs: Any) -> None:
        c = self.coordinator
        await c.async_set_daytime_simulation(True, round(c.daytime_position_h * 60), round(c.daytime_duration_h * 60))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_daytime_simulation(False, 0, 0)


class KeepManualSwitch(HeliaLuxEntity, SwitchEntity):
    """An: HA hält die manuelle Farbe (verlängert, stellt nach Neustart wieder her).
    Aus: nach der eingestellten Laufzeit übernimmt wieder das Profil der Lampe."""

    _platform = "switch"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.coordinator.keep_manual

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.set_keep_manual(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.set_keep_manual(False)
        self.async_write_ha_state()


class ProgramSwitch(HeliaLuxEntity, SwitchEntity):
    """Sonnenverlauf bzw. Eingewöhnung: das aktive Profil wird täglich aus einer Vorlage neu gerechnet."""

    _platform = "switch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HeliaLuxCoordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self._field = field

    @property
    def is_on(self) -> bool:
        return bool(getattr(self.coordinator.program, self._field))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._field == "weather_on":
            wanted = self.coordinator.weather_clouds()
            return {
                "weather_entity": self.coordinator.config_entry.options.get("weather_entity"),
                "clouds_from_weather": list(wanted) if wanted else None,
            }
        if self._field == "acclim_on":
            prog = self.coordinator.program
            return {
                "since": prog.acclim_since,
                "factor_percent": round(self.coordinator.acclimatization_factor() * 100),
            }
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_program(self._field, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_program(self._field, False)
