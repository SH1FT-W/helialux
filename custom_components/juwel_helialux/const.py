"""Konstanten der Juwel-HeliaLux-Integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "juwel_helialux"

# Schlüssel im Konfigurationseintrag – unverändert von der alten Integration übernommen,
# damit der bestehende Eintrag ohne Neueinrichtung weiterläuft.
CONF_TANK_HOST: Final = "tank_host"
CONF_TANK_NAME: Final = "tank_name"
CONF_TANK_PROTOCOL: Final = "tank_protocol"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_WEATHER: Final = "weather_entity"
WEATHER_MIN_GAP: Final = timedelta(minutes=30)  # Wolken nach Wetter: höchstens so oft ins Profil schreiben

DEFAULT_SCAN_INTERVAL: Final = 15  # Sekunden
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

PROFILE_REFRESH: Final = timedelta(minutes=10)
# So viele Abfragen dürfen hintereinander scheitern, bevor die Lampe als nicht erreichbar gilt.
# Der Webserver der Lampe verschluckt gelegentlich eine Anfrage.
FAILURES_BEFORE_UNAVAILABLE: Final = 3

# Manuelle Farbsimulation: Laufzeit, mit der sie gestartet wird, und ab welcher Restzeit sie verlängert wird.
DEFAULT_COLOR_DURATION_H: Final = 12.0
RENEW_BELOW_MIN: Final = 30

# Ab dieser Abweichung der Lampenuhr gibt es einen Reparatur-Hinweis.
CLOCK_DRIFT_ISSUE_MIN: Final = 10

STORAGE_VERSION: Final = 1

MAX_PROFILE_POINTS: Final = 16  # mehr Stützpunkte nimmt der Editor der Lampe nicht an
MAX_PROFILE_NAME: Final = 16
