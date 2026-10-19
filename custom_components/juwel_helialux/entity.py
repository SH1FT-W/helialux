"""Gemeinsame Basis aller Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HeliaLuxCoordinator


class HeliaLuxEntity(CoordinatorEntity[HeliaLuxCoordinator]):
    """unique_id = `<tank-slug>_<key>` – wie bei der alten Integration, damit Entity-IDs und Verlauf bleiben."""

    _attr_has_entity_name = True
    _platform: str

    def __init__(
        self, coordinator: HeliaLuxCoordinator, key: str, unique_id: str | None = None, object_id: str | None = None
    ) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = unique_id or f"{coordinator.slug}_{key}"
        # Englische Entity-IDs wie bei der alten Integration (gilt nur für neu angelegte Entitäten).
        self.entity_id = f"{self._platform}.{coordinator.slug}_{object_id or key}"
        device = coordinator.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.slug)},
            connections={(CONNECTION_NETWORK_MAC, format_mac(device.mac))} if device and device.mac else set(),
            name=coordinator.tank_name,
            manufacturer="Juwel",
            model=f"{device.model} {coordinator.data.status.lamp}" if device else "HeliaLux SmartControl",
            sw_version=device.firmware if device else None,
            hw_version=device.hardware if device else None,
            configuration_url=coordinator.client.base,
        )
