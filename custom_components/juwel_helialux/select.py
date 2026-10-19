"""Profil der Lampe (alle Tage oder je Wochentag) und Wolken im heute aktiven Profil."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeliaLuxConfigEntry
from .coordinator import HeliaLuxCoordinator
from .entity import HeliaLuxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: HeliaLuxConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ProfileSelect(coordinator, "profile", f"{coordinator.slug}_profile_select", "profil"),
            *(WeekdaySelect(coordinator, day, name) for day, name in enumerate(WEEKDAYS)),
            CloudSelect(coordinator, "cloud_intensity", CLOUD_INTENSITY),
            CloudSelect(coordinator, "cloud_motion", CLOUD_MOTION),
        ]
    )


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
CLOUD_INTENSITY = ("off", "light", "medium", "strong")
CLOUD_MOTION = ("off", "slow", "medium", "fast")


def option_names(names: tuple[str, ...]) -> list[str]:
    """Doppelte Profilnamen (die Lampe hat ab Werk zweimal „Standard“) mit P-Nummer unterscheiden."""
    return [f"{n} (P{i + 1})" if names.count(n) > 1 and names.index(n) != i else n for i, n in enumerate(names)]


class ProfileSelect(HeliaLuxEntity, SelectEntity):
    _platform = "select"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def options(self) -> list[str]:
        profiles = self.coordinator.data.profiles
        return option_names(profiles.names) if profiles else []

    @property
    def current_option(self) -> str | None:
        index = self.coordinator.data.status.profile_index
        options = self.options
        return options[index] if 0 <= index < len(options) else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_select_profile(self.options.index(option))


class WeekdaySelect(HeliaLuxEntity, SelectEntity):
    """Profil eines Wochentags (Montag zuerst, wie in der Lampe)."""

    _platform = "select"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HeliaLuxCoordinator, day: int, name: str) -> None:
        super().__init__(coordinator, f"profile_{name}")
        self._day = day

    @property
    def options(self) -> list[str]:
        profiles = self.coordinator.data.profiles
        return option_names(profiles.names) if profiles else []

    @property
    def current_option(self) -> str | None:
        profiles = self.coordinator.data.profiles
        if not profiles or len(profiles.week) <= self._day:
            return None
        index = profiles.week[self._day]
        options = self.options
        return options[index] if 0 <= index < len(options) else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_week_day(self._day, self.options.index(option))


class CloudSelect(HeliaLuxEntity, SelectEntity):
    """Wolken im heute aktiven Profil (Stärke bzw. Zug) – wirkt, solange das Profil der Lampe läuft."""

    _platform = "select"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: HeliaLuxCoordinator, key: str, options: tuple[str, ...]) -> None:
        super().__init__(coordinator, key)
        self._attr_options = list(options)
        self._intensity = key == "cloud_intensity"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.profile is not None

    @property
    def current_option(self) -> str | None:
        profile = self.coordinator.data.profile
        if profile is None:
            return None
        intensity, motion = profile.clouds
        return self._attr_options[intensity if self._intensity else (motion if intensity else 0)]

    async def async_select_option(self, option: str) -> None:
        value = self._attr_options.index(option)
        if self._intensity:
            await self.coordinator.async_set_clouds(intensity=value)
        else:
            await self.coordinator.async_set_clouds(motion=value)
