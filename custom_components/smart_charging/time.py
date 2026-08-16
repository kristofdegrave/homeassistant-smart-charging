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
(`select.py`) and uses `RestoreEntity` -- a deliberate, narrow correction of the design
doc's wording rather than a silent departure from it.
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
    CONF_DEADLINE_AVAILABLE,
    DAY_FRI,
    DAY_MON,
    DAY_SAT,
    DAY_SUN,
    DAY_THU,
    DAY_TUE,
    DAY_WED,
    DEFAULT_DEADLINE_AVAILABLE,
    DEPARTURE_OVERRIDE_HOLIDAY,
    DEPARTURE_OVERRIDE_HOME_DAY,
    LABEL_SC_RUNTIME,
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


class SmartChargingDepartureTime(SmartChargingEntity, RestoreEntity, TimeEntity):
    """One departure-time entity, parameterized by id-suffix and default (R14).

    `_owned_labels` is set per-instance, gated on the deadline capability
    (`deadline_available`, R18): R19 AC4 requires these entities to be hidden from the
    runtime dashboard when the deadline capability is absent. Entities are still created
    either way -- only their dashboard visibility (the `sc_runtime` label) is gated.
    `_manageable_labels` stays the class-level constant superset (`entity.py`), so a later
    reload with the capability newly absent *removes* the label, not just adds it.
    """

    _manageable_labels = frozenset({LABEL_SC_RUNTIME})

    def __init__(
        self,
        entry_id: str,
        id_suffix: str,
        default: time | None,
        deadline_available: bool = DEFAULT_DEADLINE_AVAILABLE,
    ) -> None:
        self._attr_translation_key = f"departure_{id_suffix}"
        self._object_id_suffix = f"departure_{id_suffix}"
        super().__init__(entry_id)
        self._attr_native_value = default
        self._owned_labels = frozenset({LABEL_SC_RUNTIME}) if deadline_available else frozenset()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._attr_native_value = time.fromisoformat(last.state)
            except ValueError:
                pass  # malformed restored state -- keep the constructor default

    async def async_set_value(self, value: time) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    deadline_available = entry.data.get(CONF_DEADLINE_AVAILABLE, DEFAULT_DEADLINE_AVAILABLE)
    async_add_entities(
        [
            SmartChargingDepartureTime(
                entry.entry_id, suffix, default, deadline_available=deadline_available
            )
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
