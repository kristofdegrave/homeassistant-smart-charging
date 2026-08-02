"""Departure-time entities (C2, R14). ADR-0004 native naming.

Nine owned `time` entities per design doc Sec 4 / `entity-catalog.md`: one per day of week
(`mon`..`sun`) plus a public-holiday override and a home-day override.

Deviation from design doc Sec 4: that section claims these entities need no `RestoreEntity`
because "a `time` entity's state persists natively via HA's own entity-registry state". That
is not correct for an integration-owned platform entity (as opposed to a storage-backed helper
like `input_datetime`) -- the entity registry persists entity *metadata* (unique_id, name,
...), not the runtime state value; without `RestoreEntity`, a user-set departure time would
silently revert to its constructor default on every HA restart, contradicting
`entity-catalog.md`'s own "runtime" persistence classification for these rows (the same
category `number.smart_charging_soc_limit_override`/`select.smart_charging_mode` are in, both
of which the codebase already restores). This class therefore mirrors `ModeSelect`
(`select.py`) and uses `RestoreEntity` -- flagged here as a corrected, task-scoped deviation
from the design doc's wording rather than a silent departure from it.
"""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DAY_FRI,
    DAY_MON,
    DAY_SAT,
    DAY_SUN,
    DAY_THU,
    DAY_TUE,
    DAY_WED,
    DEPARTURE_OVERRIDE_HOLIDAY,
    DEPARTURE_OVERRIDE_HOME_DAY,
    DOMAIN,
)
from .entity import SmartChargingEntity

WEEKDAY_DEFAULT = time(6, 0)

# (id_suffix, default) pairs for the seven day-of-week entities, Monday first (R14: Mon-Fri
# default 06:00, Sat/Sun default none).
DAY_OF_WEEK_DEFAULTS: list[tuple[str, time | None]] = [
    (DAY_MON, WEEKDAY_DEFAULT),
    (DAY_TUE, WEEKDAY_DEFAULT),
    (DAY_WED, WEEKDAY_DEFAULT),
    (DAY_THU, WEEKDAY_DEFAULT),
    (DAY_FRI, WEEKDAY_DEFAULT),
    (DAY_SAT, None),
    (DAY_SUN, None),
]

# The holiday/home-day overrides both default to none (R14).
OVERRIDE_DEFAULTS: list[tuple[str, time | None]] = [
    (DEPARTURE_OVERRIDE_HOLIDAY, None),
    (DEPARTURE_OVERRIDE_HOME_DAY, None),
]


# Day-of-week suffixes double as Python's own datetime.weekday() ordering (Monday=0..Sunday=6):
# DAY_OF_WEEK_DEFAULTS is Monday-first, so its list index *is* the weekday int.
_DAY_SUFFIX_TO_WEEKDAY: dict[str, int] = {
    suffix: weekday for weekday, (suffix, _) in enumerate(DAY_OF_WEEK_DEFAULTS)
}


class SmartChargingDepartureTime(SmartChargingEntity, RestoreEntity, TimeEntity):
    """One departure-time entity, parameterized by id-suffix and default (R14). Pushes its
    value into the coordinator on both restore and user-set, mirroring ModeSelect/ProfileSelect
    (select.py) so R14's deadline resolution and R9's home-day trigger see real user input
    instead of the coordinator's all-`None`/`False` construction-time defaults (issue #402)."""

    def __init__(self, entry_id: str, coordinator, id_suffix: str, default: time | None) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._id_suffix = id_suffix
        self._attr_translation_key = f"departure_{id_suffix}"
        self._object_id_suffix = f"departure_{id_suffix}"
        self._attr_unique_id = f"{entry_id}_departure_{id_suffix}"
        self._attr_native_value = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = time.fromisoformat(last.state)
            except ValueError:
                # Malformed restore-cache value -- keep the constructor default rather than
                # failing platform setup over a single bad cached value.
                pass
        self._push_to_coordinator()

    async def async_set_value(self, value: time) -> None:
        self._attr_native_value = value
        self._push_to_coordinator()
        await self._coordinator.async_request_refresh()
        self.async_write_ha_state()

    def _push_to_coordinator(self) -> None:
        if self._id_suffix == DEPARTURE_OVERRIDE_HOLIDAY:
            self._coordinator.set_departure_holiday_override(self._attr_native_value)
        elif self._id_suffix == DEPARTURE_OVERRIDE_HOME_DAY:
            self._coordinator.set_departure_home_day_override(self._attr_native_value)
        else:
            weekday = _DAY_SUFFIX_TO_WEEKDAY[self._id_suffix]
            self._coordinator.set_departure_dow_default(weekday, self._attr_native_value)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            SmartChargingDepartureTime(entry.entry_id, coordinator, suffix, default)
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
