"""Departure-time entities (C2, R14). ADR-0004 native naming.

Nine owned `time` entities per design doc Sec 4 / `entity-catalog.md`: one per day of week
(`mon`..`sun`) plus a public-holiday override and a home-day override. All are plain
user-editable `time` entities -- HA's own entity-registry state carries the value across a
restart, so no `RestoreEntity` is needed here (design doc Sec 4).
"""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import SmartChargingEntity

WEEKDAY_DEFAULT = time(6, 0)

# (id_suffix, default) pairs for the seven day-of-week entities, Monday first (R14: Mon-Fri
# default 06:00, Sat/Sun default none).
DAY_OF_WEEK_DEFAULTS: list[tuple[str, time | None]] = [
    ("mon", WEEKDAY_DEFAULT),
    ("tue", WEEKDAY_DEFAULT),
    ("wed", WEEKDAY_DEFAULT),
    ("thu", WEEKDAY_DEFAULT),
    ("fri", WEEKDAY_DEFAULT),
    ("sat", None),
    ("sun", None),
]

# The holiday/home-day overrides both default to none (R14).
OVERRIDE_DEFAULTS: list[tuple[str, time | None]] = [
    ("holiday", None),
    ("home_day", None),
]


class SmartChargingDepartureTime(SmartChargingEntity, TimeEntity):
    """One departure-time entity, parameterized by id-suffix and default (R14)."""

    def __init__(self, entry_id: str, id_suffix: str, default: time | None) -> None:
        super().__init__(entry_id)
        self._attr_translation_key = f"departure_{id_suffix}"
        self._attr_unique_id = f"{entry_id}_departure_{id_suffix}"
        self._attr_native_value = default

    async def async_set_value(self, value: time) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            SmartChargingDepartureTime(entry.entry_id, suffix, default)
            for suffix, default in (*DAY_OF_WEEK_DEFAULTS, *OVERRIDE_DEFAULTS)
        ]
    )


__all__ = [
    "DAY_OF_WEEK_DEFAULTS",
    "OVERRIDE_DEFAULTS",
    "WEEKDAY_DEFAULT",
    "SmartChargingDepartureTime",
    "async_setup_entry",
]
