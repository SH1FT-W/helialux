"""Erreichbarkeit der Lampe (bleibt verfügbar, auch wenn die Lampe es nicht ist)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ReachableSensor(entry.runtime_data, "reachable")])


class ReachableSensor(HeliaLuxEntity, BinarySensorEntity):
    _platform = "binary_sensor"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.stats
        return {
            "restores": stats.restores,
            "last_error": stats.last_error,
            "last_success": stats.last_success.isoformat() if stats.last_success else None,
        }
