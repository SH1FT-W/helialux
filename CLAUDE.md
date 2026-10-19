# HeliaLux – Projektregeln

HA-Integration (`custom_components/juwel_helialux`, Domain `juwel_helialux`) für die Juwel HeliaLux SmartControl,
entwickelt und geprüft an einer Trigon 190 (der Test-Lampe, 4 Kanäle). Ersetzt die HACS-Integration
MrSleeps/Juwel-HeliaLux-Home-Assistant-Custom-Component **mit gleicher Domain und gleichen unique_ids** – Einbau =
Ordner tauschen, Entity-IDs, Verlauf, Gerät und Automationen bleiben. Kein Code von dort übernommen (Neubau, Dank in
`NOTICE`).

- Repo ist **öffentlich**: nichts Persönliches ins Repo (keine Namen, echten IPs/MACs/Profilnamen, Heimnetz-Details,
  lokalen Pfade). Testdaten bleiben fiktiv.
- README, CHANGELOG, Release-Notizen, Issue-Texte und Commit-Texte auf Englisch.
- Lokal committen ok, Push und Releases nur nach Rückfrage.

## Aufbau (`custom_components/juwel_helialux/`)
- `api.py` Lampe: liest `statusvars.js`/`wpvars.js`/`devvars.js`, schreibt `POST /stat` (10 Kanäle, 12 Tagsimulation,
  14 Farbsimulation inkl. Kanäle + `ctime`) und `POST /week.html` (Profil für alle Wochentage). Kanalreihenfolge
  W, B, G, R (0–100 %). Eine Anfrage nach der anderen (Lock + 0,15 s Pause), Schreiben 1× wiederholt.
  **`setvars.js` nie lesen** (WLAN-Passwörter im Klartext). Profile speichern immer mit `pedit` action 30 (dauerhaft); 31 ist nur der Zwischenstand des Editors.
- `coordinator.py` Abfrage alle 15 s; erst nach 3 Fehlschlägen nicht verfügbar. `desired` (Store) = was HA zuletzt
  wollte: Modus manual/auto, Kanäle, letzte Einschalt-Mischung, Ablauf der Farbsimulation. Hält den Zustand:
  Lampe hat Farbe verloren (Neustart/abgelaufen) → wiederherstellen (höchstens alle 2 Min.); Restlaufzeit < 30 Min.
  → verlängern; in App/Weboberfläche geändert → übernehmen; Tagsimulation an der Lampe → HA gibt ab.
  Übergänge (`transition`) als Schritte ≥ 2 s über `async_call_later` (Rückrufe immer `@callback`!).
  Uhrabweichung (Lampenuhr vs. HA) → Reparatur-Hinweis ab 10 Min.
- `light.py` rgbw_color = absolute Kanalwerte (wie alt, Automation schickt absolute Werte); nur brightness skaliert
  die Mischung; turn_on ohne Werte = letzte Mischung (alt: 100 % Weiß).
- unique_ids: `<slug>_light|_white|…`, Zahlen `<entry_id>_<key>`, Select `<slug>_profile_select`. Nicht ändern.
  Entity-IDs englisch wie alt (`entity.py` setzt sie für neue Entitäten).
- Logo: `brand/` (offizielle Juwel-Wortmarke von juwel-aquarium.de, Quelle `assets/*.svg`).

## Version
Kalender-Schema **YY.M.N** ohne v (Jahr zweistellig, Monat ohne führende Null, N = laufende Nummer im Monat ab 1;
es zählen nur echte, veröffentlichte GitHub-Releases des Monats, auch alte X.Y.Z; bloße Tags nicht; ohne Release im Monat → .1; neuer Monat → wieder .1).
Jedes Release als GitHub-Release veröffentlichen (Tag + Release-Titel ohne v = genau die manifest-Version), sonst zählt es nicht mit.
Nächste Nummer immer aus `tools/next-version`, nie von Hand hochzählen, keine Patch-/Minor-Unterscheidung
(+ `CHANGELOG.md` `## YY.M.N – DD.MM.YYYY`, englisch). Die Versions-Badge im README und die Versionszeile der
Projektseite (`docs/index.html`) lesen die manifest.json selbst.

## Prüfen

- `python -m pytest -q -p no:logging --cov=custom_components/juwel_helialux` in einer venv mit `requirements_test.txt`
  (nachgebaute Lampe in `tests/conftest.py`, Antworten von einer echten mitgeschnitten)
- `uvx ruff check . && uvx ruff format --check .`, `uvx mypy@2.3.1 --python-executable <venv>/bin/python`
- `python tools/pruefe-uebersetzungen.py` (strings.json gegen translations/*.json)
- GitHub Actions `.github/workflows/pruefung.yml` (Vorlage repo-vorlagen/vorlagen/ci-ha-integration.yml): dasselbe bei
  Push/PR auf main, montags zusätzlich gegen die neueste HA; Abdeckungsgrenze dort 96 % (`--cov-fail-under`).
  Pakete der CI in `requirements_test.txt` (HA 2026.9.3). `.github/workflows/hacs.yml`: HACS-Validierung.
- `tools/next-version` und `tools/pruefe-uebersetzungen.py` sind byteidentische Kopien der Vorlagen.
- Testdaten sind fiktiv (192.0.2.x, 02:00:00:00:00:01, Profile wie `My_Profile`); keine echten Werte aus einem
  Heimnetz in Tests.
- hassfest: `docker run --rm -v "$PWD/custom_components:/github/workspace/custom_components" ghcr.io/home-assistant/hassfest`
- README-Bilder: Karten aus `docs/readme-images.json`, gerendert mit `theme/v1/readme-images/render.mjs <repo> cards`
  aus sh1ft-w.github.io. Das Titelbild kommt aus `docs/readme-title.html` (headless Chrome, Befehl im Kommentar dort),
  randlos mit `docs/images/stage-photo.jpg` (KI-generiertes Bild, frei verwendbar, ohne Metadaten), nicht mit render.mjs.
- Live: in einer Test-HA mit einer echten Lampe; danach die Lampe wieder dem eigenen Profil überlassen (manuelle
  Farbsimulation aus).
