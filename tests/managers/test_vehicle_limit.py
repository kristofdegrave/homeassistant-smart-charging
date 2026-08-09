"""HA-harness tests for the Vehicle-Limit Manager (M2 -- UC09/R6/ADR-0011).

Covers the skeleton constructor/echo-guard state (Task 3.1, corrected to ADR-0018's Store
access shape), the disconnect-reset reaction (Task 3.2, UC09 steps 7-8, R6 AC 3), the
Vehicle->System manual-adoption reaction (Task 3.3, UC09 steps 4-6, R6 AC 5), and the
System->vehicle write-on-change reaction (Task 4.1, UC09 step 2, R6 AC 2/4, C2-gated --
dormant until E3/M1 materialize sensor.smart_charging_active_soc_limit, design §0). Drives
M2 through its public reaction methods directly (not HA listener plumbing -- that is Phase
5's job).
"""

from homeassistant.const import Platform
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.smart_charging.const import (
    ATTR_ENTRY_ID,
    ATTR_LIMIT,
    EVENT_MANUAL_CHARGE_LIMIT_ADOPTED,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    EVENT_VEHICLE_CHARGE_LIMIT_SYNCED,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    ROLE_CAR_HOME,
    ROLE_CHARGER_STATUS,
    ROLE_VEHICLE_CHARGE_LIMIT,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.managers.vehicle_limit import VehicleLimitManager


class _RWAdapter:
    def __init__(self, value=None):
        self.value = value
        self.writes = []

    async def read(self):
        return self.value

    async def write(self, value):
        self.writes.append(value)
        self.value = value


class _ReadAdapter:
    def __init__(self, value):
        self.value = value

    async def read(self):
        return self.value


class _FakeStore:
    """Stands in for adapters/store.py's Store (ADR-0018) -- mirrors the double in
    tests/test_coordinator.py."""

    def __init__(self, values, *, write_succeeds=True):
        self._values = values
        self._write_succeeds = write_succeeds
        self.writes = []

    async def read(self, entity_domain, unique_id_suffix, value_type):
        return self._values.get((entity_domain, unique_id_suffix))

    async def write(self, entity_domain, unique_id_suffix, value):
        self.writes.append((entity_domain, unique_id_suffix, value))
        return self._write_succeeds


def _manager(
    hass, *, vehicle=80.0, home=True, status=STATE_CONNECTED, soc_override=80.0, store=None
):
    adapters = {
        ROLE_VEHICLE_CHARGE_LIMIT: _RWAdapter(vehicle),
        ROLE_CAR_HOME: _ReadAdapter(home),
        ROLE_CHARGER_STATUS: _ReadAdapter(status),
    }
    if store is None:
        store = _FakeStore({(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): soc_override})
    return VehicleLimitManager(hass, adapters=adapters, entry_id="abc", store=store)


def _manager_without_vehicle_adapter(hass, *, soc_override=80.0):
    """No ROLE_VEHICLE_CHARGE_LIMIT entry -- design success-criterion 6, M2 stays inert."""
    adapters = {
        ROLE_CAR_HOME: _ReadAdapter(True),
        ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CONNECTED),
    }
    store = _FakeStore({(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): soc_override})
    return VehicleLimitManager(hass, adapters=adapters, entry_id="abc", store=store)


async def test_manager_starts_with_no_recorded_write(hass):
    """UC09 design §6: the echo guard initialises empty -- nothing written yet."""
    m = _manager(hass)
    assert m._last_written_limit is None


async def test_manager_starts_with_no_recorded_status(hass):
    """Disconnect detection is edge-based (design §5.3) -- nothing observed yet."""
    m = _manager(hass)
    assert m._last_status is None


async def test_disconnect_from_connected_resets_vehicle_to_default(hass):
    """UC09 step 8 / R6 AC 3: connected->disconnected writes the default (80%) to the vehicle."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_RESET)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]
    assert m._last_written_limit == 80.0  # recorded for the echo guard
    assert len(events) == 1
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_LIMIT: 80.0}


async def test_disconnect_from_charging_resets_vehicle_to_default(hass):
    """design §5.3: the edge's origin is "connected/charging", not just "connected"."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    await m.on_status_changed(STATE_CHARGING)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]


async def test_disconnected_non_edge_is_a_noop(hass):
    """No prior connected status -> no reset (design §5.3 edge detection)."""
    m = _manager(hass, vehicle=65.0)
    await m.on_status_changed(STATE_DISCONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_unknown_status_reading_does_not_mask_the_edge(hass):
    """A transient unavailable/unknown status read (None) between two real readings must not
    erase the edge -- connected -> None -> disconnected still resets (design §5.3)."""
    m = _manager(hass, vehicle=65.0, soc_override=80.0)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(None)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [80.0]


async def test_reset_write_failure_is_swallowed(hass):
    """A just-unplugged vehicle may be unreachable -- best-effort write (design §5.3)."""
    m = _manager(hass)
    await m.on_status_changed(STATE_CONNECTED)

    async def _boom(_value):
        raise RuntimeError("vehicle offline")

    m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].write = _boom
    await m.on_status_changed(STATE_DISCONNECTED)  # must not raise
    assert m._last_written_limit is None


async def test_reset_is_a_noop_when_no_default_soc_limit_is_available(hass):
    """The Store returns None when soc_limit_override is unregistered/unavailable (ADR-0018) --
    the reset must skip, not crash on float(None)."""
    m = _manager(hass, vehicle=65.0, soc_override=None)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_reset_is_a_noop_when_vehicle_adapter_is_unmapped(hass):
    """design success-criterion 6: no vehicle_charge_limit role configured -> M2 stays inert."""
    m = _manager_without_vehicle_adapter(hass)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)
    assert m._last_written_limit is None


async def test_manual_change_is_adopted_as_default(hass):
    """UC09 step 5 / R6 AC 5: a vehicle-side value != our last write -> adopted into
    soc_limit_override through the Store (ADR-0018), and ManualChargeLimitAdopted fires."""
    m = _manager(hass)
    events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)

    await m.on_vehicle_limit_changed(70.0)  # user set 70% on the car

    assert m._store.writes == [(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0)]
    assert len(events) == 1
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_LIMIT: 70.0}


async def test_echo_of_own_write_is_ignored(hass):
    """UC09 exception flow / R6 AC (echo guard): a report equal to our last write -> no
    adoption, and no ManualChargeLimitAdopted -- the vehicle is reflecting back a write M2
    itself just made, not a manual change."""
    m = _manager(hass, vehicle=80.0)
    await m.on_status_changed(STATE_CONNECTED)
    await m.on_status_changed(STATE_DISCONNECTED)  # records _last_written_limit = 80.0
    m._store.writes.clear()  # the disconnect-reset above reads the Store, never writes it
    events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)

    await m.on_vehicle_limit_changed(80.0)  # the vehicle reflects it back

    assert m._store.writes == []
    assert len(events) == 0


async def test_adoption_does_not_update_the_echo_guard(hass):
    """design §6: the echo guard tracks the System's own writes to the vehicle (§5.1/§5.3),
    never a vehicle-originated adoption -- otherwise a later, identical manual report would be
    wrongly swallowed as an echo of an adoption it never was."""
    m = _manager(hass)

    await m.on_vehicle_limit_changed(70.0)
    assert m._last_written_limit is None

    m._store.writes.clear()
    await m.on_vehicle_limit_changed(70.0)  # a second, identical report is still adopted
    assert m._store.writes == [(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0)]


async def test_manual_change_adopted_even_when_away(hass):
    """UC09 alt 5a: C2 gates only System->vehicle writes, never read+adopt --
    on_vehicle_limit_changed does not consult car_home at all today, so this also guards
    against Task 4.1's System->vehicle write accidentally sharing this reaction's code path."""
    m = _manager(hass, home=False)

    await m.on_vehicle_limit_changed(60.0)

    assert m._store.writes == [(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 60.0)]


async def test_adoption_clamps_above_the_number_range(hass):
    """R6 AC 1: the default SOC limit lives in 50-100."""
    m = _manager(hass)

    await m.on_vehicle_limit_changed(120.0)

    assert m._store.writes == [(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 100.0)]


async def test_adoption_clamps_below_the_number_range(hass):
    """R6 AC 1, the floor half -- catches a clamp written with only an upper bound
    (e.g. min(reported, MAX) with the floor silently dropped)."""
    m = _manager(hass)

    await m.on_vehicle_limit_changed(20.0)

    assert m._store.writes == [(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 50.0)]


async def test_none_report_is_ignored(hass):
    """A missing/unavailable vehicle read is not a manual change (design §4/§5)."""
    m = _manager(hass)

    await m.on_vehicle_limit_changed(None)

    assert m._store.writes == []


async def test_adoption_event_not_fired_when_store_write_fails(hass):
    """Store.write's bool return gates the domain event (mirrors _write_vehicle/
    EVENT_VEHICLE_CHARGE_LIMIT_RESET) -- a failed adoption write must not report success, but
    the write must still have been attempted (not an early no-op)."""
    store = _FakeStore(
        {(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): 80.0}, write_succeeds=False
    )
    m = _manager(hass, store=store)
    events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)

    await m.on_vehicle_limit_changed(70.0)

    assert store.writes == [(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE, 70.0)]
    assert len(events) == 0


async def test_soc_limit_change_writes_vehicle_when_connected_at_home(hass):
    """UC09 step 2 / R6 AC 2: connected + at home -> write the new limit + sync event
    (Task 4.1, dormant until E3/M1 materialize sensor.smart_charging_active_soc_limit)."""
    m = _manager(hass, home=True, status=STATE_CONNECTED)
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_SYNCED)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [90.0]
    assert m._last_written_limit == 90.0
    assert len(events) == 1
    assert events[0].data == {ATTR_ENTRY_ID: "abc", ATTR_LIMIT: 90.0}


async def test_soc_limit_change_writes_vehicle_when_connected_charging_at_home(hass):
    """design §5.1/C2: the guard's "connected" covers both connected and charging."""
    m = _manager(hass, home=True, status=STATE_CHARGING)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [90.0]


async def test_no_write_when_away(hass):
    """UC09 alt 2a / R6 AC 4: away -> no System write to the vehicle (C2)."""
    m = _manager(hass, home=False, status=STATE_CHARGING)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []
    assert m._last_written_limit is None


async def test_no_write_when_car_home_is_unknown(hass):
    """design §4: a car_home read of None means "cannot confirm home" -> suppress the write,
    same as an explicit False (fail-safe, C2)."""
    adapters = {
        ROLE_VEHICLE_CHARGE_LIMIT: _RWAdapter(80.0),
        ROLE_CAR_HOME: _ReadAdapter(None),
        ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CHARGING),
    }
    store = _FakeStore({(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): 80.0})
    m = VehicleLimitManager(hass, adapters=adapters, entry_id="abc", store=store)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_no_write_when_disconnected(hass):
    """UC09 alt 2a / R6 AC 4/C2: disconnected -> no System write, even if car_home is True."""
    m = _manager(hass, home=True, status=STATE_DISCONNECTED)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_no_write_when_charger_status_is_unknown(hass):
    """design §4: an unavailable/unknown charger_status read (None) is not a chargeable state
    -- fails safe, same as an explicit disconnected reading (C2)."""
    m = _manager(hass, home=True, status=None)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_no_write_when_car_home_role_is_unmapped(hass):
    """§3/§9.1: car_home is required whenever vehicle_charge_limit is mapped at config time, but
    the runtime guard must not crash/assume True if it is somehow absent -- fail-safe (C2)."""
    adapters = {
        ROLE_VEHICLE_CHARGE_LIMIT: _RWAdapter(80.0),
        ROLE_CHARGER_STATUS: _ReadAdapter(STATE_CHARGING),
    }
    store = _FakeStore({(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): 80.0})
    m = VehicleLimitManager(hass, adapters=adapters, entry_id="abc", store=store)

    await m.on_active_soc_limit_changed(90.0)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_active_soc_limit_none_report_is_ignored(hass):
    """A missing/unavailable sensor read is not a resolved-limit change (mirrors
    on_vehicle_limit_changed's None handling, design §5.1)."""
    m = _manager(hass, home=True, status=STATE_CHARGING)

    await m.on_active_soc_limit_changed(None)

    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == []


async def test_write_then_reflect_back_settles_without_a_second_write(hass):
    """UC09 exception flow: §5.1 write -> vehicle echoes -> §5.2 echo guard suppresses
    re-adoption and no second write occurs (settling loop, design §6)."""
    m = _manager(hass, home=True, status=STATE_CHARGING)
    adoption_events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)

    await m.on_active_soc_limit_changed(90.0)  # System write records 90
    await m.on_vehicle_limit_changed(90.0)  # vehicle reflects 90 back

    assert len(adoption_events) == 0  # not re-adopted
    assert m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].writes == [90.0]  # no second write


async def test_active_soc_limit_write_failure_is_swallowed(hass):
    """A vehicle unreachable at the moment of a resolved-limit change is best-effort, same as
    the disconnect-reset branch (design §5.1, mirrors §5.3). The failed write must not report
    success -- no VehicleChargeLimitSynced fires (mirrors
    test_adoption_event_not_fired_when_store_write_fails)."""
    m = _manager(hass, home=True, status=STATE_CHARGING)
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_SYNCED)

    async def _boom(_value):
        raise RuntimeError("vehicle offline")

    m._adapters[ROLE_VEHICLE_CHARGE_LIMIT].write = _boom

    await m.on_active_soc_limit_changed(90.0)  # must not raise

    assert m._last_written_limit is None
    assert len(events) == 0


async def test_active_soc_limit_change_is_a_noop_when_vehicle_adapter_is_unmapped(hass):
    """design success-criterion 6: no vehicle_charge_limit role configured -> M2 stays inert."""
    m = _manager_without_vehicle_adapter(hass)

    await m.on_active_soc_limit_changed(90.0)

    assert m._last_written_limit is None
