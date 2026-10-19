"""Die Integration als Ganzes gegen die nachgebaute Lampe."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.juwel_helialux.const import DOMAIN
from custom_components.juwel_helialux.diagnostics import async_get_config_entry_diagnostics

from .conftest import ENTRY_ID, FakeLamp

LIGHT = "light.trigon_190_light"


async def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float = 15) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def turn_on(hass: HomeAssistant, **data) -> None:
    await hass.services.async_call("light", "turn_on", {"entity_id": LIGHT, **data}, blocking=True)
    await hass.async_block_till_done()


async def test_old_entry_keeps_entity_ids(hass: HomeAssistant, setup, lamp: FakeLamp):
    """Gleiche unique_ids wie die alte Integration → Automationen und Verlauf bleiben."""
    reg = er.async_get(hass)
    for entity_id, uid in (
        (LIGHT, "trigon_190_light"),
        ("switch.trigon_190_manual_color_simulation", "trigon_190_manual_color_simulation"),
        ("number.trigon_190_manual_color_simulation_duration", f"{ENTRY_ID}_manual_color_simulation_duration"),
        ("select.trigon_190_profil", "trigon_190_profile_select"),
        ("sensor.trigon_190_white", "trigon_190_white"),
    ):
        platform = entity_id.split(".")[0]
        assert reg.async_get_entity_id(platform, DOMAIN, uid), (entity_id, uid)
    assert setup.minor_version == 2
    assert setup.options == {"scan_interval": 15}
    assert "update_interval" not in setup.data
    state = hass.states.get(LIGHT)
    assert state.state == STATE_ON
    assert state.attributes["rgbw_color"] == (204, 140, 153, 255)
    assert state.attributes["brightness"] == 255
    assert hass.states.get("select.trigon_190_profil").state == "Standard_Tank"
    assert hass.states.get("binary_sensor.trigon_190_reachable").state == STATE_ON


async def test_rgbw_absolute_like_old_integration(hass: HomeAssistant, setup, lamp: FakeLamp):
    """Die Tageslicht-Automation schickt absolute Werte (Abendlicht)."""
    await turn_on(hass, rgbw_color=[77, 26, 20, 64])
    assert lamp.levels == [25, 8, 10, 30]  # W, B, G, R
    assert hass.states.get(LIGHT).attributes["rgbw_color"] == (76, 26, 20, 64)


async def test_brightness_keeps_mix(hass: HomeAssistant, setup, lamp: FakeLamp):
    """Alte Integration: nur Helligkeit → volles Weiß. Jetzt bleibt die Mischung."""
    await turn_on(hass, brightness=128)
    assert lamp.levels == [50, 30, 28, 40]
    await turn_on(hass, rgbw_color=[255, 0, 0, 0], brightness=51)
    assert lamp.levels == [0, 0, 0, 20]


async def test_toggle_restores_last_mix(hass: HomeAssistant, setup, lamp: FakeLamp):
    await hass.services.async_call("light", "turn_off", {"entity_id": LIGHT}, blocking=True)
    assert lamp.levels == [0, 0, 0, 0] and lamp.csim  # aus = alle Kanäle 0, Profil bleibt aus
    await turn_on(hass)
    assert lamp.levels == [100, 60, 55, 80]


async def test_restore_after_lamp_reboot(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await turn_on(hass, rgbw_color=[77, 26, 20, 64])
    lamp.reboot()
    await tick(hass, freezer)
    await hass.async_block_till_done()
    assert lamp.csim and lamp.levels == [25, 8, 10, 30]
    diag = await async_get_config_entry_diagnostics(hass, setup)
    assert diag["stats"]["restores"] == 1
    assert "192.0.2.10" not in str(diag)
    # Sperre: ein zweiter Neustart direkt danach wird erst nach 2 Minuten wiederhergestellt.
    lamp.reboot()
    await tick(hass, freezer)
    assert not lamp.csim
    await tick(hass, freezer, 120)
    await hass.async_block_till_done()
    assert lamp.csim


async def test_profile_mode_is_not_restored(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.trigon_190_manual_color_simulation"}, blocking=True
    )
    assert not lamp.csim
    await tick(hass, freezer)
    assert not lamp.csim
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_profil", "option": "Standard Nacht"}, blocking=True
    )
    assert lamp.week == [4] * 7
    assert hass.states.get("select.trigon_190_profil").state == "Standard Nacht"
    assert "Standard (P8)" in hass.states.get("select.trigon_190_profil").attributes["options"]


async def test_select_profile_ends_manual(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_profil", "option": "Classic"}, blocking=True
    )
    assert not lamp.csim and lamp.prof_num == 2
    await tick(hass, freezer)
    assert not lamp.csim


async def test_adopts_changes_from_app(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await turn_on(hass, rgbw_color=[255, 255, 255, 255])
    await tick(hass, freezer, 60)
    lamp.levels = [5, 5, 5, 5]  # in der App geändert
    await tick(hass, freezer)
    await hass.async_block_till_done()
    assert setup.runtime_data.desired.levels == (5, 5, 5, 5)
    assert lamp.levels == [5, 5, 5, 5]


async def test_renews_before_expiry(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await turn_on(hass, rgbw_color=[255, 0, 0, 0])
    assert lamp.ctime == 12 * 60
    posts = len(lamp.posts)
    await tick(hass, freezer, (12 * 60 - 20) * 60)
    await hass.async_block_till_done()
    assert lamp.posts[posts:][-1][1]["action"] == 14
    assert hass.states.get("sensor.trigon_190_color_simulation_remaining").state == "720"


async def test_transition(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await turn_on(hass, rgbw_color=[0, 0, 0, 0])
    await turn_on(hass, rgbw_color=[255, 0, 0, 255], transition=100)
    assert 0 < lamp.levels[0] < 100  # erster Schritt sofort
    for _ in range(55):
        await tick(hass, freezer, 2)
    assert lamp.levels == [100, 0, 0, 100]
    # Neuer Befehl bricht den laufenden Übergang ab.
    await turn_on(hass, rgbw_color=[0, 0, 0, 0], transition=60)
    await turn_on(hass, rgbw_color=[255, 255, 255, 255])
    for _ in range(35):
        await tick(hass, freezer, 2)
    assert lamp.levels == [100, 100, 100, 100]


async def test_unavailable_only_after_three_failures(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    lamp.offline = True
    await tick(hass, freezer)
    with pytest.raises(HomeAssistantError, match="did not accept"):
        await turn_on(hass, brightness=10)
    await tick(hass, freezer)
    assert hass.states.get(LIGHT).state == STATE_ON
    await tick(hass, freezer)
    assert hass.states.get(LIGHT).state == STATE_UNAVAILABLE
    reachable = hass.states.get("binary_sensor.trigon_190_reachable")
    assert reachable.state == "off" and "ClientConnectorError" in reachable.attributes["last_error"]
    lamp.offline = False
    await tick(hass, freezer)
    assert hass.states.get(LIGHT).state == STATE_ON


async def test_clock_drift_issue(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    issues = ir.async_get(hass)
    offset = int(hass.states.get("sensor.trigon_190_clock_offset").state)
    assert (abs(offset) >= 10) == bool(issues.async_get_issue(DOMAIN, f"clock_drift_{ENTRY_ID}"))
    # Uhr gestellt → Hinweis verschwindet
    from homeassistant.util import dt as dt_util

    now = dt_util.now()
    lamp.minutes = now.hour * 60 + now.minute
    await tick(hass, freezer, 1)
    now = dt_util.now()
    lamp.minutes = now.hour * 60 + now.minute
    await tick(hass, freezer, 15)
    assert issues.async_get_issue(DOMAIN, f"clock_drift_{ENTRY_ID}") is None
    lamp.minutes = (lamp.minutes + 30) % 1440
    await tick(hass, freezer)
    assert issues.async_get_issue(DOMAIN, f"clock_drift_{ENTRY_ID}") is not None


async def test_daytime_simulation_and_numbers(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.trigon_190_manual_color_simulation_duration", "value": 14},
        blocking=True,
    )
    assert setup.runtime_data.color_duration_h == 14
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.trigon_190_manual_daytime_simulation"}, blocking=True
    )
    assert lamp.tsim and not lamp.csim
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.trigon_190_daytime_simulation_position", "value": 20},
        blocking=True,
    )
    assert lamp.posts[-1][1]["ch5"] == 1200
    await tick(hass, freezer)
    assert lamp.tsim  # HA kämpft nicht gegen die Tagsimulation
    assert hass.states.get("sensor.trigon_190_clock_offset").state == "unknown"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.trigon_190_manual_daytime_simulation"}, blocking=True
    )
    assert not lamp.tsim


async def test_daytime_started_in_app_releases_control(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await turn_on(hass, rgbw_color=[255, 0, 0, 0])
    lamp.tsim, lamp.csim = True, False
    await tick(hass, freezer)
    await tick(hass, freezer, 200)
    assert not lamp.csim


async def test_unload(hass: HomeAssistant, setup, lamp: FakeLamp):
    assert await hass.config_entries.async_unload(setup.entry_id)


async def test_config_flow(hass: HomeAssistant, lamp: FakeLamp):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    lamp.offline = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tank_host": "192.0.2.10", "tank_name": "Trigon 190", "tank_protocol": "http"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    lamp.offline = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tank_host": " 192.0.2.10 ", "tank_name": "Trigon 190", "tank_protocol": "http"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "02:00:00:00:00:01"
    assert result["data"]["tank_host"] == "192.0.2.10"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tank_host": "192.0.2.10", "tank_name": "X", "tank_protocol": "http"}
    )
    assert result["reason"] == "already_configured"


async def test_options_and_reconfigure(hass: HomeAssistant, setup, lamp: FakeLamp):
    result = await hass.config_entries.options.async_init(setup.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 30})
    await hass.async_block_till_done()
    assert setup.options == {"scan_interval": 30}
    assert setup.runtime_data.update_interval == timedelta(seconds=30)
    result = await setup.start_reconfigure_flow(hass)
    lamp.offline = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tank_host": "192.0.2.20", "tank_protocol": "http"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    lamp.offline = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"tank_host": "192.0.2.20", "tank_protocol": "http"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert setup.data["tank_host"] == "192.0.2.20"


async def test_channel_sliders(hass: HomeAssistant, setup, lamp: FakeLamp):
    assert hass.states.get("number.trigon_190_red").state == "80"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.trigon_190_blue", "value": 10}, blocking=True
    )
    assert lamp.levels == [100, 10, 55, 80]
    assert hass.states.get("number.trigon_190_blue").state == "10"
    # Aus dem Profilmodus heraus startet der Regler die manuelle Farbe.
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.trigon_190_manual_color_simulation"}, blocking=True
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.trigon_190_white", "value": 0}, blocking=True
    )
    assert lamp.csim and lamp.levels[0] == 0


async def test_first_start_adopts_manual_color(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    """Nach dem Umstieg gehört die laufende manuelle Farbe sofort HA (Restzeit bekannt, Neustart wird repariert)."""
    await hass.async_block_till_done()
    assert setup.runtime_data.desired.mode == "manual"
    assert hass.states.get("sensor.trigon_190_color_simulation_remaining").state == "720"
    lamp.reboot()
    await tick(hass, freezer)
    await hass.async_block_till_done()
    assert lamp.csim and lamp.levels == [100, 60, 55, 80]


async def test_set_channels_service(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await hass.services.async_call(DOMAIN, "set_channels", {"entity_id": LIGHT, "white": 40, "red": 10}, blocking=True)
    assert lamp.levels == [40, 60, 55, 10]
    await hass.services.async_call(
        DOMAIN,
        "set_channels",
        {"entity_id": LIGHT, "white": 0, "blue": 0, "green": 0, "red": 0, "transition": 20},
        blocking=True,
    )
    for _ in range(15):
        await tick(hass, freezer, 2)
    assert lamp.levels == [0, 0, 0, 0]


async def test_week_plan(hass: HomeAssistant, setup, lamp: FakeLamp):
    assert hass.states.get("select.trigon_190_profile_monday").state == "Standard Nacht"
    assert hass.states.get("select.trigon_190_profile_tuesday").state == "Standard_Tank"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.trigon_190_profile_monday", "option": "Standard_Tank"},
        blocking=True,
    )
    assert lamp.week == [3] * 7
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_profile_sunday", "option": "Classic"}, blocking=True
    )
    assert lamp.week == [3, 3, 3, 3, 3, 3, 2]
    week = hass.states.get("sensor.trigon_190_current_profile").attributes["week"]
    assert week["sunday"] == "Classic" and week["monday"] == "Standard_Tank"


async def test_profile_curve(hass: HomeAssistant, setup, lamp: FakeLamp):
    attrs = hass.states.get("sensor.trigon_190_current_profile").attributes
    assert attrs["curve"][3] == {"time": "10:00", "white": 65, "blue": 45, "green": 35, "red": 80, "clouds": 0}
    # 18:29 liegt zwischen 18:00 (65/45/35/80) und 19:30 (30/40/15/30)
    assert attrs["profile_now"] == {"white": 54, "blue": 43, "green": 29, "red": 64}


async def test_clouds(hass: HomeAssistant, setup, lamp: FakeLamp):
    assert hass.states.get("select.trigon_190_cloud_intensity").state == "off"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_cloud_intensity", "option": "medium"}, blocking=True
    )
    p = lamp.profiles[3]
    assert p["cI"] == [2, 0, 2, 2, 2, 2, 2, 0]  # nur wo Licht brennt (07:00 dunkel, 23:59 = Tagesende)
    assert p["cM"] == [2, 0, 2, 2, 2, 2, 2, 0]  # Zug startet mittel
    assert hass.states.get("select.trigon_190_cloud_motion").state == "medium"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_cloud_motion", "option": "fast"}, blocking=True
    )
    assert p["cM"][3] == 3 and p["cI"][3] == 2
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_cloud_intensity", "option": "off"}, blocking=True
    )
    assert p["cI"] == [0] * 8 and p["cM"] == [0] * 8
    assert p["CH"][0] == [0, 0, 25, 65, 65, 30, 0, 0]  # Kanäle unangetastet
    assert hass.states.get("select.trigon_190_cloud_motion").state == "off"


async def test_keep_manual_off_lets_profile_return(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.trigon_190_keep_manual"}, blocking=True)
    await turn_on(hass, rgbw_color=[255, 0, 0, 0])
    posts = len(lamp.posts)
    await tick(hass, freezer, (12 * 60 - 20) * 60)  # kurz vor Ablauf: keine Verlängerung
    assert all(p[1].get("action") != 14 for p in lamp.posts[posts:])
    lamp.reboot()  # Laufzeit abgelaufen → Profil der Lampe
    await tick(hass, freezer)
    await tick(hass, freezer, 200)
    assert not lamp.csim
    assert setup.runtime_data.desired.mode == "auto"
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.trigon_190_keep_manual"}, blocking=True)
    assert hass.states.get("switch.trigon_190_keep_manual").state == "on"


async def test_get_and_set_profile(hass: HomeAssistant, setup, lamp: FakeLamp):
    res = await hass.services.async_call(
        DOMAIN, "get_profile", {"entity_id": LIGHT, "profile": "P8"}, blocking=True, return_response=True
    )
    assert res[LIGHT]["profile"] == "Standard" and res[LIGHT]["slot"] == "P8"
    assert res[LIGHT]["points"][3] == {
        "time": "10:00",
        "white": 65,
        "blue": 45,
        "green": 35,
        "red": 80,
        "clouds": 0,
        "cloud_motion": 0,
    }
    await hass.services.async_call(
        DOMAIN,
        "set_profile",
        {
            "entity_id": LIGHT,
            "profile": "Standard (P8)",
            "name": "My_Profile",
            "points": [
                {"time": "10:00", "white": 100, "blue": 60, "green": 55, "red": 80, "clouds": 2, "cloud_motion": 1},
                {"time": "9:00"},
                {"time": "22:00"},
            ],
        },
        blocking=True,
    )
    p = lamp.profiles[7]
    assert lamp.names[7] == "My_Profile"
    assert p["times"] == [0, 540, 600, 1320, 1439]  # sortiert, 00:00 und 23:59 ergänzt (vom letzten Punkt)
    assert p["CH"][0] == [0, 0, 100, 0, 0] and p["CH"][3] == [0, 0, 80, 0, 0]
    assert p["cI"] == [0, 0, 2, 0, 0] and p["cM"] == [0, 0, 1, 0, 0]
    assert "My_Profile" in hass.states.get("select.trigon_190_profil").attributes["options"]
    # Ohne Wolkenangaben bleibt die Wolken-Einstellung des Profils (auf allen Punkten mit Licht).
    await hass.services.async_call(
        DOMAIN,
        "set_profile",
        {"entity_id": LIGHT, "profile": "My_Profile", "points": [{"time": "10:00", "white": 50}, {"time": "20:00"}]},
        blocking=True,
    )
    assert p["times"] == [0, 600, 1200, 1439] and p["cI"] == [0, 2, 0, 0] and p["cM"] == [0, 1, 0, 0]
    # Ohne Profilangabe: das heute aktive (P4)
    await hass.services.async_call(
        DOMAIN, "set_profile", {"entity_id": LIGHT, "points": [{"time": "12:00", "white": 10}]}, blocking=True
    )
    assert lamp.profiles[3]["times"] == [0, 720, 1439]


async def test_set_profile_errors(hass: HomeAssistant, setup, lamp: FakeLamp):
    import voluptuous as vol

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_profile",
            {"entity_id": LIGHT, "profile": "Gibtsnicht", "points": [{"time": "10:00"}]},
            blocking=True,
        )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_profile",
            {"entity_id": LIGHT, "profile": "P8", "points": [{"time": "10:00"}, {"time": "10:00"}]},
            blocking=True,
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "set_profile", {"entity_id": LIGHT, "name": "a&b", "points": [{"time": "10:00"}]}, blocking=True
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "set_profile",
            {"entity_id": LIGHT, "points": [{"time": f"{h:02d}:00"} for h in range(17)]},
            blocking=True,
        )
    # Unbenannter Platz per Zahl
    assert setup.runtime_data.profile_index("8") == 7 and setup.runtime_data.profile_index("p2") == 1


MY_PROFILE = [
    {"time": "09:00"},
    {"time": "10:00", "white": 100, "blue": 60, "green": 55, "red": 80, "clouds": 2, "cloud_motion": 2},
    {"time": "19:40", "white": 100, "blue": 60, "green": 55, "red": 80, "clouds": 2, "cloud_motion": 2},
    {"time": "20:00", "white": 25, "blue": 8, "green": 10, "red": 30, "clouds": 2, "cloud_motion": 2},
    {"time": "21:50", "white": 25, "blue": 8, "green": 10, "red": 30, "clouds": 2, "cloud_motion": 2},
    {"time": "22:00"},
]


async def make_my_profile(hass: HomeAssistant, lamp: FakeLamp) -> dict:
    await hass.services.async_call(
        DOMAIN, "set_profile", {"entity_id": LIGHT, "profile": "P4", "points": MY_PROFILE}, blocking=True
    )
    await hass.async_block_till_done()
    return lamp.profiles[3]


async def test_cloud_window(hass: HomeAssistant, setup, lamp: FakeLamp):
    p = await make_my_profile(hass, lamp)
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.trigon_190_cloud_from", "time": "12:00"}, blocking=True
    )
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.trigon_190_cloud_to", "time": "17:00"}, blocking=True
    )
    await hass.async_block_till_done()
    # Zwischenpunkte 12:00 und 17:00 eingefügt, Wolken nur ab 12:00 bis 17:00
    assert p["times"] == [0, 540, 600, 720, 1020, 1180, 1200, 1310, 1320, 1439]
    assert p["cI"] == [0, 0, 0, 2, 0, 0, 0, 0, 0, 0]
    assert p["CH"][0][3] == 100  # Zwischenpunkt mit den Werten, die die Lampe dort zeigt
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_cloud_intensity", "option": "off"}, blocking=True
    )
    assert p["cI"] == [0] * 10


async def test_sun_cycle_and_back(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    p = await make_my_profile(hass, lamp)
    original = (list(p["times"]), [list(c) for c in p["CH"]])
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.trigon_190_sun_earliest", "time": "05:00"}, blocking=True
    )
    await hass.services.async_call(
        "time", "set_value", {"entity_id": "time.trigon_190_sun_latest", "time": "23:30"}, blocking=True
    )
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.trigon_190_sun_cycle"}, blocking=True)
    await hass.async_block_till_done()
    from homeassistant.helpers.sun import get_astral_event_date
    from homeassistant.util import dt as dt_util

    rise = dt_util.as_local(get_astral_event_date(hass, "sunrise", dt_util.now().date()))
    dusk = dt_util.as_local(get_astral_event_date(hass, "sunset", dt_util.now().date()))
    start, evening = rise.hour * 60 + rise.minute, dusk.hour * 60 + dusk.minute
    assert p["times"] == [0, start, start + 60, evening, evening + 20, evening + 130, evening + 140, 1439]
    assert p["CH"] == original[1]  # Form und Werte unverändert, nur verschoben
    assert p["cI"][2] == 2  # Wolken wandern mit
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.trigon_190_sun_cycle"}, blocking=True)
    await hass.async_block_till_done()
    assert p["times"] == original[0]  # zurück ins Original


async def test_acclimatization(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    p = await make_my_profile(hass, lamp)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.trigon_190_acclim_weeks", "value": 1}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.trigon_190_acclimatization"}, blocking=True
    )
    await hass.async_block_till_done()
    assert p["CH"][0][2] == 50  # Weiß am Tag: 100 % × 50 %
    assert hass.states.get("switch.trigon_190_acclimatization").attributes["factor_percent"] == 50
    for _ in range(8):
        await tick(hass, freezer, 86400)
    assert p["CH"][0][2] == 100
    assert hass.states.get("switch.trigon_190_acclimatization").state == "off"


async def test_clouds_from_weather(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    p = await make_my_profile(hass, lamp)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.trigon_190_manual_color_simulation"}, blocking=True
    )
    hass.states.async_set("weather.wetterstation", "partlycloudy", {"wind_speed": 5.5, "wind_speed_unit": "km/h"})
    result = await hass.config_entries.options.async_init(setup.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 15, "weather_entity": "weather.wetterstation"}
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.trigon_190_weather_clouds"}, blocking=True
    )
    await hass.async_block_till_done()
    assert max(p["cI"]) == 1 and max(p["cM"]) == 1
    attrs = hass.states.get("switch.trigon_190_weather_clouds").attributes
    assert attrs["clouds_from_weather"] == [1, 1]
    # Gewitter: erst nach 30 Minuten wieder schreiben
    hass.states.async_set("weather.wetterstation", "lightning-rainy", {"wind_speed": 40, "wind_speed_unit": "km/h"})
    await hass.async_block_till_done()
    assert max(p["cI"]) == 1
    await tick(hass, freezer, 31 * 60)
    await hass.async_block_till_done()
    assert max(p["cI"]) == 3 and max(p["cM"]) == 3
    # Sonne: Wolken aus
    await tick(hass, freezer, 31 * 60)
    hass.states.async_set("weather.wetterstation", "sunny", {"wind_speed": 3})
    await hass.async_block_till_done()
    assert max(p["cI"]) == 0


# --- Fehlerpfade: die Lampe antwortet nicht, nichts darf aus einer Hintergrundaufgabe fallen -------


async def test_transition_steps_fail_quietly(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    """Ein gescheiterter Schritt wird übersprungen; scheitert auch der Zielwert, gibt es eine Warnung."""
    await turn_on(hass, rgbw_color=[0, 0, 0, 0])
    with patch("custom_components.juwel_helialux.coordinator._LOGGER.warning") as warning:
        await turn_on(hass, rgbw_color=[255, 0, 0, 255], transition=20)  # 10 Schritte à 2 s
        first = list(lamp.levels)
        lamp.fail_next = 2  # ein Schritt (Schreiben + Wiederholung) geht verloren
        await tick(hass, freezer, 2)
        await tick(hass, freezer, 2)  # die Wiederholung läuft im Hintergrund erst im nächsten Zeitschritt
        assert lamp.levels == first
        await tick(hass, freezer, 2)
        assert lamp.levels != first  # der nächste Schritt kommt wieder an
        lamp.offline = True
        for _ in range(25):  # jeder Schritt braucht zwei Zeitschritte (Schreiben, Wiederholung)
            await tick(hass, freezer, 2)
        lamp.offline = False
    assert lamp.levels != [100, 0, 0, 100]
    assert warning.call_count == 1 and "Zielwert des Übergangs" in warning.call_args.args[0]


async def test_color_simulation_switch_restarts_with_last_mix(hass: HomeAssistant, setup, lamp: FakeLamp):
    await turn_on(hass, rgbw_color=[200, 100, 50, 255])
    switch = "switch.trigon_190_manual_color_simulation"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert lamp.csim is False
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await hass.async_block_till_done()
    assert lamp.csim is True and lamp.levels == [100, 20, 39, 78]  # W, B, G, R aus rgbw_color


async def test_clouds_with_sun_template(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    """Läuft der Sonnenverlauf (Vorlage gespeichert), landen Wolken in der Vorlage und im gerechneten Profil."""
    p = await make_my_profile(hass, lamp)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.trigon_190_sun_cycle"}, blocking=True)
    await hass.async_block_till_done()
    shifted = list(p["times"])
    assert shifted != [0, 540, 600, 1180, 1200, 1310, 1320, 1439]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.trigon_190_cloud_intensity", "option": "off"}, blocking=True
    )
    await hass.async_block_till_done()
    assert p["cI"] == [0] * len(p["cI"]) and p["times"] == shifted  # Sonne bleibt, Wolken weg
    assert max(setup.runtime_data.program.template["ci"]) == 0  # auch in der Vorlage
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.trigon_190_sun_cycle"}, blocking=True)
    await hass.async_block_till_done()
    assert p["cI"] == [0] * 8  # zurück ins Original, ohne Wolken


async def test_weather_and_nightly_failures_only_warn(hass: HomeAssistant, setup, lamp: FakeLamp, freezer):
    p = await make_my_profile(hass, lamp)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.trigon_190_manual_color_simulation"}, blocking=True
    )
    hass.states.async_set("weather.wetterstation", "sunny", {"wind_speed": 5, "wind_speed_unit": "km/h"})
    result = await hass.config_entries.options.async_init(setup.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 15, "weather_entity": "weather.wetterstation"}
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.trigon_190_weather_clouds"}, blocking=True
    )
    await hass.async_block_till_done()
    assert max(p["cI"]) == 0
    with patch("custom_components.juwel_helialux.coordinator._LOGGER.warning") as warning:
        await tick(hass, freezer, 31 * 60)
        lamp.fail_next = 1  # das Lesen des Profils scheitert
        hass.states.async_set("weather.wetterstation", "cloudy", {"wind_speed": 15, "wind_speed_unit": "km/h"})
        await hass.async_block_till_done()
        assert max(p["cI"]) == 0
        assert any("Wolken nach Wetter nicht gesetzt" in c.args[0] for c in warning.call_args_list)
        # Nachts mit Sonnenverlauf, Lampe nicht erreichbar
        await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.trigon_190_sun_cycle"}, blocking=True)
        await hass.async_block_till_done()
        lamp.offline = True
        await tick(hass, freezer, 86400)
        lamp.offline = False
        assert any("Profil nachts nicht neu gerechnet" in c.args[0] for c in warning.call_args_list)


async def test_maintain_scheduled_once(hass: HomeAssistant, setup):
    """Zwei Abfragen direkt nacheinander starten nur einen Halte-Lauf."""
    coordinator = setup.runtime_data
    runs: list[object] = []

    async def fake_maintain(data: object) -> None:
        runs.append(data)

    await hass.async_block_till_done()
    coordinator._maintaining = False
    with patch.object(coordinator, "_maintain", fake_maintain):
        coordinator._schedule_maintain(coordinator.data)
        coordinator._schedule_maintain(coordinator.data)
        await hass.async_block_till_done()
    assert len(runs) == 1
    coordinator._maintaining = False
