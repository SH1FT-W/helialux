"""Wolken nach echtem Wetter: Wetterzustand → Wolkenstärke, Wind → Wolkenzug (je 0–3).

Rein, ohne Home Assistant – damit die Zuordnung einfach zu testen ist.
"""

from __future__ import annotations

from typing import Any

# Wetterzustände von Home Assistant → Wolkenstärke
_INTENSITY = {
    "sunny": 0,
    "clear-night": 0,
    "windy": 0,
    "partlycloudy": 1,
    "cloudy": 2,
    "windy-variant": 2,
    "fog": 3,
    "rainy": 3,
    "pouring": 3,
    "snowy": 3,
    "snowy-rainy": 3,
    "hail": 3,
    "lightning": 3,
    "lightning-rainy": 3,
    "exceptional": 3,
}


def clouds_for(condition: str | None, attributes: dict[str, Any]) -> tuple[int, int] | None:
    """(Stärke, Zug) für die Lampe; None = Wetter unbekannt (nichts ändern)."""
    coverage = attributes.get("cloud_coverage")
    if isinstance(coverage, int | float):
        intensity = 0 if coverage < 20 else 1 if coverage < 50 else 2 if coverage < 85 else 3
        if condition in ("rainy", "pouring", "lightning", "lightning-rainy", "hail"):
            intensity = 3
    elif condition in _INTENSITY:
        intensity = _INTENSITY[condition]
    else:
        return None
    if intensity == 0:
        return 0, 0
    wind = attributes.get("wind_speed")
    if not isinstance(wind, int | float):
        return intensity, 2
    # Grenzen in km/h; andere Einheiten der Wetter-Integrationen umrechnen (Beaufort gibt es nicht als Zahl).
    unit = attributes.get("wind_speed_unit")
    if unit == "m/s":
        wind *= 3.6
    elif unit == "mph":
        wind *= 1.609
    elif unit == "kn":
        wind *= 1.852
    elif unit == "ft/s":
        wind *= 1.097
    motion = 1 if wind < 10 else 2 if wind < 25 else 3
    return intensity, motion
