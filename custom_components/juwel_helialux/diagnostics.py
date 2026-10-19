"""Diagnose-Download: Zustand, Wunschzustand und die letzten Ereignisse."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from . import HeliaLuxConfigEntry
from .const import CONF_TANK_HOST

REDACT = {CONF_TANK_HOST, "mac"}


def _hide_host(text: str | None, host: str) -> str | None:
    """Fehlertexte von aiohttp nennen die IP-Adresse der Lampe – im Download ausblenden."""
    return text.replace(host, REDACTED) if text and host else text


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: HeliaLuxConfigEntry) -> dict[str, Any]:
    c = entry.runtime_data
    data = c.data
    host = str(entry.data.get(CONF_TANK_HOST) or "")
    return {
        "entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, REDACT),
        "device": async_redact_data(asdict(c.device), REDACT) if c.device else None,
        "status": asdict(data.status) if data else None,
        "profiles": asdict(data.profiles) if data and data.profiles else None,
        "clock_offset_min": data.clock_offset_min if data else None,
        "desired": c.desired.as_dict(),
        "numbers": {
            "color_duration_h": c.color_duration_h,
            "daytime_position_h": c.daytime_position_h,
            "daytime_duration_h": c.daytime_duration_h,
        },
        "stats": {
            "restores": c.stats.restores,
            "failures_in_row": c.stats.failures_in_row,
            "last_error": _hide_host(c.stats.last_error, host),
            "last_success": c.stats.last_success.isoformat() if c.stats.last_success else None,
            "log": [_hide_host(line, host) for line in c.stats.log],
        },
    }
