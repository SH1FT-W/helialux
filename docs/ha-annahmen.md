# HA-Annahmen

<!-- Vorlage aus repo-vorlagen/vorlagen/ha-annahmen.md. Liegt im Repo als docs/ha-annahmen.md.
     Der HA-Beta-Bericht (repo-vorlagen/ha-beta-bericht.md) gleicht diese Liste jeden Monat mit den
     Neuerungen der HA-Beta ab. Nur festhalten, was bei einer Änderung in HA still kaputtginge. -->

Worauf sich dieses Repo bei Home Assistant verlässt. Bei jeder Änderung am Code mitpflegen.

**Getestet mit:** HA 2026.9.3 (Tests, `requirements_test.txt`) · **Mindestversion:** 2026.9.0 (`hacs.json`)

## Annahmen

| Annahme | Wo im Code | Abgesichert durch |
|---|---|---|
| Einträge der alten Integration (Version 2.1) laufen beim Laden durch `async_migrate_entry`; die Entity-Registry ordnet bestehende Entitäten über die unveränderten unique_ids zu, ein vor dem Hinzufügen gesetztes `self.entity_id` gilt nur für neu angelegte Entitäten | `__init__.py` `async_migrate_entry()`, `entity.py` | `test_integration.py::test_old_entry_keeps_entity_ids` |
| Device-Registry speichert `connections` mit `CONNECTION_NETWORK_MAC` in der Schreibweise von `format_mac` (`aa:bb:cc:dd:ee:ff`); „Neu konfigurieren“ vergleicht bei alten Einträgen (URL als unique_id) die MAC der Lampe damit (meldet die Lampe keine MAC, obwohl eine bekannt ist: Abbruch) | `entity.py` `device_info`, `config_flow.py` `_device_macs()`, `async_step_reconfigure()` | `test_integration.py::test_reconfigure_other_lamp_aborts`, `::test_reconfigure_same_lamp_keeps_old_unique_id`, `::test_reconfigure_without_known_mac` |
| `_abort_if_unique_id_mismatch` bricht „Neu konfigurieren“ mit dem Grund `unique_id_mismatch` ab, wenn die per `async_set_unique_id` gesetzte ID nicht zum Eintrag passt (Text in `strings.json` unter `config.abort`) | `config_flow.py` `async_step_reconfigure()` | `test_integration.py::test_reconfigure_mac_entry` |
| Licht im `ColorMode.RGBW`: `rgbw_color` ist (R, G, B, W) je 0–255, `transition` kommt in `async_turn_on` an, wenn `LightEntityFeature.TRANSITION` gesetzt ist | `light.py` | `test_integration.py::test_rgbw_absolute_like_old_integration`, `::test_brightness_keeps_mix`, `::test_transition` |
| Entitätsdienste über `service.async_register_platform_entity_service` (Methodenname als `func`, `supports_response`) für Lichter dieser Plattform | `__init__.py` `async_setup()` | `test_integration.py::test_set_channels_service`, `::test_get_and_set_profile`, `::test_set_profile_errors` |
| `DataUpdateCoordinator`: `UpdateFailed` macht die Entitäten nicht verfügbar, ein zurückgegebener alter Stand hält sie verfügbar | `coordinator.py` `_async_update_data()` | `test_integration.py::test_unavailable_only_after_three_failures` |
| Rückrufe von `async_call_later` laufen im Event-Loop, wenn sie mit `@callback` markiert sind (Übergangsschritte) | `coordinator.py` | `test_integration.py::test_transition`, `::test_transition_steps_fail_quietly` |
| `get_astral_event_date(hass, "sunrise"/"sunset", Tag)` liefert die Zeiten für den Sonnenverlauf | `coordinator.py` | `test_integration.py::test_sun_cycle_and_back` |
| `Store` je Eintrag (`juwel_helialux.<entry_id>`), verzögertes Speichern, beim Löschen des Eintrags per `async_remove` entfernt | `coordinator.py`, `__init__.py` `async_remove_entry()` | `test_quality.py::test_remove_entry_deletes_store` |
| Reparatur-Hinweis über `issue_registry.async_create_issue`/`async_delete_issue` (Uhrabweichung) | `coordinator.py` | `test_integration.py::test_clock_drift_issue` |

## Fremde Integrationen

- Beliebige `weather`-Entität (in den Optionen gewählt): Zustand (`sunny`, `cloudy`, `rainy`, …) und die Attribute
  `cloud_coverage`, `wind_speed`, `wind_speed_unit` (`km/h`, `m/s`, `mph`, `kn`, `ft/s`); `weather.py`
  `clouds_for()`, `coordinator.py` `weather_clouds()`. Abgesichert durch `test_api.py::test_weather_mapping`,
  `test_integration.py::test_clouds_from_weather`.
- MrSleeps/Juwel-HeliaLux (die ersetzte Integration, gleiche Domain): Aufbau ihres Eintrags (Version 2.1, URL als
  unique_id, Host/Name/Protokoll auch in den Optionen, `update_interval`), ihre unique_ids und ihre Speicherdateien
  `juwel_helialux_<entry_id>_<attr>.json` für die Dauer-Regler (`coordinator.py`, einmalig übernommen; nur die
  Einträge sind getestet, die Speicherdateien nicht).

## Prüfbefehl

Gegen eine andere HA-Version: venv mit `homeassistant==<version>` und passender
`pytest-homeassistant-custom-component`, dann

```sh
python -m pytest -q -p no:logging
```
