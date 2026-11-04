# HA-Annahmen

<!-- Vorlage aus repo-vorlagen/vorlagen/ha-annahmen.md. Liegt im Repo als docs/ha-annahmen.md.
     Der HA-Beta-Bericht (repo-vorlagen/ha-beta-bericht.md) gleicht diese Liste jeden Monat mit den
     Neuerungen der HA-Beta ab. Nur festhalten, was bei einer Änderung in HA still kaputtginge. -->

Worauf sich dieses Repo bei Home Assistant verlässt. Bei jeder Änderung am Code mitpflegen.

**Getestet mit:** HA 2026.9.3 (Tests, `requirements_test.txt`) · **Mindestversion:** 2026.9.0 (`hacs.json`)

## Annahmen

| Annahme | Wo im Code | Abgesichert durch |
|---|---|---|
| Ein vor dem Hinzufügen gesetztes `self.entity_id` gilt für neu angelegte Entitäten (gleiche Entity-IDs wie bei MrSleeps, damit der Umstieg von Hand Verlauf und Automationen behält); ist die ID belegt, hängt HA `_2` an (nicht getestet) | `entity.py` | `test_integration.py::test_entity_ids` |
| Device-Registry speichert `connections` mit `CONNECTION_NETWORK_MAC` in der Schreibweise von `format_mac` (`aa:bb:cc:dd:ee:ff`); „Neu konfigurieren“ vergleicht bei Einträgen ohne MAC als unique_id die MAC der Lampe damit (meldet die Lampe keine MAC, obwohl eine bekannt ist: Abbruch) | `entity.py` `device_info`, `device.py` `device_macs()`, `config_flow.py` `async_step_reconfigure()`, `async_step_dhcp()` | `test_integration.py::test_reconfigure_other_lamp_aborts`, `::test_reconfigure_same_lamp_keeps_unique_id`, `::test_reconfigure_without_known_mac` |
| DHCP-Erkennung: `manifest.json` `dhcp` mit `macaddress` (OUI-Muster) und `registered_devices` startet `async_step_dhcp` mit `DhcpServiceInfo` (`macaddress` klein ohne Doppelpunkte, `ip`); `registered_devices` meldet auch Geräte, deren MAC als `CONNECTION_NETWORK_MAC` an einem Eintrag dieser Domain hängt | `manifest.json`, `config_flow.py` `async_step_dhcp()` | `test_discovery.py::test_dhcp_new_lamp`, `::test_dhcp_updates_ip_of_mac_entry` (Matcher selbst nur per hassfest, nicht im Test) |
| `async_update_reload_and_abort(…, unique_id=, data_updates=, reason=, reload_even_if_entry_is_unchanged=False)` darf aus dem DHCP-Schritt aufgerufen werden und lädt nur bei Änderung neu | `config_flow.py` `_update_discovered_entry()` | `test_discovery.py::test_dhcp_updates_ip_of_mac_entry`, `::test_dhcp_finds_entry_without_mac_by_device_mac` |
| Legt ein Flow einen Eintrag mit einer schon vergebenen unique_id an, ersetzt HA den bestehenden Eintrag (nur Log-Warnung). Deshalb prüft `discovery_confirm` beim Absenden erneut, und übernimmt ein Eintrag ohne MAC-unique_id die MAC, werden offene Flows dieser Lampe (`_async_in_progress(match_context={"unique_id": …})`) abgebrochen | `config_flow.py` `async_step_discovery_confirm()`, `_update_discovered_entry()` | `test_discovery.py::test_open_discovery_cannot_replace_entry_without_mac`, `::test_mac_takeover_closes_open_discovery` |
| Ein Gerät gehört seit 2026.9 genau einem Eintrag; aus Sammelgeräten aufgeteilte Geräte tragen `has_composite_identifiers`, ihre Verbindungen gelten dann nicht als Beleg für die MAC eines Eintrags ohne MAC-unique_id | `device.py` `mac_unique_id()` | `test_discovery.py::test_mac_unique_id_only_when_safe`, `::test_mac_unique_id_ignores_split_composite_device` |
| `_abort_if_unique_id_mismatch` bricht „Neu konfigurieren“ mit dem Grund `unique_id_mismatch` ab, wenn die per `async_set_unique_id` gesetzte ID nicht zum Eintrag passt (Text in `strings.json` unter `config.abort`) | `config_flow.py` `async_step_reconfigure()` | `test_integration.py::test_reconfigure_mac_entry` |
| Licht im `ColorMode.RGBW`: `rgbw_color` ist (R, G, B, W) je 0–255, `transition` kommt in `async_turn_on` an, wenn `LightEntityFeature.TRANSITION` gesetzt ist | `light.py` | `test_integration.py::test_rgbw_absolute_like_old_integration`, `::test_brightness_keeps_mix`, `::test_transition` |
| Entitätsdienste über `service.async_register_platform_entity_service` (Methodenname als `func`, `supports_response`) für Lichter dieser Plattform | `__init__.py` `async_setup()` | `test_integration.py::test_set_channels_service`, `::test_get_and_set_profile`, `::test_set_profile_errors` |
| `DataUpdateCoordinator`: `UpdateFailed` macht die Entitäten nicht verfügbar, ein zurückgegebener alter Stand hält sie verfügbar | `coordinator.py` `_async_update_data()` | `test_integration.py::test_unavailable_only_after_three_failures` |
| Rückrufe von `async_call_later` laufen im Event-Loop, wenn sie mit `@callback` markiert sind (Übergangsschritte) | `coordinator.py` | `test_integration.py::test_transition`, `::test_transition_steps_fail_quietly` |
| `get_astral_event_date(hass, "sunrise"/"sunset", Tag)` liefert die Zeiten für den Sonnenverlauf | `coordinator.py` | `test_integration.py::test_sun_cycle_and_back` |
| `Store` je Eintrag (`helialux.<entry_id>`), verzögertes Speichern, beim Löschen des Eintrags per `async_remove` entfernt | `coordinator.py`, `__init__.py` `async_remove_entry()` | `test_quality.py::test_remove_entry_deletes_store` |
| Reparatur-Hinweis über `issue_registry.async_create_issue`/`async_delete_issue` (Uhrabweichung) | `coordinator.py` | `test_integration.py::test_clock_drift_issue` |
| `loader.async_get_custom_components(hass)` liefert die Integrationen unter `custom_components` nach Domain (beim Start zwischengespeichert, kein I/O im Loop), `Integration.issue_tracker` aus deren manifest.json. `async_setup` läuft nur, wenn ein Eintrag lädt oder angelegt wird, ein Config-Flow lädt nur die Plattform `config_flow`; deshalb bricht der Flow selbst ab (`old_version_installed`) und der Reparatur-Hinweis deckt nur Altfälle mit Eintrag | `old_version.py`, `__init__.py` `_async_check_old_version()`, `config_flow.py` `_abort_if_old_version()` | `test_quality.py::test_old_version_warning`, `::test_flows_refuse_while_old_version_installed` (Loader gepatcht) |

## Fremde Integrationen

- Beliebige `weather`-Entität (in den Optionen gewählt): Zustand (`sunny`, `cloudy`, `rainy`, …) und die Attribute
  `cloud_coverage`, `wind_speed`, `wind_speed_unit` (`km/h`, `m/s`, `mph`, `kn`, `ft/s`); `weather.py`
  `clouds_for()`, `coordinator.py` `weather_clouds()`. Abgesichert durch `test_api.py::test_weather_mapping`,
  `test_integration.py::test_clouds_from_weather`.
- MrSleeps/Juwel-HeliaLux (Domain `juwel_helialux`): seit 26.11.3 keine Annahme mehr. Eigene Domain, nichts wird
  übernommen (hacs/default#13077); `test_quality.py::test_no_takeover_of_other_integrations`.

## Prüfbefehl

Gegen eine andere HA-Version: venv mit `homeassistant==<version>` und passender
`pytest-homeassistant-custom-component`, dann

```sh
python -m pytest -q -p no:logging
```
