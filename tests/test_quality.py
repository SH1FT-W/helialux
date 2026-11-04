"""Quality-Scale-Punkte: Diagnose ohne IP-Adresse, übersetzte Fehlermeldungen."""

from __future__ import annotations

import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import pytest

from custom_components.helialux.diagnostics import async_get_config_entry_diagnostics

from .conftest import FakeLamp, make_entry

COMPONENT = Path(__file__).parent.parent / "custom_components" / "helialux"


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
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    key = f"helialux.{entry.entry_id}"
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert key in hass_storage  # beim Entladen gespeichert
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_no_takeover_of_other_integrations(hass: HomeAssistant, lamp: FakeLamp, hass_storage) -> None:
    """Own domain, and a first start reads nothing but its own store (hacs/default#13077).

    Earlier versions shared the domain of MrSleeps' integration and imported its slider values.
    """
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["domain"] == "helialux"
    entry = make_entry()
    for prefix in ("juwel_helialux", "helialux"):
        hass_storage[f"{prefix}_{entry.entry_id}_manual_color_simulation_duration.json"] = {
            "version": 1,
            "key": f"{prefix}_{entry.entry_id}_manual_color_simulation_duration.json",
            "data": {"value": 5},
        }
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.color_duration_h == 12.0
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def test_old_domain_only_named_for_the_warning() -> None:
    """The old domain appears in const.py only (for the warning), no code reads its entries or stores."""
    for path in COMPONENT.glob("*.py"):
        text = path.read_text()
        if path.name == "const.py":
            assert text.count('"juwel_helialux"') == 1
        else:
            assert "juwel_helialux" not in text, path.name


@pytest.mark.parametrize(
    ("tracker", "warned"),
    [
        ("https://github.com/SH1FT-W/helialux/issues", True),
        ("https://github.com/MrSleeps/Juwel-HeliaLux-Home-Assistant-Custom-Component/issues", False),
        (None, False),
    ],
)
async def test_old_version_warning(hass: HomeAssistant, lamp: FakeLamp, tracker, warned) -> None:
    """Old HeliaLux (domain juwel_helialux) still installed: repair notice; MrSleeps' integration: none."""
    found = {"juwel_helialux": SimpleNamespace(issue_tracker=tracker)} if tracker else {}
    entry = make_entry()
    entry.add_to_hass(hass)
    with patch("custom_components.helialux.old_version.async_get_custom_components", AsyncMock(return_value=found)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue("helialux", "old_version_installed")
    assert (issue is not None) is warned
    if issue:
        assert issue.translation_key == "old_version_installed"
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("source", [SOURCE_USER, SOURCE_DHCP])
async def test_flows_refuse_while_old_version_installed(hass: HomeAssistant, lamp: FakeLamp, source) -> None:
    """No second entry next to the old version's running entry (async_setup and its notice run only with an entry)."""
    found = {"juwel_helialux": SimpleNamespace(issue_tracker="https://github.com/SH1FT-W/helialux/issues")}
    data = DhcpServiceInfo(ip="192.0.2.20", hostname="", macaddress="020000000001") if source == SOURCE_DHCP else None
    with patch("custom_components.helialux.old_version.async_get_custom_components", AsyncMock(return_value=found)):
        result = await hass.config_entries.flow.async_init("helialux", context={"source": source}, data=data)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "old_version_installed"
    assert not lamp.posts
    assert not hass.config_entries.async_entries("helialux")
