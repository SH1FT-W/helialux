<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme-title-dark.png" />
  <img src="docs/images/readme-title-light.png" alt="HeliaLux: Your aquarium light, fully local. A rendered image of an aquarium with a HeliaLux LED light bar on its holders above the tank, planted with green plants and driftwood." />
</picture>

<p>Local control for the Juwel HeliaLux SmartControl aquarium light in Home Assistant.<br/>
Robust, complete, no cloud.</p>

[![Version](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FSH1FT-W%2Fhelialux%2Fmain%2Fcustom_components%2Fjuwel_helialux%2Fmanifest.json&query=%24.version&label=version&style=flat-square&color=003A5D&labelColor=111111)](https://github.com/SH1FT-W/helialux/releases/latest)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-003A5D?style=flat-square&labelColor=111111&logo=homeassistant&logoColor=white)](https://www.home-assistant.io)
[![HACS](https://img.shields.io/badge/HACS-custom%20repository-003A5D?style=flat-square&labelColor=111111)](https://hacs.xyz)
[![IoT class](https://img.shields.io/badge/iot-local%20polling-003A5D?style=flat-square&labelColor=111111)](https://developers.home-assistant.io/docs/creating_integration_manifest/#iot-class)
[![Quality scale](https://img.shields.io/badge/quality%20scale-silver%20(self--assessed)-003A5D?style=flat-square&labelColor=111111)](custom_components/juwel_helialux/quality_scale.yaml)
[![License](https://img.shields.io/badge/license-Apache%202.0-003A5D?style=flat-square&labelColor=111111)](LICENSE)

<p><a href="https://sh1ft-w.github.io/helialux"><b>Website</b></a> &nbsp;·&nbsp; <a href="#new">New</a> &nbsp;·&nbsp; <a href="#features">Features</a> &nbsp;·&nbsp; <a href="#entities">Entities</a> &nbsp;·&nbsp; <a href="#installation">Install</a> &nbsp;·&nbsp; <a href="#migration-from-mrsleeps-integration">Migration</a> &nbsp;·&nbsp; <a href="#troubleshooting">Troubleshooting</a> &nbsp;·&nbsp; <a href="CHANGELOG.md">Changelog</a></p>

</div>

<br/>

HeliaLux controls the LED lighting of Juwel aquariums with a **HeliaLux SmartControl** over the lamp's own web server in your Wi-Fi. It was built and tested on a **Trigon 190** (SmartControl 4Ch, firmware 2.2.2, hardware 1.1C).

It replaces [MrSleeps' Juwel HeliaLux integration](https://github.com/MrSleeps/Juwel-HeliaLux-Home-Assistant-Custom-Component) and **keeps its domain `juwel_helialux` and its unique IDs**, so entities, history, device, automations and dashboards stay the same when you switch.

> [!NOTE]
> HeliaLux is an independent project. It is not affiliated with, endorsed by or sponsored by Juwel Aquarium AG & Co. KG. Juwel and HeliaLux are trademarks of Juwel Aquarium AG & Co. KG.

<br/>

<a id="new"></a>
<sub><b>JUST ARRIVED</b></sub>
## Steadier profiles, quieter logs.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme-cards-new-dark.png" />
  <img src="docs/images/readme-cards-new-light.png" alt="True to the profile (26.10.2): before the first point of a profile the value of that point applies, exactly as on the lamp. Safe profile names (26.10.2): names with characters the lamp cannot store are rejected before saving. Wind in any unit (26.10.2): clouds from weather convert knots and feet per second correctly, holding the state starts only once. Calendar versions (26.10.1): year, month and the release of that month, 26.10.2 is the second release of October 2026." />
</picture>

Every change, release by release, in the [changelog](CHANGELOG.md).

<a id="features"></a>
## Features

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme-cards-features-dark.png" />
  <img src="docs/images/readme-cards-features-light.png" alt="Every channel a slider: white, blue, green and red from 0 to 100 percent, plus the service set_channels. An RGBW light with transitions: brightness keeps the mix, transition fades in gentle steps, switching on brings back the last mix. Holds what you set: after a power cut the colour comes back, the manual colour simulation is extended before it runs out. No fight with the app: changes in the Juwel app are taken over, the daytime simulation makes Home Assistant step back. Profiles and weekly plan: get_profile and set_profile, one profile for all days or per weekday. Clouds, sun and weather: cloud strength and motion, cloud window, clouds from a weather entity, sun cycle. Acclimatization: a new tank starts dimmed and reaches full brightness after 1 to 12 weeks. Robust, with diagnostics: one request at a time, unavailable only after three misses, clock offset repair issue and diagnostics download." />
</picture>

- **Keep manual colour:** on, Home Assistant holds the colour permanently; off, the lamp's profile takes over again after the set duration (handy for a quick manual tweak).
- **Profile curve as data:** points per channel, clouds and what the profile would show right now, for charts in dashboards.
- **Repair issue:** if the lamp's clock is more than 10 minutes off, a notice appears under *Repairs*.

<a id="entities"></a>
## Entities

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme-cards-entities-dark.png" />
  <img src="docs/images/readme-cards-entities-light.png" alt="Light: light.trigon_190_light, RGBW with absolute channel values, brightness and transition. Channel numbers: white, blue, green and red from 0 to 100 percent, plus simulation durations. Switches: manual_color_simulation, manual_daytime_simulation, keep_manual, sun_cycle, acclimatization and weather_clouds. Selects and times: profil, profile_monday to _sunday, cloud_intensity, cloud_motion, cloud_from, cloud_to, sun_earliest, sun_latest. Sensors: channel values, current_profile with curve, profile_now and week, device_time and profiles. Diagnostics: reachable, clock_offset and color_simulation_remaining." />
</picture>

All IDs start with the tank name, for example `light.trigon_190_light`, and are the same as in the previous integration. Entity names are available in English and German.

<details>
<summary>All entities (for a tank named "Trigon 190")</summary>

| Entity | Meaning |
|---|---|
| `light.trigon_190_light` | The lamp (RGBW, absolute channel values, `transition`) |
| `number.trigon_190_white` / `_blue` / `_green` / `_red` | Set one channel (0 to 100 %) |
| `switch.trigon_190_manual_color_simulation` | On = Home Assistant decides the colour, off = the lamp's profile |
| `switch.trigon_190_manual_daytime_simulation` | Play the profile in fast motion from a start time |
| `select.trigon_190_profil` | Lamp profile (all days) |
| `select.trigon_190_profile_monday` … `_sunday` | Profile per weekday |
| `select.trigon_190_cloud_intensity` / `_cloud_motion` | Clouds in the active profile |
| `switch.trigon_190_keep_manual` | Keep manual colour |
| `time.trigon_190_cloud_from` / `_cloud_to` | Cloud window: clouds only in this period |
| `switch.trigon_190_sun_cycle` + `time.trigon_190_sun_earliest` / `_sun_latest` | Sun cycle: morning and evening of the profile follow sunrise and sunset, limited to earliest/latest |
| `switch.trigon_190_acclimatization` + `number.trigon_190_acclim_start` / `_acclim_weeks` | Acclimatization: the profile starts dimmed (10 to 100 %) and reaches full brightness after 1 to 12 weeks |
| `switch.trigon_190_weather_clouds` | Clouds from weather (choose the weather entity in the options) |
| `sensor.trigon_190_white` / `_blue` / `_green` / `_red` | Channel values in % |
| `sensor.trigon_190_current_profile` | Active profile; attributes `curve`, `profile_now`, `week` |
| `sensor.trigon_190_device_time`, `_profiles` | Lamp clock, number of profiles |
| `number.trigon_190_manual_color_simulation_duration` | Duration the colour simulation is started with |
| `number.trigon_190_daytime_simulation_position` / `_manual_daytime_simulation_duration` | Daytime simulation |
| `binary_sensor.trigon_190_reachable` | Diagnostic: lamp reachable (with the last error) |
| `sensor.trigon_190_clock_offset`, `_color_simulation_remaining` | Diagnostic |

</details>

### Colour values

`rgbw_color` holds the **absolute** channel values (0 to 255 equals 0 to 100 %), just as the lamp shows them:

| Call | Result |
|---|---|
| only `rgbw_color` | exactly these channel values |
| `rgbw_color` + `brightness` | colour scaled so the brightest channel has `brightness` |
| only `brightness` | current mix brighter or darker |
| no values | stays as it is; if the lamp was off, the last mix comes back |

```yaml
action: light.turn_on
target:
  entity_id: light.trigon_190_light
data:
  rgbw_color: [204, 140, 153, 255]   # red 80 %, green 55 %, blue 60 %, white 100 %
  transition: 3600                   # a one-hour sunrise
```

### Service `set_channels`

```yaml
action: juwel_helialux.set_channels
target:
  entity_id: light.trigon_190_light
data:
  white: 100
  blue: 60
  green: 55
  red: 80
  transition: 3600   # sunrise over one hour
```

Missing channels stay as they are.

### Read and write profiles

The lamp can play its daily schedule by itself (profile, up to 16 points, smooth transitions, clouds). `get_profile` reads a profile, `set_profile` writes one, in the same format:

```yaml
action: juwel_helialux.set_profile
target:
  entity_id: light.trigon_190_light
data:
  profile: My_Profile           # name or slot (P1 to P8); empty = today's active profile
  points:
    - {time: "09:00", white: 0, blue: 0, green: 0, red: 0}
    - {time: "10:00", white: 100, blue: 60, green: 55, red: 80, clouds: 2, cloud_motion: 2}
    - {time: "19:40", white: 100, blue: 60, green: 55, red: 80, clouds: 2, cloud_motion: 2}
    - {time: "20:00", white: 25, blue: 8, green: 10, red: 30}
    - {time: "21:50", white: 25, blue: 8, green: 10, red: 30}
    - {time: "22:00", white: 0, blue: 0, green: 0, red: 0}
```

If 00:00 or 23:59 are missing, the last point is continued there (usually: off). Without `clouds`/`cloud_motion` the profile keeps its cloud setting. The profile is saved permanently in the lamp; if someone is editing the same profile in the Juwel app at that moment, nothing is overwritten.

## Supported devices

- **Juwel HeliaLux SmartControl** in Wi-Fi, firmware 2.2.2 (hardware 1.1C). Tested on a Trigon 190 with four channels (white, blue, green, red). If a lamp has fewer channels, the integration only creates as many channel sliders.
- Not supported: Juwel lamps without SmartControl (without their own web server in Wi-Fi).

## Installation

### HACS (custom repository)

1. In HACS, open the three dots menu, choose **Custom repositories** and add `https://github.com/SH1FT-W/helialux` with the type **Integration**.
2. Search for **Juwel HeliaLux**, download it and restart Home Assistant.

### Manual

1. Download the [latest release](https://github.com/SH1FT-W/helialux/releases/latest).
2. Copy the folder `custom_components/juwel_helialux` into `/config/custom_components/` and restart Home Assistant.

Requires Home Assistant 2026.9 or newer.

## Setup

**Settings > Devices & services > Add integration > Juwel HeliaLux**:

| Field | Meaning |
|---|---|
| IP address | Address of the SmartControl in your Wi-Fi (best reserved in the router) |
| Aquarium name | Sets the device name and entity IDs (`Trigon 190` → `light.trigon_190_light`) |
| Protocol | `http` (default) or `https` |

Before creating the entry the integration queries the lamp; if it does not answer, "The lamp does not respond" appears. A new IP address can be entered later with **three dots > Reconfigure** (the name stays).

### Options

| Option | Meaning |
|---|---|
| Poll every … seconds | 5 to 300, default 15 |
| Weather for "clouds from weather" | Weather entity: the condition or cloud coverage sets the cloud strength, the wind the cloud motion. Written only on change and at most every 30 minutes |

## Migration from MrSleeps' integration

1. In HACS, remove "Juwel Helialux Smart Controller". Keep the integration entry.
2. Install HeliaLux (see above) and restart Home Assistant.
3. The existing entry is taken over: entity IDs, history, device and automations stay.

Three entities of the old integration remain as "no longer provided" (`sensor.<name>_combined_sensor` and two duplicate `binary_sensor.<name>_manual_*`); they can be deleted.

## Good to know

- **Do not leave the lamp's web interface open.** While it is open in a browser, it sends its own slider values every second and overwrites Home Assistant.
- **Lamp clock:** the lamp sets its clock by NTP (`ptbtime1.ptb.de`). If it has no internet access, UDP 123 has to be allowed outwards, otherwise the profile runs at the wrong time.
- **Data updates:** Home Assistant reads the state every 15 seconds (options) and the profile names every 10 minutes. Changes in the Juwel app therefore show up with up to 15 seconds delay. The lamp only handles one request at a time; all commands run one after the other.
- **Sun cycle and acclimatization** recalculate the active profile every night at 03:05 and write it to the lamp. Home Assistant keeps the original; when both are off, it is written back.
- **One lamp per entry, no automatic discovery.** Each lamp is set up by its IP address.

## Troubleshooting

- **All entities "unavailable".** The lamp did not answer three times in a row. Check the IP address in your router and enter it with **three dots > Reconfigure** if needed. Single lost requests are bridged.
- **Colour jumps back.** Usually the lamp's web interface is still open in a browser (see above).
- **Profile runs at the wrong time.** See the notice under *Repairs*: the lamp clock cannot reach its NTP server.
- **"The lamp did not accept the command".** The lamp was not reachable or refused; the reason follows the colon.
- **Diagnostics:** **Settings > Devices & services > Juwel HeliaLux > three dots > Download diagnostics**, with state, desired state and the last 20 events, without IP address and MAC address.
- **Debug log:**

  ```yaml
  logger:
    logs:
      custom_components.juwel_helialux: debug
  ```

When you open an [issue](https://github.com/SH1FT-W/helialux/issues), please attach the diagnostics file.

## Removal

1. If used: switch off **sun cycle** and **acclimatization**, so Home Assistant writes the original profile back to the lamp. Switch off the manual colour simulation so the profile runs again.
2. **Settings > Devices & services > Juwel HeliaLux > three dots > Delete.** The stored desired state is deleted with it.
3. Delete the folder `/config/custom_components/juwel_helialux` (or remove the repository in HACS) and restart Home Assistant.

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/readme-cards-how-dark.png" />
  <img src="docs/images/readme-cards-how-light.png" alt="statusvars.js: channels, mode and the lamp clock, every 15 seconds over the lamp's own web server. POST /stat: channels, colour and daytime simulation, one request after the other. /pedit and /week.html: profile points, clouds and the weekly plan, saved permanently in the lamp." />
</picture>

Everything runs locally over the lamp's web server. Home Assistant remembers what it last wanted (mode, channels, last mix, end of the colour simulation) and holds that state: if the lamp lost its colour, it is restored (at most every 2 minutes); less than 30 minutes left, the simulation is extended; changed in the app or web interface, the change is taken over; daytime simulation started on the lamp, Home Assistant steps back. Protocol notes are in [`CLAUDE.md`](CLAUDE.md) (German).

HeliaLux is a rewrite and contains no code from [MrSleeps' integration](https://github.com/MrSleeps/Juwel-HeliaLux-Home-Assistant-Custom-Component) or [moretea/pyHelialux](https://github.com/moretea/pyHelialux); thanks to both for the groundwork.

## Development

```bash
python -m pytest -q -p no:logging --cov=custom_components/juwel_helialux   # fake lamp in tests/conftest.py
uvx ruff check . && uvx ruff format --check .
uvx mypy@2.3.1 --python-executable <venv>/bin/python
python tools/pruefe-uebersetzungen.py    # strings.json against translations/*.json
```

Install the test requirements with `pip install -r requirements_test.txt`. The tests run against a simulated lamp whose answers were recorded from a real one. The same checks run on GitHub Actions for every push and pull request, plus HACS validation and hassfest. Self-assessed state of the [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/): [`quality_scale.yaml`](custom_components/juwel_helialux/quality_scale.yaml).

## License

[Apache License 2.0](LICENSE), Copyright 2026 SH1FT-W. See [`NOTICE`](NOTICE) for acknowledgements and trademarks.
