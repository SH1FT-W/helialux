"""Uhrzeiten: Wolken von/bis und Sonnenverlauf frühestens hell / spätestens dunkel."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .coordinator import HeliaLuxCoordinator
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0

# Entitäts-Schlüssel → Feld in ProgramSettings
TIMES = {"cloud_from": "cloud_from", "cloud_to": "cloud_to", "sun_earliest": "sun_earliest", "sun_latest": "sun_latest"}


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(ProgramTime(entry.runtime_data, key) for key in TIMES)


class ProgramTime(HeliaLuxEntity, TimeEntity):
    _platform = "time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HeliaLuxCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._field = TIMES[key]

    @property
    def native_value(self) -> time:
        minutes = int(getattr(self.coordinator.program, self._field))
        return time(minutes // 60, minutes % 60)

    async def async_set_value(self, value: time) -> None:
        await self.coordinator.async_set_program(self._field, value.hour * 60 + value.minute)
