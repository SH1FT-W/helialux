"""MAC helpers shared by the config flow and the entry migration."""

from __future__ import annotations

from ipaddress import ip_address
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac

from .const import DOMAIN

_MAC = re.compile(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}")  # as written by format_mac


def is_mac(value: str | None) -> bool:
    """New entries use the MAC as unique_id, entries of the old integration the lamp URL."""
    return value is not None and _MAC.fullmatch(value) is not None


def is_ip(host: str) -> bool:
    """Only a plain IP address may be replaced by a discovered one (a host name stays as entered)."""
    try:
        ip_address(host)
    except ValueError:
        return False
    return True


def device_macs(hass: HomeAssistant, entry_id: str) -> set[str]:
    """MACs the entry's device reported to the device registry (empty if the lamp never sent one)."""
    return {
        format_mac(value)
        for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
        for kind, value in device.connections
        if kind == CONNECTION_NETWORK_MAC
    }


def mac_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """MAC to replace the URL unique_id of an old entry with, or None if that is not safe.

    Safe means: the entry's device reported exactly one MAC (the lamp itself sent it, see
    entity.device_info), its connections are not unreconciled copies from a split composite
    device, and no other entry of this domain, ignored ones included, already uses that MAC.
    Entity unique_ids, device identifiers and the store do not depend on the entry's unique_id.
    """
    if is_mac(entry.unique_id):
        return None
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    # Connections copied from a pre-2026.9 composite device may belong to another entry.
    if any(getattr(device, "has_composite_identifiers", False) for device in devices):
        return None
    macs = device_macs(hass, entry.entry_id)
    if len(macs) != 1:
        return None
    mac = macs.pop()
    others = hass.config_entries.async_entries(DOMAIN, include_ignore=True, include_disabled=True)
    if any(other.unique_id == mac for other in others if other.entry_id != entry.entry_id):
        return None
    return mac
