# Changelog

## 26.11.3 – 04.11.2026

- **Own domain `helialux`** (was `juwel_helialux`, the domain of MrSleeps' integration). HeliaLux can now be
  installed next to it and no longer takes over its entries, unique IDs or stored values.
- **Breaking:** existing installations of HeliaLux are not moved over automatically. The update installs into the
  new folder `custom_components/helialux` and leaves `custom_components/juwel_helialux` in place, so the old entry
  keeps running: switch off sun cycle and acclimatization, delete the old entry, delete the old folder by hand,
  restart and set the lamp up again with the same aquarium name. Entity IDs and history stay; device automations,
  area, names and labels are set again. While the old version is still installed, setting up a lamp is refused and a repair notice explains the steps.
- Actions are now `helialux.set_channels`, `helialux.get_profile` and `helialux.set_profile`.
- unique_ids and the device identifier are based on the entry instead of the aquarium name, so two lamps with the
  same name no longer collide. Steps in the README under "Moving over".

## 26.11.2 – 02.11.2026

- **DHCP discovery:** Home Assistant recognises the lamp by its MAC address (prefix registered to JUWEL Aquarium)
  and offers it under "Discovered"; only the aquarium name is asked for. A lamp that is already set up is not
  offered again.
- **New IP address picked up by itself:** when a known lamp shows up under a new address, its entry is updated and
  reloaded. Entries taken over from the old integration (lamp URL as unique_id) are found through the MAC of their
  device. Addresses entered as host names stay as they are.
- Entries with the lamp URL as unique_id switch to the lamp's MAC address, when that is unambiguous (the device
  reported exactly one MAC and no other entry uses it). Entity IDs, unique_ids of the entities, history and device
  stay unchanged.

## 26.11.1 – 02.11.2026

- "Reconfigure" only accepts the lamp that belongs to the entry: another HeliaLux lamp at the new address is
  rejected instead of taking the entry over. Entries created by this integration compare the MAC (unique_id),
  entries taken over from the old integration (lamp URL as unique_id) compare with the MAC of their device.
- `docs/ha-annahmen.md`: what the integration relies on in Home Assistant and which test covers it.
- Prepared for public release: Apache 2.0 license and NOTICE, English README with pictures in the project theme,
  project website (`docs/index.html`), issue template, HACS validation workflow, this changelog.
- Tests, examples and service descriptions use fictitious addresses, MAC and profile names.

## 26.10.2 – 19.10.2026

- Clouds from weather: wind speed in knots and feet per second is now converted correctly.
- "Hold state" starts only one run even for two polls in quick succession, instead of addressing the lamp twice.
- Quieter log: losing the manual colour is logged as a single warning instead of twice; the other diagnostic log
  entries use fitting log levels.
- **Fix:** Before the first point of a profile, channel values were extrapolated incorrectly. The value of the first
  point now applies there, as on the lamp.
- **Fix:** Profile names with characters the lamp cannot store (`& = [ ] ;` and quotes) are now also rejected when
  saving, instead of mangling the profile on the lamp.
- **Fix:** Unexpected responses from the lamp (broken weekly schedule, unusual reply when switching) no longer cause an
  unclear error but are treated as "unreadable".
- Tooling: GitHub checks (ruff, mypy, translations, pytest with a coverage threshold, hassfest, weekly against the
  latest Home Assistant), `tools/pruefe-uebersetzungen.py` and `tools/next-version` from the shared template.

## 26.10.1 – 16.10.2026

- **New version numbers:** From now on the version counts **year.month.number of the release in that month**:
  `26.10.1` is the first release in October 2026, next month starts again at `.1` (for example `26.11.1`). The jump
  from `1.0.1` to `26.10.1` is intentional: Home Assistant recognises `26.10.1` as newer, and the update shows up as
  usual. No other changes.

## 1.0.1 – 13.10.2026

- Checked against the Integration Quality Scale (self-assessed silver, see `quality_scale.yaml`).
- Diagnostics also hide the IP address in error texts and events.
- Deleting the entry also removes the stored desired state.
- Type checking with `mypy --strict`, code owner `@SH1FT-W`.
- README: all entities, setup and options, supported devices, data updates, troubleshooting, removal.

## 1.0.0 – 07.10.2026

- First version: a rewrite replacing MrSleeps' Juwel HeliaLux integration with the same domain and the same unique
  IDs (entity IDs, history, device and automations stay).
- Light as an RGBW lamp with absolute channel values, real transitions, switching on brings back the last mix.
- A slider per channel (white, blue, green, red, 0 to 100 %); on the first start a running manual colour is taken over.
- Holds what Home Assistant set: restores the colour after a power cut or lamp restart, extends the manual colour
  simulation before it runs out, takes over changes made in the Juwel app, steps back when the daytime simulation runs.
- Service `set_channels`, services `get_profile` and `set_profile` (profiles saved permanently in the lamp).
- Profile for all days or per weekday, profile curve as attributes, cloud intensity and motion.
- Cloud window, sun cycle (morning and evening follow sunrise and sunset), acclimatization over weeks, clouds from a
  weather entity.
- Diagnostics: reachable, lamp clock offset with a repair issue from 10 minutes, remaining colour simulation time,
  diagnostics download.
