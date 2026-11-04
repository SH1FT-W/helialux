"""Juwel HeliaLux SmartControl."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import config_validation as cv, issue_registry as ir, service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import PROFILE_NAME_RE, HeliaLuxClient
from .const import (
    CONF_TANK_HOST,
    CONF_TANK_PROTOCOL,
    DOMAIN,
    MAX_PROFILE_NAME,
    MAX_PROFILE_POINTS,
    OLD_VERSION_ISSUE,
    STORAGE_VERSION,
)
from .coordinator import HeliaLuxCoordinator
from .old_version import MOVING_OVER_URL, async_old_version_installed

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

type HeliaLuxConfigEntry = ConfigEntry[HeliaLuxCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_PERCENT = vol.All(vol.Coerce(int), vol.Range(min=0, max=100))
_CLOUD = vol.All(vol.Coerce(int), vol.Range(min=0, max=3))


def _minutes(value: object) -> int:
    """„HH:MM“ (auch „H:MM“, „HH:MM:SS“ oder ein Zeit-Objekt) → Minuten seit Mitternacht."""
    t = cv.time(value)
    return t.hour * 60 + t.minute


# Dieselbe Regel wie beim Speichern (api.PROFILE_NAME_RE), hier mit lesbarer Längenmeldung.
_NAME = vol.All(str, vol.Length(min=1, max=MAX_PROFILE_NAME), vol.Match(PROFILE_NAME_RE))
_POINT = vol.Schema(
    {
        vol.Required("time"): _minutes,
        vol.Optional("white", default=0): _PERCENT,
        vol.Optional("blue", default=0): _PERCENT,
        vol.Optional("green", default=0): _PERCENT,
        vol.Optional("red", default=0): _PERCENT,
        vol.Optional("clouds"): _CLOUD,
        vol.Optional("cloud_motion"): _CLOUD,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienst `set_channels`: Kanäle direkt in % (fehlende bleiben), optional mit Übergang."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "set_channels",
        entity_domain=LIGHT_DOMAIN,
        schema={
            vol.Optional("white"): _PERCENT,
            vol.Optional("blue"): _PERCENT,
            vol.Optional("green"): _PERCENT,
            vol.Optional("red"): _PERCENT,
            vol.Optional("transition"): vol.All(vol.Coerce(float), vol.Range(min=0, max=21600)),
        },
        func="async_set_channels",
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "get_profile",
        entity_domain=LIGHT_DOMAIN,
        schema={vol.Optional("profile"): cv.string},
        func="async_get_profile",
        supports_response=SupportsResponse.ONLY,
    )
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "set_profile",
        entity_domain=LIGHT_DOMAIN,
        schema={
            vol.Optional("profile"): cv.string,
            vol.Optional("name"): _NAME,
            vol.Required("points"): vol.All(cv.ensure_list, [_POINT], vol.Length(min=1, max=MAX_PROFILE_POINTS)),
        },
        func="async_set_profile",
    )
    await _async_check_old_version(hass)
    return True


async def _async_check_old_version(hass: HomeAssistant) -> None:
    """Repair notice while the old version is still installed (the flows refuse new entries then)."""
    if await async_old_version_installed(hass):
        ir.async_create_issue(
            hass,
            DOMAIN,
            OLD_VERSION_ISSUE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=OLD_VERSION_ISSUE,
            learn_more_url=MOVING_OVER_URL,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, OLD_VERSION_ISSUE)


async def async_setup_entry(hass: HomeAssistant, entry: HeliaLuxConfigEntry) -> bool:
    client = HeliaLuxClient(
        async_get_clientsession(hass), entry.data[CONF_TANK_HOST], entry.data.get(CONF_TANK_PROTOCOL, "http")
    )
    coordinator = HeliaLuxCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeliaLuxConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Beim Löschen auch den gespeicherten Wunschzustand entfernen (.storage/helialux.<entry_id>)."""
    await Store[dict[str, Any]](hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
