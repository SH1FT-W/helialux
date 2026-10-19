"""Regler: Kanäle (Weiß/Blau/Grün/Rot in %), Laufzeit der Farbsimulation, Startzeit/Dauer der Tagsimulation."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .coordinator import HeliaLuxCoordinator
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HeliaLuxNumberDescription(NumberEntityDescription):
    attr: str


NUMBERS = (
    HeliaLuxNumberDescription(
        key="manual_color_simulation_duration",
        attr="color_duration_h",
        native_min_value=1,
        native_max_value=23.5,
        native_step=0.5,
    ),
    HeliaLuxNumberDescription(
        key="manual_daytime_simulation_duration",
        attr="daytime_duration_h",
        native_min_value=0.5,
        native_max_value=23.5,
        native_step=0.5,
    ),
    HeliaLuxNumberDescription(
        key="daytime_simulation_position",
        attr="daytime_position_h",
        native_min_value=0,
        native_max_value=23.75,
        native_step=0.25,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    # Die alte Integration hatte hier die entry_id statt des Tank-Namens in der unique_id.
    async_add_entities(HeliaLuxNumber(coordinator, d, f"{entry.entry_id}_{d.key}") for d in NUMBERS)
    async_add_entities(
        ChannelNumber(coordinator, index, color) for index, color in enumerate(CHANNELS[: coordinator.channels])
    )
    async_add_entities(
        [
            ProgramNumber(coordinator, "acclim_start", 10, 100, PERCENTAGE),
            ProgramNumber(coordinator, "acclim_weeks", 1, 12, UnitOfTime.WEEKS),
        ]
    )


class HeliaLuxNumber(HeliaLuxEntity, NumberEntity):
    _platform = "number"
    entity_description: HeliaLuxNumberDescription
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: HeliaLuxCoordinator, description: HeliaLuxNumberDescription, uid: str) -> None:
        super().__init__(coordinator, description.key, uid)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return float(getattr(self.coordinator, self.entity_description.attr))

    async def async_set_native_value(self, value: float) -> None:
        c = self.coordinator
        c.set_number(self.entity_description.attr, float(value))
        self.async_write_ha_state()
        if self.entity_description.attr == "daytime_position_h" and c.data.status.daytime_simulation:
            # Läuft die Tagsimulation, springt sie sofort an die neue Uhrzeit.
            await c.async_set_daytime_simulation(True, round(value * 60), round(c.daytime_duration_h * 60))


# Reihenfolge der Kanäle an der Lampe
CHANNELS = ("white", "blue", "green", "red")


class ChannelNumber(HeliaLuxEntity, NumberEntity):
    """Ein Kanal als Schieberegler – schaltet die manuelle Farbsimulation bei Bedarf ein."""

    _platform = "number"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: HeliaLuxCoordinator, index: int, color: str) -> None:
        super().__init__(coordinator, f"{color}_level", object_id=color)
        self._index = index

    @property
    def native_value(self) -> int:
        return self.coordinator.data.status.levels[self._index]

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_channel(self._index, round(value))


class ProgramNumber(HeliaLuxEntity, NumberEntity):
    """Eingewöhnung: Start-Helligkeit und Dauer."""

    _platform = "number"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, coordinator: HeliaLuxCoordinator, key: str, low: int, high: int, unit: str) -> None:
        super().__init__(coordinator, key)
        self._attr_native_min_value, self._attr_native_max_value = low, high
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> int:
        return int(getattr(self.coordinator.program, self._attr_translation_key or ""))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_program(self._attr_translation_key or "", int(value))
