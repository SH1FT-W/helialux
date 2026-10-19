"""Lesen der Lampen-Dateien und Befehle an /stat."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.juwel_helialux.api import (
    HeliaLuxClient,
    HeliaLuxError,
    hhmm,
    parse_device,
    parse_profiles,
    parse_reply,
    parse_status,
)

from .conftest import FakeLamp


def test_parse_real_files():
    lamp = FakeLamp()
    status = parse_status(lamp.statusvars())
    assert status.levels == (100, 60, 55, 80)
    assert status.color_simulation and not status.daytime_simulation
    assert (status.profile, status.profile_index, status.device_minutes, status.channels) == (
        "Standard_Tank",
        3,
        1109,
        4,
    )
    profiles = parse_profiles(lamp.wpvars())
    assert profiles.names[3] == "Standard_Tank" and profiles.week == (4, 3, 3, 3, 3, 3, 3)
    device = parse_device(lamp.devvars())
    assert (device.model, device.hardware, device.firmware, device.mac) == (
        "HeliaLux SmartControl",
        "1.1C",
        "2.2.2",
        "02:00:00:00:00:01",
    )


def test_parse_two_channel_lamp():
    lamp = FakeLamp()
    lamp.lamp = "2Ch"
    assert parse_status(lamp.statusvars()).levels == (100, 60)


@pytest.mark.parametrize("text", ["", "lamp='4Ch';", "<html>Fehlerseite</html>"])
def test_parse_broken_status(text):
    with pytest.raises(HeliaLuxError):
        parse_status(text)


def test_parse_broken_profiles_and_device():
    with pytest.raises(HeliaLuxError):
        parse_profiles("lang=0;")
    with pytest.raises(HeliaLuxError):
        parse_device("lang=0;")
    with pytest.raises(HeliaLuxError, match="Wochenplan"):
        parse_profiles("profnames=['A','B'];profsel=[0,'x'];")


def test_parse_reply():
    reply = parse_reply(FakeLamp().reply(10))
    assert reply.color_simulation is True and reply.daytime_simulation is False
    assert reply.color_remaining_min == 374 and reply.levels == (100, 60, 55, 80)
    assert parse_reply("kein json") == parse_reply("{}")
    empty = parse_reply("{}")
    # Kaputte, aber gültige JSON-Antworten: nichts bekannt, kein Absturz
    for text in ("[]", '{"S": [1]}', '{"C": {"ch": ["x"]}}', '{"C": {"ch": [1], "no": "zwei"}}'):
        assert parse_reply(text) == empty


def test_hhmm_limits():
    assert hhmm(0) == "00:01"
    assert hhmm(14 * 60) == "14:00"
    assert hhmm(24 * 60) == "23:59"


async def test_set_levels_starts_simulation_and_retries():
    client = HeliaLuxClient(AsyncMock(), "1.2.3.4")
    lamp = FakeLamp()
    lamp.fail_next = 1
    client._request = lamp.request  # type: ignore[method-assign]
    reply = await client.set_levels((10, 20, 30, 40), 14 * 60)
    assert lamp.posts[-1] == (
        "stat",
        {"action": 14, "cswi": "true", "ctime": "14:00", "tswi": "false", "ch1": 10, "ch2": 20, "ch3": 30, "ch4": 40},
    )
    assert reply.levels == (10, 20, 30, 40)
    await client.set_levels((1, 2, 3, 4))
    assert lamp.posts[-1][1]["action"] == 10


async def test_week_profile_post():
    client = HeliaLuxClient(AsyncMock(), "1.2.3.4")
    lamp = FakeLamp()
    client._request = lamp.request  # type: ignore[method-assign]
    await client.set_week_profile(4, tuple(lamp.names))
    assert lamp.posts[-1] == ("week.html", {"key": "BU", **{f"s{d}": "P5 | Standard Nacht" for d in range(7)}})


async def test_real_http(hass, aioclient_mock):
    """Der echte HTTP-Weg: GET/POST, Fehlercodes, Zeitüberschreitung."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    lamp = FakeLamp()
    aioclient_mock.get("http://1.2.3.4/statusvars.js", text=lamp.statusvars())
    aioclient_mock.get("http://1.2.3.4/wpvars.js", status=500)
    aioclient_mock.get("http://1.2.3.4/devvars.js", exc=TimeoutError())
    aioclient_mock.post("http://1.2.3.4/stat", text=lamp.reply(10))
    client = HeliaLuxClient(async_get_clientsession(hass), "1.2.3.4")
    assert (await client.status()).levels == (100, 60, 55, 80)
    with pytest.raises(HeliaLuxError, match="HTTP 500"):
        await client.profiles()
    with pytest.raises(HeliaLuxError, match="TimeoutError"):
        await client.device()
    assert (await client.stop_color_simulation()).color_simulation is True
    assert aioclient_mock.mock_calls[-1][2] == {"action": 14, "cswi": "false"}


def test_profile_roundtrip_and_body():
    from urllib.parse import unquote

    from custom_components.juwel_helialux.api import parse_profile, profile_body

    lamp = FakeLamp()
    lamp.editor = 1
    profile = parse_profile(lamp.profeditvars())
    assert profile.name == "Standard o. Mi." and profile.index == 1 and len(profile.channels) == 4
    body = profile_body(profile)
    assert "%20" in body and "+" not in body and "%5B" in body  # wie encodeURI im Editor
    assert unquote(body).startswith("action=30&PNAME=Standard o. Mi.&TIMES=[0,420,")
    assert profile.levels_at(0) == (0, 5, 0, 0) and profile.levels_at(1439) == (0, 5, 0, 0)
    assert profile.levels_at(600) == (65, 45, 35, 80)


def test_levels_before_first_point_and_bad_name():
    from custom_components.juwel_helialux.api import HeliaLuxProfile, profile_body

    # Profil beginnt erst um 07:00: davor gilt der erste Punkt, nichts wird rückwärts extrapoliert
    profile = HeliaLuxProfile(0, "Spät", (420, 480, 1439), ((10, 50, 0), (20, 60, 0)), (0, 0, 0), (0, 0, 0))
    assert profile.levels_at(0) == (10, 20) and profile.levels_at(419) == (10, 20)
    assert profile.levels_at(450) == (30, 40) and profile.levels_at(1500) == (0, 0)
    # Name mit Trennzeichen des Speicherformats: nie roh in den Body
    for bad in ("a&b", "x=y", "P[1]", "zu lang 123456789"):
        with pytest.raises(HeliaLuxError, match="Profilname"):
            profile_body(HeliaLuxProfile(0, bad, (0, 1439), ((0, 0),), (0, 0), (0, 0)))
    assert "PNAME=Standard%20o.%20Mi." in profile_body(HeliaLuxProfile(0, "Standard o. Mi.", (0,), ((0,),), (0,), (0,)))


def test_parse_profile_broken():
    from custom_components.juwel_helialux.api import parse_profile

    with pytest.raises(HeliaLuxError):
        parse_profile("profNum=0;times=[0,1];CH1=[1];")


async def test_profile_guards():
    lamp = FakeLamp()
    client = HeliaLuxClient(AsyncMock(), "1.2.3.4")
    client._request = lamp.request  # type: ignore[method-assign]
    profile = await client.profile(5)
    assert profile.index == 5
    lamp.profiles[5]["times"] = [0, 1439] + [1439] * 6  # in der App geändert
    with pytest.raises(HeliaLuxError, match="geändert"):
        await client.save_profile(profile)
    real = lamp.profeditvars
    lamp.profeditvars = lambda: real().replace("profNum=6", "profNum=0")  # Editor zeigt ein anderes Profil
    with pytest.raises(HeliaLuxError, match="statt"):
        await client.profile(6)


def test_weather_mapping():
    from custom_components.juwel_helialux.weather import clouds_for

    assert clouds_for("sunny", {"wind_speed": 40}) == (0, 0)
    assert clouds_for("partlycloudy", {"wind_speed": 5.5, "wind_speed_unit": "km/h"}) == (1, 1)
    assert clouds_for("cloudy", {"wind_speed": 15}) == (2, 2)
    assert clouds_for("lightning-rainy", {"wind_speed": 10, "wind_speed_unit": "m/s"}) == (3, 3)  # 36 km/h
    assert clouds_for("cloudy", {}) == (2, 2)
    assert clouds_for("rainy", {"cloud_coverage": 30}) == (3, 2)
    assert clouds_for("cloudy", {"cloud_coverage": 10}) == (0, 0)
    assert clouds_for("cloudy", {"cloud_coverage": 60, "wind_speed": 20, "wind_speed_unit": "mph"}) == (2, 3)
    assert clouds_for("unavailable", {}) is None
    # weitere Einheiten der Wetter-Integrationen: Knoten und Fuß pro Sekunde
    assert clouds_for("cloudy", {"wind_speed": 6, "wind_speed_unit": "kn"}) == (2, 2)  # 11 km/h
    assert clouds_for("cloudy", {"wind_speed": 4, "wind_speed_unit": "kn"}) == (2, 1)  # 7 km/h
    assert clouds_for("cloudy", {"wind_speed": 7, "wind_speed_unit": "ft/s"}) == (2, 1)  # 7,7 km/h
    assert clouds_for("cloudy", {"wind_speed": 25, "wind_speed_unit": "ft/s"}) == (2, 3)  # 27 km/h
    assert clouds_for("cloudy", {"wind_speed": 3, "wind_speed_unit": "Beaufort"}) == (2, 1)  # unbekannt: wie km/h
