"""Sensoren: Kanalwerte, Profil, Gerätezeit und Diagnose."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .coordinator import HeliaLuxCoordinator, HeliaLuxData
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HeliaLuxSensorDescription(SensorEntityDescription):
    value: Callable[[HeliaLuxData], Any]
    attributes: Callable[[HeliaLuxData], dict[str, Any]] | None = None
    channel: int | None = None


def _level(index: int) -> Callable[[HeliaLuxData], int | None]:
    def get(data: HeliaLuxData) -> int | None:
        levels = data.status.levels
        return levels[index] if index < len(levels) else None

    return get


COLORS = ("white", "blue", "green", "red")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _curve(data: HeliaLuxData) -> dict[str, Any]:
    """Tagesverlauf des aktiven Profils (für Diagramme) und was es jetzt zeigen würde."""
    out: dict[str, Any] = {}
    profiles = data.profiles
    if profiles and len(profiles.week) == 7:
        names = profiles.names
        out["week"] = {
            day: names[i] if 0 <= i < len(names) else None for day, i in zip(WEEKDAYS, profiles.week, strict=True)
        }
    profile = data.profile
    if profile is None:
        return out
    out["curve"] = [
        {
            "time": _hhmm(t),
            **{c: ch[n] for c, ch in zip(COLORS, profile.channels, strict=False)},
            "clouds": profile.cloud_intensity[n] if n < len(profile.cloud_intensity) else 0,
        }
        for n, t in enumerate(profile.times)
    ]
    out["profile_now"] = dict(zip(COLORS, profile.levels_at(data.status.device_minutes), strict=False))
    return out


def _clock(data: HeliaLuxData) -> str:
    return _hhmm(data.status.device_minutes)


def _channel(key: str, index: int) -> HeliaLuxSensorDescription:
    return HeliaLuxSensorDescription(
        key=key,
        value=_level(index),
        channel=index,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    )


SENSORS = (
    # Reihenfolge der Kanäle an der Lampe: Weiß, Blau, Grün, Rot
    _channel("white", 0),
    _channel("blue", 1),
    _channel("green", 2),
    _channel("red", 3),
    HeliaLuxSensorDescription(key="current_profile", value=lambda d: d.status.profile or None, attributes=_curve),
    HeliaLuxSensorDescription(key="device_time", value=_clock),
    HeliaLuxSensorDescription(
        key="profiles",
        value=lambda d: len(d.profiles.names) if d.profiles else None,
        attributes=lambda d: {"available_profiles": list(d.profiles.names) if d.profiles else []},
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HeliaLuxSensorDescription(
        key="clock_offset",
        value=lambda d: d.clock_offset_min,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    HeliaLuxSensorDescription(
        key="color_simulation_remaining",
        value=lambda d: d.color_remaining_min if d.status.color_simulation else None,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    channels = coordinator.channels
    async_add_entities(HeliaLuxSensor(coordinator, d) for d in SENSORS if d.channel is None or d.channel < channels)


class HeliaLuxSensor(HeliaLuxEntity, SensorEntity):
    _platform = "sensor"
    entity_description: HeliaLuxSensorDescription

    def __init__(self, coordinator: HeliaLuxCoordinator, description: HeliaLuxSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs = self.entity_description.attributes
        return attrs(self.coordinator.data) if attrs else None
