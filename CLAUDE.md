# HeliaLux – Projektregeln

HA-Integration (`custom_components/helialux`, Domain `helialux`) für die Juwel HeliaLux SmartControl,
entwickelt und geprüft an einer Trigon 190 (der Test-Lampe, 4 Kanäle). Alternative zur Marketplace-Integration
MrSleeps/Juwel-HeliaLux-Home-Assistant-Custom-Component (Domain `juwel_helialux`). Bis 26.11.2 hatten wir deren
Domain und übernahmen ihre Einträge; Frenck hat das im Marketplace-Review abgelehnt (hacs/default#13077), seit
26.11.3 eigene Domain und **nichts mehr übernehmen** (keine fremden Einträge, Speicherdateien oder unique_ids).
Das Update lässt den alten Ordner `juwel_helialux` liegen; `__init__.py` `_async_check_old_version` meldet das per
Reparatur-Hinweis (nur unsere Altversion, erkannt am issue_tracker).
Umstieg nur von Hand (README „Moving over“). Kein Code von dort übernommen (Neubau, Dank in `NOTICE`).

- Repo ist **öffentlich**: nichts Persönliches ins Repo (keine Namen, echten IPs/MACs/Profilnamen, Heimnetz-Details,
  lokalen Pfade). Testdaten bleiben fiktiv (192.0.2.x, 02:00:00:00:00:01, Profile wie `My_Profile`).
- README, CHANGELOG, Release-Notizen, Issue-Texte und Commit-Texte auf Englisch.
- Lokal committen ok, Push und Releases nur nach Rückfrage.

## Aufbau (`custom_components/helialux/`)
- `api.py` Lampe über HTTP (`*vars.js` lesen, `POST /stat`, `/week.html`, `/pedit`); eine Anfrage nach der anderen.
- `coordinator.py` Abfrage, `desired` (Store) = was HA zuletzt wollte; hält den Zustand gegen Neustart/Ablauf der
  Lampe, übernimmt Änderungen aus App/Weboberfläche, Übergänge, Uhrabweichung → Reparatur-Hinweis.
- `device.py` MAC-Hilfen: Einträge ohne MAC als unique_id (Lampe meldete beim Einrichten keine) bekommen sie, wenn eindeutig; DHCP-Erkennung zieht neue IP nach.
- `weather.py` rein: Wolken nach echtem Wetter. `light.py`, `number.py`, `select.py` usw. Entitäten.
- Logo: `brand/` (offizielle Juwel-Wortmarke von juwel-aquarium.de, Quelle `assets/*.svg`).

## Warum es so ist (steht nicht im Code)
- **`setvars.js` nie lesen** (WLAN-Passwörter im Klartext).
- Profile speichern immer mit `pedit` action 30 (dauerhaft); 31 ist nur der Zwischenstand des Editors.
- Rückrufe von `async_call_later` immer `@callback`, sonst führt HA sie in einem Hilfs-Thread aus.
- Die MAC wird nur dann unique_id, wenn eindeutig (genau eine MAC, kein anderer Eintrag damit).
- `light.py` rgbw_color = absolute Kanalwerte wie bei MrSleeps (Automationen schicken absolute Werte); nur
  brightness skaliert die Mischung; turn_on ohne Werte = letzte Mischung (alt: 100 % Weiß).
- Tagsimulation an der Lampe → HA gibt ab.
- unique_ids seit 26.11.3 alle `<entry_id>_<key>` (Licht `_light`, Select `_profile_select`), Geräte-Identifier
  `(helialux, entry_id)`. Nicht ändern.
  Entity-IDs englisch wie bei MrSleeps, damit der Umstieg von Hand Verlauf und Automationen behält (`entity.py` setzt sie für neue Entitäten).

## Version
Versionen über `tools/next-version` (Regeln in der globalen CLAUDE.md); Tag + Release-Titel = genau die
manifest-Version. `CHANGELOG.md` `## YY.M.N – DD.MM.YYYY`, englisch. Die Versions-Badge im README und die
Versionszeile der Projektseite (`docs/index.html`) lesen die manifest.json selbst.

## Prüfen
- `LC_ALL=en_US.UTF-8 TZ=UTC ~/Software/recall/.venv/bin/python -m pytest -q -p no:logging --cov=custom_components/helialux`
  (oder eine venv mit `requirements_test.txt`; nachgebaute Lampe in `tests/conftest.py`, Antworten von einer echten
  mitgeschnitten)
- `uvx ruff@0.16.9 check . && uvx ruff@0.16.9 format --check .`, `uvx mypy@2.3.1 --python-executable <venv>/bin/python`
  (dieselben Versionen wie in der CI)
- `python tools/pruefe-uebersetzungen.py` (strings.json gegen translations/*.json)
- hassfest: `docker run --rm -v "$PWD/custom_components:/github/workspace/custom_components" ghcr.io/home-assistant/hassfest`
- GitHub Actions `.github/workflows/pruefung.yml` (Vorlage repo-vorlagen/vorlagen/ci-ha-integration.yml): dasselbe bei
  Push/PR auf main, montags zusätzlich gegen die neueste HA; Abdeckungsgrenze 96 % (`--cov-fail-under`).
  Pakete der CI in `requirements_test.txt` (HA 2026.9.3). `.github/workflows/hacs.yml`: HACS-Validierung.
- `tools/next-version` und `tools/pruefe-uebersetzungen.py` sind byteidentische Kopien der Vorlagen.
- README-Bilder aus `docs/readme-images.json` mit `theme/v2/readme-images/render.mjs <repo>` aus sh1ft-w.github.io:
  Titel-Banner `docs/images/readme-title-{light,dark}.webp` (2560 × 880) plus `readme-title-social.png` (1280 × 640) für die
  GitHub-Vorschau, aus `title.name`, `title.line` und drei `title.lanes`. README- und Seitenaufbau nach
  `repo-vorlagen/readme-muster.md` (Design v2: Hero mit den drei Bahnen, kein Titelbild im Hero).
- Live: in einer Test-HA mit einer echten Lampe; danach die Lampe wieder dem eigenen Profil überlassen (manuelle
  Farbsimulation aus).
