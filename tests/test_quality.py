"""Quality-Scale-Punkte: Diagnose ohne IP-Adresse, übersetzte Fehlermeldungen."""

from __future__ import annotations

import json
from pathlib import Path
import re

from homeassistant.core import HomeAssistant

from custom_components.juwel_helialux.diagnostics import async_get_config_entry_diagnostics

from .conftest import FakeLamp, old_entry

COMPONENT = Path(__file__).parent.parent / "custom_components" / "juwel_helialux"


async def test_diagnostics_hide_host_in_errors(hass: HomeAssistant, setup) -> None:
    stats = setup.runtime_data.stats
    stats.last_error = "statusvars.js: ClientConnectorError Cannot connect to host 192.0.2.10:80"
    stats.log.append("12:00 Fehler bei 192.0.2.10")
    diag = await async_get_config_entry_diagnostics(hass, setup)
    assert "192.0.2.10" not in str(diag)
    assert diag["stats"]["last_error"].endswith("**REDACTED**:80")


def test_exception_keys_translated() -> None:
    """Jeder translation_key einer Ausnahme steht in strings.json und beiden Übersetzungen."""
    code = "".join(p.read_text() for p in COMPONENT.glob("*.py"))
    used = set(re.findall(r'translation_domain=DOMAIN,\s*translation_key="(\w+)"', code))
    assert used
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        exceptions = json.loads((COMPONENT / name).read_text())["exceptions"]
        assert used <= exceptions.keys(), name


async def test_remove_entry_deletes_store(hass: HomeAssistant, lamp: FakeLamp, hass_storage) -> None:
    entry = old_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    key = f"juwel_helialux.{entry.entry_id}"
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert key in hass_storage  # beim Entladen gespeichert
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage
