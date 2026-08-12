"""Vehicle-Limit Manager (M2, V12) -- bidirectional vehicle charge-limit sync (UC09/R6).

A Manager (system-design §4 rule 5 / ADR-0011): triggered by HA state changes, including the
materialized active-SOC-limit diagnostic sensor's own state changes (the entity the
ActiveSocLimitChanged event fires alongside -- M2 observes the entity, not the bus event),
it reads inputs through adapters and writes the vehicle through the vehicle_charge_limit
adapter / adopts manual changes into number.smart_charging_soc_limit_override. It NEVER
calls or is called by the Coordinator.
No control-cycle logic, no clamps, no set-point -- see
docs/plans/2026-07-21-vehicle-limit-manager-design.md.

Homed under `managers/` per ADR-0015; `soc_limit_override` is reached through RA3's Store
(ADR-0018), never a coordinator reference, setter, or event.

Covers the Vehicle->System manual-adoption reaction (UC09 steps 4-6, R6 AC 5),
the disconnect-reset (UC09 steps 7-8, R6 AC 3), the
System->vehicle write branch (UC09 step 2, R6 AC 2/4, gated on connected AND car_home (C2)),
and `register_listeners`, wiring the three reactions above to real HA
state changes at setup (design §5.4) -- M2 self-wires its own triggers rather than a
dedicated C6 client (design §9.5).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event

from ..adapters.base import Adapter
from ..adapters.store import Store
from ..const import (
    ATTR_ENTRY_ID,
    ATTR_LIMIT,
    CHARGEABLE_STATES,
    EVENT_MANUAL_CHARGE_LIMIT_ADOPTED,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    EVENT_VEHICLE_CHARGE_LIMIT_SYNCED,
    OWNED_SUFFIX_ACTIVE_SOC_LIMIT,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    SOC_LIMIT_OVERRIDE_MAX,
    SOC_LIMIT_OVERRIDE_MIN,
    STATE_DISCONNECTED,
)

_LOGGER = logging.getLogger(__name__)


class VehicleLimitManager:
    """Vehicle-Limit Manager (M2). Holds the adapter map and the echo-guard state.

    `_last_written_limit` (design §6) records the value this Manager itself last wrote to
    the vehicle, so a subsequent vehicle-side report equal to it is recognised as an echo
    of our own write rather than a manual change. `_last_status` backs the disconnect-edge
    detection (design §5.3) -- an unknown/unavailable status reading (`None`) never
    overwrites it, so a transient dropout between two real readings can't erase the edge.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        adapters: dict[str, Adapter],
        entry_id: str,
        store: Store,
    ) -> None:
        self._hass = hass
        self._adapters = adapters
        self._entry_id = entry_id
        self._store = store
        self._last_written_limit: float | None = None
        self._last_status: str | None = None

    async def on_status_changed(self, status: str | None) -> None:
        """React to a canonical charger-status change (design §5.3). Disconnect edge -> reset.

        `status is None` (unregistered/unknown/unavailable read) is not a canonical state --
        it leaves `_last_status` untouched rather than being treated as "not connected", so a
        transient dropout between two real readings can't mask a genuine disconnect edge.
        """
        if status is None:
            return
        was_connected = self._last_status in CHARGEABLE_STATES
        self._last_status = status
        if status == STATE_DISCONNECTED and was_connected:
            await self._reset_to_default()

    async def on_vehicle_limit_changed(self, reported: float | None) -> None:
        """React to a vehicle-side charge-limit change (design §5.2). Adopt unless it is our
        own echo.

        Holds regardless of car_home (C2 gates only System->vehicle writes, never this
        read+adopt direction). Deliberately never updates `_last_written_limit` -- the echo
        guard tracks only the System's own writes to the vehicle (§5.1/§5.3), not a
        vehicle-originated adoption.
        """
        if reported is None:
            return
        if self._last_written_limit is not None and reported == self._last_written_limit:
            return  # our own write reflecting back -- echo guard (design §6)
        adopted = min(max(float(reported), SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX)
        if await self._store.write(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, adopted):
            self._fire(EVENT_MANUAL_CHARGE_LIMIT_ADOPTED, adopted)

    async def on_active_soc_limit_changed(self, new_limit: float | None) -> None:
        """React to a resolved active-SOC-limit change (design §5.1, ADR-0011). Writes the new
        value to the vehicle iff `charger_status` is connected/charging AND `car_home` is True
        (C2 -- UC09 alt 2a / R6 AC 4). `new_limit` is read from the materialized active-SOC-limit
        diagnostic sensor by the setup-time listener `register_listeners` wires.

        Reads `charger_status`/`car_home` through their adapters rather than re-deriving the
        Coordinator's composition (ADR-0011 Option B rejected). `charger_status` is a mandatory
        role (always registered), unlike the optional `car_home`; a `car_home` read of `None`
        (cannot confirm home) fails safe, the same as `False`.
        """
        if new_limit is None:
            return
        status = await self._adapters[ROLE_CHARGER_STATUS].read()
        if status not in CHARGEABLE_STATES:
            return
        car_home_adapter = self._adapters.get(ROLE_CAR_HOME)
        car_home = await car_home_adapter.read() if car_home_adapter is not None else None
        if car_home is not True:  # C2 -- None (cannot confirm) fails safe like False
            return
        value = float(new_limit)
        if await self._write_vehicle(value):
            self._fire(EVENT_VEHICLE_CHARGE_LIMIT_SYNCED, value)

    async def prime_status(self) -> None:
        """Seed `_last_status` from the ROLE_CHARGER_STATUS adapter's current reading
        (design §5.3). Call once at setup, before `register_listeners` subscribes to future
        changes: `async_track_state_change_event` only fires on changes observed AFTER
        registration, so an unprimed manager on a reload/restart with the vehicle already
        connected would never see the "before" side of the next connected->disconnected
        edge, silently skipping UC09 steps 7-8's reset. A `None` reading (unmapped/
        unavailable/unknown) primes to `None`, same as the unprimed skeleton default --
        the edge simply starts from scratch on the first later real reading.
        """
        self._last_status = await self._adapters[ROLE_CHARGER_STATUS].read()

    def register_listeners(
        self, *, vehicle_entity_id: str, status_entity_id: str
    ) -> list[Callable[[], None]]:
        """Wire M2's three triggers (design §5.4): the mapped `vehicle_charge_limit` and
        `charger_status` entities, and the materialized active-SOC-limit sensor. Called once
        at setup, only when `vehicle_charge_limit` is mapped -- the caller registers
        each returned unsub via `entry.async_on_unload` so a reload tears down and
        re-registers cleanly (ADR-0008).

        The two hardware-backed roles are read back through their own adapters rather than by
        parsing `event.data["new_state"].state` directly, so the adapter's numeric-coercion/
        status-translation/None semantics stay the single source of truth (ADR-0003) -- the
        same reasoning `_write_vehicle` already applies on the write side. The active-SOC-limit
        sensor is an owned diagnostic entity (E3/M1) with no adapter role of its own, so its real
        entity_id is resolved through the Store's registry lookup (ADR-0018/0019) rather than a
        hardcoded id, the same protection ADR-0013 gives every other owned entity against a
        locale change or rename silently breaking the binding. If it is not yet registered (it
        always is by the time `__init__.py` calls this, after platform setup), that one listener
        is simply not registered -- the reaction stays unreachable rather than raising, the same
        fail-safe M2 already applies when a role is unmapped.
        """

        async def _on_vehicle_event(_event: Event) -> None:
            await self.on_vehicle_limit_changed(
                await self._adapters[ROLE_VEHICLE_CHARGE_LIMIT].read()
            )

        async def _on_status_event(_event: Event) -> None:
            await self.on_status_changed(await self._adapters[ROLE_CHARGER_STATUS].read())

        async def _on_active_soc_limit_event(_event: Event) -> None:
            await self.on_active_soc_limit_changed(
                await self._store.read(Platform.SENSOR, OWNED_SUFFIX_ACTIVE_SOC_LIMIT, float)
            )

        unsubs = [
            async_track_state_change_event(self._hass, [vehicle_entity_id], _on_vehicle_event),
            async_track_state_change_event(self._hass, [status_entity_id], _on_status_event),
        ]
        active_soc_limit_entity_id = self._store.resolve_entity_id(
            Platform.SENSOR, OWNED_SUFFIX_ACTIVE_SOC_LIMIT
        )
        if active_soc_limit_entity_id is not None:
            unsubs.append(
                async_track_state_change_event(
                    self._hass, [active_soc_limit_entity_id], _on_active_soc_limit_event
                )
            )
        else:
            _LOGGER.debug(
                "active_soc_limit sensor not yet registered -- System->vehicle sync listener "
                "not installed this setup"
            )
        return unsubs

    async def _reset_to_default(self) -> None:
        default = await self._store.read(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, float)
        if default is None:
            _LOGGER.debug("soc_limit_override unavailable -- skipping disconnect reset")
            return
        if await self._write_vehicle(default):
            self._fire(EVENT_VEHICLE_CHARGE_LIMIT_RESET, default)

    async def _write_vehicle(self, value: float) -> bool:
        """Best-effort write to the vehicle; records the value for the echo guard. Returns
        success."""
        adapter = self._adapters.get(ROLE_VEHICLE_CHARGE_LIMIT)
        if adapter is None:
            return False
        try:
            await adapter.write(value)
        except Exception as err:  # noqa: BLE001 - a just-unplugged vehicle may be unreachable (§5.3)
            _LOGGER.debug("vehicle_charge_limit write failed: %s", err)
            return False
        self._last_written_limit = value
        return True

    def _fire(self, event_type: str, limit: float) -> None:
        self._hass.bus.async_fire(event_type, {ATTR_ENTRY_ID: self._entry_id, ATTR_LIMIT: limit})
