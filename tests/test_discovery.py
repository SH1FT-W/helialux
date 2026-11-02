"""DHCP discovery and the URL -> MAC unique_id migration of old entries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_DHCP, SOURCE_IGNORE, SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.juwel_helialux.const import DOMAIN
from custom_components.juwel_helialux.device import mac_unique_id

from .conftest import ENTRY_ID, FakeLamp, old_entry

MAC = "02:00:00:00:00:01"
URL_ID = "http://192.0.2.10"


def dhcp(ip: str = "192.0.2.20", mac: str = "020000000001") -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="", macaddress=mac)


async def discover(hass: HomeAssistant, info: DhcpServiceInfo):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=info)
    await hass.async_block_till_done()
    return result


def entry_v22(unique_id: str = URL_ID, host: str = "192.0.2.10", entry_id: str = ENTRY_ID) -> MockConfigEntry:
    """Entry as it is stored by 26.11.1 and earlier (version 2.2)."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title="Trigon 190",
        version=2,
        minor_version=2,
        unique_id=unique_id,
        data={"tank_host": host, "tank_name": "Trigon 190", "tank_protocol": "http"},
        options={"scan_interval": 15},
    )


def add_device(hass: HomeAssistant, entry: MockConfigEntry, *macs: str) -> None:
    """Device as an earlier version registered it: the MAC the lamp reported as connection."""
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "trigon_190")},
        connections={(CONNECTION_NETWORK_MAC, mac) for mac in macs},
    )


async def unload(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.async_block_till_done()
    if entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_dhcp_new_lamp(hass: HomeAssistant, lamp: FakeLamp):
    result = await discover(hass, dhcp())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"] == {"host": "192.0.2.20"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"tank_name": "Trigon 190"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == MAC
    assert entry.data == {"tank_host": "192.0.2.20", "tank_name": "Trigon 190", "tank_protocol": "http"}
    assert entry.options == {"scan_interval": 15}
    # The same lamp seen again is not offered a second time.
    result = await discover(hass, dhcp())
    assert result["reason"] == "already_configured"
    await unload(hass, entry)


async def test_dhcp_lamp_not_answering(hass: HomeAssistant, lamp: FakeLamp):
    lamp.offline = True
    assert (await discover(hass, dhcp()))["reason"] == "cannot_connect"
    lamp.offline = False
    lamp.mac = "02:00:00:00:00:02"  # the address already belongs to another device
    assert (await discover(hass, dhcp()))["reason"] == "cannot_connect"


async def test_dhcp_ignored_lamp_stays_ignored(hass: HomeAssistant, lamp: FakeLamp):
    MockConfigEntry(domain=DOMAIN, source=SOURCE_IGNORE, unique_id=MAC).add_to_hass(hass)
    assert (await discover(hass, dhcp()))["reason"] == "already_configured"
    assert not lamp.posts


async def test_dhcp_updates_ip_of_mac_entry(hass: HomeAssistant, lamp: FakeLamp):
    entry = entry_v22(unique_id=MAC)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await discover(hass, dhcp(ip="192.0.2.20"))
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["tank_host"] == "192.0.2.20"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.client.base == "http://192.0.2.20"  # reloaded with the new address
    # Same address again: nothing to change.
    assert (await discover(hass, dhcp(ip="192.0.2.20")))["reason"] == "already_configured"
    assert entry.data["tank_host"] == "192.0.2.20"
    await unload(hass, entry)


async def test_dhcp_keeps_host_name(hass: HomeAssistant, lamp: FakeLamp):
    """A host name entered by the user is not replaced by the discovered IP."""
    entry = entry_v22(unique_id=MAC, host="aquarium.example")
    entry.add_to_hass(hass)
    assert (await discover(hass, dhcp()))["reason"] == "already_configured"
    assert entry.data["tank_host"] == "aquarium.example"


async def test_dhcp_finds_old_entry_by_device_mac(hass: HomeAssistant, setup, lamp: FakeLamp):
    """Old entry (URL as unique_id): found through its device's MAC, new IP and MAC unique_id taken over."""
    assert setup.unique_id == URL_ID  # its device had no MAC yet when the entry was migrated
    reg = er.async_get(hass)
    before = {e.entity_id: e.unique_id for e in er.async_entries_for_config_entry(reg, setup.entry_id)}
    result = await discover(hass, dhcp(ip="192.0.2.20", mac="02-00-00-00-00-01"))
    assert result["reason"] == "already_configured"
    assert setup.data["tank_host"] == "192.0.2.20"
    assert setup.unique_id == MAC
    after = {e.entity_id: e.unique_id for e in er.async_entries_for_config_entry(reg, setup.entry_id)}
    assert after == before
    # From now on the MAC entry is matched directly; a second lamp is offered as new.
    assert (await discover(hass, dhcp(ip="192.0.2.20")))["reason"] == "already_configured"
    lamp.mac = "02:00:00:00:00:02"
    result = await discover(hass, dhcp(ip="192.0.2.30", mac="020000000002"))
    assert result["step_id"] == "discovery_confirm"


async def test_dhcp_old_entry_keeps_url_when_mac_taken(hass: HomeAssistant, setup, lamp: FakeLamp):
    """Another entry already uses the MAC (ignored discovery): only the address follows, no duplicate unique_id."""
    MockConfigEntry(domain=DOMAIN, source=SOURCE_IGNORE, unique_id=MAC).add_to_hass(hass)
    assert (await discover(hass, dhcp(ip="192.0.2.20")))["reason"] == "already_configured"
    assert setup.data["tank_host"] == "192.0.2.20"
    assert setup.unique_id == URL_ID


async def test_dhcp_old_entry_without_mac_same_address(hass: HomeAssistant, lamp: FakeLamp):
    """Old entry whose lamp never reported a MAC: a discovery at its address is not offered again."""
    old_entry().add_to_hass(hass)
    assert (await discover(hass, dhcp(ip="192.0.2.10")))["reason"] == "already_configured"
    assert not lamp.posts


async def test_migration_url_to_mac(hass: HomeAssistant, lamp: FakeLamp):
    """Entry of 26.11.1 with URL unique_id and a device with the lamp's MAC: unique_id becomes the MAC."""
    entry = entry_v22()
    entry.add_to_hass(hass)
    add_device(hass, entry, MAC)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == 3
    assert entry.unique_id == MAC
    reg = er.async_get(hass)
    for platform, uid in (
        ("light", "trigon_190_light"),
        ("number", f"{ENTRY_ID}_manual_color_simulation_duration"),
        ("select", "trigon_190_profile_select"),
    ):
        assert reg.async_get_entity_id(platform, DOMAIN, uid)
    assert hass.states.get("light.trigon_190_light") is not None
    await unload(hass, entry)


async def test_migration_keeps_url_when_not_safe(hass: HomeAssistant, lamp: FakeLamp):
    """No MAC, two MACs or a MAC already used by another entry: the URL stays, the entry still loads."""
    no_mac = entry_v22(entry_id="01NOMAC0000000000000000000")
    no_mac.add_to_hass(hass)
    assert mac_unique_id(hass, no_mac) is None
    two = entry_v22(unique_id="http://192.0.2.11", entry_id="01TWOMACS00000000000000000")
    two.add_to_hass(hass)
    add_device(hass, two, MAC, "02:00:00:00:00:03")
    assert mac_unique_id(hass, two) is None
    taken = entry_v22(unique_id="http://192.0.2.12", entry_id="01TAKEN0000000000000000000")
    taken.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=taken.entry_id,
        identifiers={(DOMAIN, "other")},
        connections={(CONNECTION_NETWORK_MAC, "02:00:00:00:00:04")},
    )
    MockConfigEntry(domain=DOMAIN, unique_id="02:00:00:00:00:04", data={}).add_to_hass(hass)
    assert mac_unique_id(hass, taken) is None
    assert mac_unique_id(hass, MockConfigEntry(domain=DOMAIN, unique_id=MAC)) is None  # already a MAC
    assert await hass.config_entries.async_setup(taken.entry_id)
    await hass.async_block_till_done()
    assert taken.minor_version == 3
    assert taken.unique_id == "http://192.0.2.12"
    await unload(hass, taken)


async def test_migration_ignores_split_composite_device(hass: HomeAssistant):
    """Connections copied from a pre-2026.9 composite device may belong to another entry."""
    entry = entry_v22()
    entry.add_to_hass(hass)
    device = SimpleNamespace(has_composite_identifiers=True, connections={(CONNECTION_NETWORK_MAC, MAC)})
    with patch("custom_components.juwel_helialux.device.dr.async_entries_for_config_entry", return_value=[device]):
        assert mac_unique_id(hass, entry) is None


async def test_open_discovery_cannot_replace_old_entry(hass: HomeAssistant, lamp: FakeLamp):
    """A discovery offered before the old entry knew its MAC must not create a second entry later.

    Home Assistant replaces (deletes) an entry when a new one with the same unique_id is created.
    """
    entry = entry_v22()
    entry.add_to_hass(hass)
    first = await discover(hass, dhcp(ip="192.0.2.20"))
    assert first["step_id"] == "discovery_confirm"
    add_device(hass, entry, MAC)  # the entry loaded meanwhile and its device reported the MAC
    # Confirming the open form now: the lamp is known, nothing is created.
    result = await hass.config_entries.flow.async_configure(first["flow_id"], {"tank_name": "Trigon 190"})
    assert result["reason"] == "already_configured"
    assert hass.config_entries.async_entries(DOMAIN) == [entry]


async def test_mac_takeover_closes_open_discovery(hass: HomeAssistant, lamp: FakeLamp):
    """The old entry takes over the MAC: a discovery form of the same lamp still open is closed."""
    entry = entry_v22()
    entry.add_to_hass(hass)
    assert (await discover(hass, dhcp(ip="192.0.2.20")))["step_id"] == "discovery_confirm"
    add_device(hass, entry, MAC)
    assert (await discover(hass, dhcp(ip="192.0.2.30")))["reason"] == "already_configured"
    assert entry.unique_id == MAC
    assert entry.data["tank_host"] == "192.0.2.30"
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
    await unload(hass, entry)


async def test_dhcp_prefers_mac_entry(hass: HomeAssistant, lamp: FakeLamp):
    """Old and new entry for the same lamp: the entry with the MAC as unique_id gets the new address."""
    old = entry_v22(host="192.0.2.10")
    old.add_to_hass(hass)
    add_device(hass, old, MAC)
    new = entry_v22(unique_id=MAC, host="aquarium.example", entry_id="01NEWENTRY0000000000000000")
    new.add_to_hass(hass)
    assert (await discover(hass, dhcp(ip="192.0.2.20")))["reason"] == "already_configured"
    assert old.data["tank_host"] == "192.0.2.10"
    assert old.unique_id == URL_ID


async def test_dhcp_old_device_with_two_macs_is_no_proof(hass: HomeAssistant, lamp: FakeLamp):
    """Device with the MACs of an old and a new controller: the old one showing up elsewhere is a new lamp."""
    entry = entry_v22()
    entry.add_to_hass(hass)
    add_device(hass, entry, "02:00:00:00:00:05", MAC)
    result = await discover(hass, dhcp(ip="192.0.2.20"))
    assert result["step_id"] == "discovery_confirm"
    assert entry.data["tank_host"] == "192.0.2.10"
    assert entry.unique_id == URL_ID


async def test_user_flow_finds_old_entry_by_device_mac(hass: HomeAssistant, lamp: FakeLamp):
    """Adding the lamp of an old entry by hand under a new address creates no second entry."""
    entry = entry_v22()
    entry.add_to_hass(hass)
    add_device(hass, entry, MAC)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tank_host": "192.0.2.20", "tank_name": "Trigon 190", "tank_protocol": "http"}
    )
    assert result["reason"] == "already_configured"
    assert hass.config_entries.async_entries(DOMAIN) == [entry]
