"""Detect HeliaLux 26.11.2 or earlier (OLD_DOMAIN) still lying in custom_components."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_custom_components

from .const import OLD_DOMAIN

MOVING_OVER_URL = "https://github.com/SH1FT-W/helialux#moving-over"


async def async_old_version_installed(hass: HomeAssistant) -> bool:
    """True while our old version is installed.

    Updating in the Marketplace installs this version into a new folder and leaves the old one in
    place, so the old entry keeps running. Only the manifest of the custom integration is looked at
    (cached by Home Assistant at start); nothing is read from its entries. MrSleeps' integration uses
    the same domain but another issue tracker and is not reported.
    """
    old = (await async_get_custom_components(hass)).get(OLD_DOMAIN)
    return old is not None and "SH1FT-W/helialux" in (old.issue_tracker or "")
