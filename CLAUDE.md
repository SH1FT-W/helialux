# HeliaLux – Projektregeln

HA-Integration (`custom_components/juwel_helialux`, Domain `juwel_helialux`) für die Juwel HeliaLux SmartControl,
entwickelt und geprüft an einer Trigon 190 (der Test-Lampe, 4 Kanäle). Ersetzt die HACS-Integration
MrSleeps/Juwel-HeliaLux-Home-Assistant-Custom-Component **mit gleicher Domain und gleichen unique_ids** – Einbau =
Ordner tauschen, Entity-IDs, Verlauf, Gerät und Automationen bleiben. Kein Code von dort übernommen (Neubau, Dank in
`NOTICE`).

- Repo ist **öffentlich**: nichts Persönliches ins Repo (keine Namen, echten IPs/MACs/Profilnamen, Heimnetz-Details,
  lokalen Pfade). Testdaten bleiben fiktiv (192.0.2.x, 02:00:00:00:00:01, Profile wie `My_Profile`).
- README, CHANGELOG, Release-Notizen, Issue-Texte und Commit-Texte auf Englisch.
- Lokal committen ok, Push und Releases nur nach Rückfrage.

## Aufbau (`custom_components/juwel_helialux/`)
- `api.py` Lampe über HTTP (`*vars.js` lesen, `POST /stat`, `/week.html`, `/pedit`); eine Anfrage nach der anderen.
- `coordinator.py` Abfrage, `desired` (Store) = was HA zuletzt wollte; hält den Zustand gegen Neustart/Ablauf der
  Lampe, übernimmt Änderungen aus App/Weboberfläche, Übergänge, Uhrabweichung → Reparatur-Hinweis.
- `device.py` MAC-Hilfen, Migration alter Einträge (URL als unique_id → MAC), DHCP-Erkennung zieht neue IP nach.
- `weather.py` rein: Wolken nach echtem Wetter. `light.py`, `number.py`, `select.py` usw. Entitäten.
- Logo: `brand/` (offizielle Juwel-Wortmarke von juwel-aquarium.de, Quelle `assets/*.svg`).

## Warum es so ist (steht nicht im Code)
- **`setvars.js` nie lesen** (WLAN-Passwörter im Klartext).
- Profile speichern immer mit `pedit` action 30 (dauerhaft); 31 ist nur der Zwischenstand des Editors.
- Rückrufe von `async_call_later` immer `@callback`, sonst führt HA sie in einem Hilfs-Thread aus.
- Migration setzt die MAC als unique_id nur, wenn eindeutig (genau eine MAC, kein anderer Eintrag damit).
- `light.py` rgbw_color = absolute Kanalwerte wie in der alten Integration (Automationen schicken absolute Werte); nur
  brightness skaliert die Mischung; turn_on ohne Werte = letzte Mischung (alt: 100 % Weiß).
- Tagsimulation an der Lampe → HA gibt ab.
- unique_ids: `<slug>_light|_white|…`, Zahlen `<entry_id>_<key>`, Select `<slug>_profile_select`. Nicht ändern.
  Entity-IDs englisch wie alt (`entity.py` setzt sie für neue Entitäten).

## Version
Versionen über `tools/next-version` (Regeln in der globalen CLAUDE.md); Tag + Release-Titel = genau die
manifest-Version. `CHANGELOG.md` `## YY.M.N – DD.MM.YYYY`, englisch. Die Versions-Badge im README und die
Versionszeile der Projektseite (`docs/index.html`) lesen die manifest.json selbst.

## Prüfen
- `LC_ALL=en_US.UTF-8 TZ=UTC ~/Software/recall/.venv/bin/python -m pytest -q -p no:logging --cov=custom_components/juwel_helialux`
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
- README-Bilder aus `docs/readme-images.json` mit `theme/v1/readme-images/render.mjs <repo>` aus sh1ft-w.github.io:
  Titel `docs/images/readme-title-{light,dark}.webp` (2560 × 1280, Fenster zeigt `docs/images/title-shot-*.png` =
  Funktionsblock der Projektseite, 2× aufgenommen) plus `readme-title-social.png` für die GitHub-Vorschau; Karten
  als Tabellen zwischen `<!-- cards:… -->` im README, Icons in `docs/images/icons/`. Die Projektseite zeigt das
  Titelbild im Hero.
- Live: in einer Test-HA mit einer echten Lampe; danach die Lampe wieder dem eigenen Profil überlassen (manuelle
  Farbsimulation aus).
