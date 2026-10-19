"""Nachgebaute Lampe – antwortet wie die echte HeliaLux SmartControl (Texte vom 07.10.2026 mitgeschnitten)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.juwel_helialux.api import HeliaLuxError
from custom_components.juwel_helialux.const import DOMAIN

ENTRY_ID = "01KP8JHDEQ0K11S0CJKHTB56SM"


class FakeLamp:
    def __init__(self) -> None:
        self.levels = [100, 60, 55, 80]  # W, B, G, R
        self.csim = True
        self.tsim = False
        self.ctime = 6 * 60 + 14
        self.minutes = 18 * 60 + 29
        self.prof_num = 3
        self.week = [4, 3, 3, 3, 3, 3, 3]
        self.names = [
            "Standard",
            "Standard o. Mi.",
            "Classic",
            "Standard_Tank",
            "Standard Nacht",
            "Summer Colorado",
            "Sunny Ibiza",
            "Standard",
        ]
        self.lamp = "4Ch"
        self.offline = False
        self.editor = 0
        # Profile wie in der Lampe: Stützpunkte, Kanäle W/B/G/R, Wolken
        self.profiles = {
            i: {
                "times": [0, 420, 510, 600, 1080, 1170, 1260, 1439],
                "CH": [
                    [0, 0, 25, 65, 65, 30, 0, 0],
                    [5, 0, 18, 45, 45, 40, 15, 5],
                    [0, 0, 12, 35, 35, 15, 0, 0],
                    [0, 0, 20, 80, 80, 30, 0, 0],
                ],
                "cI": [0] * 8,
                "cM": [0] * 8,
            }
            for i in range(8)
        }
        self.fail_next = 0
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def reboot(self) -> None:
        """Strom weg und wieder da: manuelle Farbe vergessen, Profil läuft."""
        self.csim = False
        self.levels = [65, 45, 35, 80]

    def statusvars(self) -> str:
        b = ",".join(str(v) for v in self.levels)
        return (
            f"lang=0;debugMode=0;pwdWarn=0;lamp='{self.lamp}';profNum={self.prof_num};"
            f"profile='{self.names[self.prof_num]}';tsimtime={self.minutes};tsimact={int(self.tsim)};"
            f"csimact={int(self.csim)};brightness=[{b}];times=[0,0,420,510,600,1080,1170,1260,1439];"
            "CH1=[0,0,0,25,65,65,30,0,0];"
        )

    def wpvars(self) -> str:
        names = ",".join(f'"{n}"' for n in self.names)
        return f"lang=0;debugMode=0;profnames=[{names}];profsel=[{','.join(map(str, self.week))}];"

    def profeditvars(self) -> str:
        p = self.profiles[self.editor]

        def a(v):
            return "[" + ",".join(map(str, v)) + "]"

        return (
            f"lang=0;debugMode=0;lamp='{self.lamp}';live=0;profNum={self.editor};profile='{self.names[self.editor]}';"
            f"times={a(p['times'])};cM={a(p['cM'])};cI={a(p['cI'])};"
            + "".join(f"CH{i + 1}={a(ch)};" for i, ch in enumerate(p["CH"]))
        )

    def pedit(self, body: str) -> str:
        from urllib.parse import unquote

        self.posts.append(("pedit", {"body": body}))
        fields = dict(part.split("=", 1) for part in unquote(body).split("&"))
        assert fields["action"] == "30"
        self.names[self.editor] = fields["PNAME"]

        def arr(key):
            return [int(x) for x in fields[key].strip("[]").split(",")]

        p = self.profiles[self.editor]
        p["times"] = arr("TIMES")
        p["CH"] = [arr(f"CH{i}") for i in range(1, 5)]
        p["cI"], p["cM"] = arr("CINT"), arr("CMOT")
        return json.dumps({"A": {"action": "31"}, "C": {"no": 4, "ch": self.levels}})

    @staticmethod
    def devvars() -> str:
        return (
            "debugMode=0;updSer='';lang=0;wlan=1;"
            "info=['HeliaLux SmartControl','V1.1C','V2.2.2','192.0.2.10','02:00:00:00:00:01'];"
        )

    def reply(self, action: Any) -> str:
        h, m = divmod(self.ctime, 60)
        return json.dumps(
            {
                "A": {"action": str(action)},
                "S": {
                    "dtime": str(self.minutes),
                    "stime": self.minutes,
                    "tswi": "true" if self.tsim else "",
                    "cswi": "true" if self.csim else "",
                    "ttime": "01:00",
                    "ctime": f"{h:02d}:{m:02d}",
                },
                "C": {"no": 4, "ch": self.levels},
            }
        )

    async def request(self, method: str, path: str, data: dict[str, Any] | None = None) -> str:
        if self.offline:
            raise HeliaLuxError(f"{path}: ClientConnectorError")
        if self.fail_next:
            self.fail_next -= 1
            raise HeliaLuxError(f"{path}: TimeoutError")
        if method == "GET":
            return {
                "statusvars.js": self.statusvars,
                "wpvars.js": self.wpvars,
                "devvars.js": self.devvars,
                "profeditvars.js": self.profeditvars,
            }[path]()
        if path == "pedit":
            return self.pedit(str(data))
        data = data or {}
        if path == "profedit.html":
            self.editor = int(data["profNum"])
            return "<html></html>"

        self.posts.append((path, dict(data)))
        if path == "week.html":
            self.week = [int(data[f"s{d}"].split(" | ")[0][1:]) - 1 for d in range(7)]
            self.prof_num = self.week[2]  # Testtag ist ein Mittwoch
            return "<html></html>"
        action = int(data["action"])
        if action == 14:
            self.csim = data["cswi"] == "true"
            if self.csim:
                self.tsim = False
                h, m = data["ctime"].split(":")
                self.ctime = int(h) * 60 + int(m)
        if action == 12:
            self.tsim = data["tswi"] == "true"
            self.csim = False
        if self.csim and "ch1" in data:
            self.levels = [int(data[f"ch{i}"]) for i in range(1, 5)]
        return self.reply(action)


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations, hass: HomeAssistant):
    hass.config.language = "de"


@pytest.fixture(autouse=True)
def no_waits():
    """Pausen zwischen Anfragen kosten im Test nur Zeit (und hängen bei eingefrorener Uhr)."""
    with (
        patch("custom_components.juwel_helialux.api.MIN_REQUEST_GAP", 0),
        patch("custom_components.juwel_helialux.api.RETRY_DELAY", 0),
    ):
        yield


@pytest.fixture
def lamp():
    fake = FakeLamp()
    with patch("custom_components.juwel_helialux.api.HeliaLuxClient._request", side_effect=fake.request):
        yield fake


def old_entry(**options: Any) -> MockConfigEntry:
    """So liegt der Eintrag der alten Integration in einer bestehenden Installation."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        title="Trigon 190",
        version=2,
        minor_version=1,
        unique_id="http://192.0.2.10",
        data={"tank_host": "192.0.2.10", "tank_name": "Trigon 190", "tank_protocol": "http", "update_interval": 1},
        options=options
        or {"tank_protocol": "http", "tank_host": "192.0.2.10", "tank_name": "Trigon 190", "update_interval": 1},
    )


@pytest.fixture
async def setup(hass: HomeAssistant, lamp: FakeLamp):
    entry = old_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    if entry.state.recoverable:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
