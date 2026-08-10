"""RA3: reads and writes owned control-entity state through the entity registry + HA state
machine (ADR-0018/0019)."""

from __future__ import annotations

import logging
from datetime import time
from typing import TypeVar

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN

T = TypeVar("T", str, float, bool, time)

_LOGGER = logging.getLogger(__name__)


class Store:
    """One instance per config entry (mirrors the Adapter factory's per-entry scoping,
    ADR-0003) -- read() and write() only ever resolve this entry's own owned entities."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id

    def resolve_entity_id(self, entity_domain: str, unique_id_suffix: str) -> str | None:
        """Shared entity-id resolution for read() and write() -- the one place both halves'
        f"{entry_id}_{unique_id_suffix}" lookup lives, so they cannot drift apart. Public so a
        Manager needing the real entity_id up front (e.g. to register a state-change listener)
        resolves it the same way, rather than hardcoding it (ADR-0013's locale-dependent id
        concern)."""
        return er.async_get(self._hass).async_get_entity_id(
            entity_domain, DOMAIN, f"{self._entry_id}_{unique_id_suffix}"
        )

    async def read(
        self, entity_domain: str, unique_id_suffix: str, value_type: type[T]
    ) -> T | None:
        """Resolve f"{entry_id}_{unique_id_suffix}" as an entity_domain entity via the entity
        registry, read its HA state, and coerce to value_type. None if unregistered,
        missing/unknown/unavailable, or the value doesn't coerce -- never raises (mirrors
        NumericReadAdapter.read(), ADR-0003)."""
        entity_id = self.resolve_entity_id(entity_domain, unique_id_suffix)
        if entity_id is None:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        if value_type is float:
            try:
                return float(state.state)
            except (ValueError, TypeError):
                return None
        if value_type is bool:
            return state.state == STATE_ON
        if value_type is time:
            try:
                return time.fromisoformat(state.state)
            except ValueError:
                return None
        return state.state

    async def write(self, entity_domain: str, unique_id_suffix: str, value: float | bool) -> bool:
        """Set `value` on this entry's owned `entity_domain` entity identified by
        `unique_id_suffix`. Returns True if applied, False otherwise; never raises
        (symmetric with read(), and the best-effort contract VehicleLimitManager's
        _write_vehicle expects -- ADR-0003/ADR-0018).

        Two value shapes are supported today, one per real caller: a `float` into a
        `number` entity (M2 -> soc_limit_override), and a `bool` into a `switch` entity
        (M3 -> home_day_flag, docs/plans/2026-08-09-ra3-store-write-half-design.md's
        deferral, closed by notifications Task 4.1). Other domains return False rather
        than issuing a service call against an entity that cannot take it.
        """
        if entity_domain not in (Platform.NUMBER, Platform.SWITCH):
            _LOGGER.debug("Store.write: unsupported entity domain %s", entity_domain)
            return False
        entity_id = self.resolve_entity_id(entity_domain, unique_id_suffix)
        if entity_id is None:
            return False
        if entity_domain == Platform.NUMBER:
            domain, service, service_data = (
                Platform.NUMBER,
                SERVICE_SET_VALUE,
                {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
            )
        else:
            # switch.turn_on/turn_off take no value payload -- the value picks the service,
            # not a service-call argument (design doc's write-half addendum, switch case).
            domain, service, service_data = (
                Platform.SWITCH,
                SERVICE_TURN_ON if value else SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: entity_id},
            )
        # Best-effort (ADR-0018): an out-of-range value or any other service-call failure
        # must not break a Manager's reaction path, and is not an ADR-0007 hardware fault
        # either -- caught broadly and reported to the caller, never escalated.
        try:
            await self._hass.services.async_call(domain, service, service_data, blocking=True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Store.write %s failed: %s", entity_id, err)
            return False
        return True
