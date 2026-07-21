"""HA-harness tests for the control cycle (M1, ADR-0006/0007)."""

import pytest
from homeassistant.util import dt as dt_util

from custom_components.smart_charging.const import (
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    ROLE_EV_SOC,
    STATE_CHARGING,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.coordinator import SmartChargingCoordinator
from custom_components.smart_charging.modes._amp_step import ROUND_DOWN
from custom_components.smart_charging.modes._phase import Phase

_AMPLE_PEAK_HEADROOM_KW = 100.0  # keeps R3's clamp out of the way of tests that don't test it


class _FakeNumeric:
    def __init__(self, value):
        self._value = value
        self.written = []

    async def read(self):
        return self._value

    async def write(self, value):
        self.written.append(value)


class _FakeStatus:
    def __init__(self, canonical):
        self._canonical = canonical

    async def read(self):
        return self._canonical


class _RaisingNumeric:
    async def read(self):
        raise RuntimeError("adapter unavailable")

    async def write(self, value):
        raise AssertionError("should not be called by a raising read")


def _adapters(
    status=STATE_CHARGING, net_w=0.0, charger_w=0.0, voltage=230.0, ev_soc_role=True, ev_soc=50.0
):
    adapters = {
        "charger_current": _FakeNumeric(0.0),
        "charger_status": _FakeStatus(status),
        "net_power": _FakeNumeric(net_w),
        "charger_power": _FakeNumeric(charger_w),
        "grid_voltage": _FakeNumeric(voltage),
    }
    if ev_soc_role:
        adapters[ROLE_EV_SOC] = _FakeNumeric(ev_soc)
    return adapters


def _config():
    return {
        "min_current": 6.0,
        "max_current": 16.0,
        "grid_ceiling_a": 25.0,
        "grid_safety_offset_a": 2.0,
        "nominal_voltage": 230.0,
        CONF_SMOOTHING_WINDOW: 1,
        CONF_SOLAR_START_THRESHOLD_W: 100.0,
        CONF_SOLAR_ONLY_START_THRESHOLD_W: 100.0,
        CONF_SOLAR_HOLD_MIN: 5.0,
        CONF_SOLAR_COOLDOWN_MIN: 2.0,
        CONF_SOLAR_ONLY_STRATEGY: ROUND_DOWN,
        CONF_SOLAR_ONLY_MIDPOINT: 0.5,
        CONF_MAX_PEAK_KW: 100.0,
        CONF_SAFETY_MARGIN_W: 250.0,
        CONF_PEAK_GRACE_MIN: 2.0,
        CONF_CAPTAR_COOLDOWN_MIN: 5.0,
        CONF_POWER_RESPECT_PEAK: True,
        CONF_PEAK_WINDOW_SIZE: 1,
    }


def _seed_ample_peak_headroom(coord, kw=_AMPLE_PEAK_HEADROOM_KW):
    """Pre-seed the Peak-Demand Tracker as though a large historical peak already exists
    (the same shape a MonthlyPeakSensor restore would seed, Task 4.2) -- keeps R3's clamp
    out of the way of tests that exercise unrelated behavior, not R3 itself."""
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = kw


async def _run(hass, adapters, config, target):
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER  # M1's original default before mode selection existed (Task 5.1)
    coord.target_current = target
    _seed_ample_peak_headroom(coord)
    result = await coord._async_update_data()
    return coord, result


async def _run_mode(hass, adapters, config, active_mode, soc_limit_override=80.0, coord=None):
    if coord is None:
        coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    else:
        coord._adapters = adapters
    coord.active_mode = active_mode
    coord.soc_limit_override = soc_limit_override
    _seed_ample_peak_headroom(coord)
    result = await coord._async_update_data()
    return coord, result


async def test_r17_commands_target_when_charging(hass):
    adapters = _adapters(status=STATE_CHARGING)
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert adapters["charger_current"].written == [10.0]
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_uc04_zero_when_disconnected(hass):
    adapters = _adapters(status=STATE_DISCONNECTED)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.commanded_current == 0.0
    assert result.fault is False
    assert adapters["charger_current"].written == [0.0]


async def test_c4_grid_ceiling_clamps_command(hass):
    # baseline = net 5980 - charger 3680 = 2300 W = 10 A;
    # headroom = (ceiling 25 - offset 2) - 10 = 13 A.
    adapters = _adapters(status=STATE_CHARGING, net_w=5980.0, charger_w=3680.0)
    _coord, result = await _run(hass, adapters, _config(), target=20.0)
    assert result.commanded_current == 13.0


async def test_adr0007_status_none_is_fault_and_forces_zero(hass):
    adapters = _adapters(status=None)  # unmapped/unavailable -> fault
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters["charger_current"].written == [0.0]


@pytest.mark.parametrize("role", ["net_power", "charger_power"])
async def test_adr0007_other_required_roles_none_is_fault(hass, role):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[role] = _FakeNumeric(None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters["charger_current"].written == [0.0]


async def test_adr0007_cycle_exception_is_fault_and_forces_zero(hass):
    adapters = _adapters(status=STATE_CHARGING)
    adapters["charger_status"] = _RaisingNumeric()
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters["charger_current"].written == [0.0]


async def test_adr0007_recovers_after_fault(hass):
    adapters = _adapters(status=None)
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert coord._was_faulted is True

    adapters["charger_status"] = _FakeStatus(STATE_CHARGING)
    result = await coord._async_update_data()
    assert result.fault is False
    assert coord._was_faulted is False


async def test_nf4_grid_voltage_none_is_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING)
    adapters["grid_voltage"] = _FakeNumeric(None)  # NF4 fallback, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_nf4_grid_voltage_unmapped_is_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING)
    del adapters["grid_voltage"]  # role not configured -> nominal voltage, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_dispatches_to_solar_when_selected(hass):
    # Arrange: surplus = charger_w(2760=12A) - net_w(0) = 2760W = 12A ideal, round-up -> 12A.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert
    assert result.fault is False
    assert result.commanded_current == 12.0
    assert result.active_mode == MODE_SOLAR


async def test_dispatches_to_solar_only_when_selected(hass):
    # Arrange
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_SOLAR_ONLY, soc_limit_override=80.0
    )

    # Assert
    assert result.fault is False
    assert result.commanded_current == 12.0
    assert result.active_mode == MODE_SOLAR_ONLY


@pytest.mark.parametrize("mode", [MODE_SOLAR, MODE_SOLAR_ONLY, MODE_CAPTAR])
async def test_soc_at_or_above_limit_forces_zero_and_holds_solar_states_at_idle(hass, mode):
    # Arrange: ev_soc at the configured limit, with ample surplus that would otherwise charge.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=80.0)

    # Act
    coord, result = await _run_mode(hass, adapters, _config(), mode, soc_limit_override=80.0)

    # Assert
    assert result.commanded_current == 0.0
    assert coord._mode_state[mode].phase == Phase.IDLE


async def test_resumes_when_the_soc_limit_rises_above_current_soc(hass):
    """R7 resume condition 1. Multi-cycle by nature (a resume is only observable across two
    cycles of the same coordinator), so Arrange/Act/Assert repeats once per cycle below."""
    # Arrange: gated at the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=80.0)

    # Act (cycle 1)
    coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert (cycle 1)
    assert result.commanded_current == 0.0  # gated: ev_soc >= limit

    # Act (cycle 2): the limit rises above the current SOC, same mode, no reconnect.
    coord, result = await _run_mode(
        hass, adapters, _config(), MODE_SOLAR, soc_limit_override=90.0, coord=coord
    )

    # Assert (cycle 2)
    assert result.commanded_current == 12.0


async def test_resumes_after_disconnect_and_reconnect_while_still_at_the_limit(hass):
    """R7 resume condition 2. Multi-cycle by nature (see test above); each phase below is its
    own Arrange/Act/Assert."""
    config = _config()

    # Arrange (cycle 1): gated at the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Act (cycle 1)
    coord, result = await _run_mode(hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0)

    # Assert (cycle 1)
    assert result.commanded_current == 0.0

    # Arrange (cycle 2): disconnect.
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Act (cycle 2)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 2): every mode's state resets to idle (existing R11 reset path).
    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_SOLAR].phase == Phase.IDLE

    # Arrange (cycle 3): reconnect while still at the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Act (cycle 3)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 3): gate still holds, no stuck Hold/Cooldown either.
    assert result.commanded_current == 0.0

    # Arrange (cycle 4): SOC finally drops below the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=70.0)

    # Act (cycle 4)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 4): resumes immediately, proving nothing was left latched by the
    # disconnect/reconnect cycle.
    assert result.commanded_current == 12.0


@pytest.mark.parametrize("mode", [MODE_POWER, MODE_OFF])
async def test_power_and_off_ignore_soc_entirely(hass, mode):
    # Arrange: no ev_soc role configured at all -- Power/Off must not regress to needing one.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc_role=False)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=_config(), interval_s=30)
    coord.active_mode = mode
    coord.soc_limit_override = 80.0
    coord.target_current = 10.0
    _seed_ample_peak_headroom(coord)

    # Act
    result = await coord._async_update_data()

    # Assert
    assert result.fault is False
    assert result.commanded_current == (10.0 if mode == MODE_POWER else 0.0)


async def test_missing_ev_soc_faults_only_while_a_solar_mode_is_selected(hass):
    """Two independent modes exercised in one test since they're the same behavior
    ('does this mode require ev_soc') viewed from each side; each is its own Act/Assert."""
    # Arrange (Solar): ev_soc role unmapped.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc_role=False)

    # Act (Solar)
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert (Solar): faults, since a solar mode requires ev_soc.
    assert result.fault is True
    assert result.commanded_current == 0.0

    # Arrange (Power): same unmapped ev_soc role.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc_role=False)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=_config(), interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0

    # Act (Power)
    result = await coord._async_update_data()

    # Assert (Power): no fault, since Power never needs ev_soc.
    assert result.fault is False


async def test_disconnect_with_unavailable_ev_soc_is_a_clean_stop_not_a_fault(hass):
    """A disconnected car is always a clean idle stop (UC01/R7), even when its own SOC
    sensor also goes unavailable on unplug -- ev_soc is only required while the car is
    both connected and a solar mode is active."""
    # Arrange
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0, ev_soc_role=False)

    # Act
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert
    assert result.fault is False
    assert result.commanded_current == 0.0


async def test_mode_switch_resets_the_incoming_modes_state(hass):
    """Multi-cycle by nature (a reset is only observable by comparing state across a
    switch); each phase below is its own Arrange/Act/Assert."""
    config = _config()
    config[CONF_SOLAR_HOLD_MIN] = 0.0  # Hold -> Cooldown transitions on the very next cycle
    config[CONF_SOLAR_COOLDOWN_MIN] = 5.0  # long enough that real test wall-clock never clears it

    ample = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    idle_surplus = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)

    # Act (cycle 1): ample surplus.
    coord, result = await _run_mode(hass, ample, config, MODE_SOLAR, soc_limit_override=80.0)

    # Assert (cycle 1)
    assert result.commanded_current == 12.0  # charging

    # Act (cycle 2): surplus drops below the start threshold.
    coord, result = await _run_mode(
        hass, idle_surplus, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 2)
    assert result.commanded_current == 6.0  # hold, floored at min_a

    # Act (cycle 3): still no surplus, hold_min elapsed (0).
    coord, result = await _run_mode(
        hass, idle_surplus, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 3)
    assert result.commanded_current == 0.0  # cooldown
    assert coord._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN

    # Act (cycles 4-5): switch away and back -- both transitions reset _mode_state (R11).
    coord, result = await _run_mode(
        hass, ample, config, MODE_OFF, soc_limit_override=80.0, coord=coord
    )
    coord, result = await _run_mode(
        hass, ample, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycles 4-5)
    assert result.commanded_current == 12.0  # fresh idle -> charges immediately, no cooldown wait


async def test_grid_ceiling_still_clamps_a_solar_request(hass):
    # Arrange: surplus = 2645W = 11.5A ideal; Solar rounds up -> 12A pre-clamp.
    # headroom = floor(0 + 11.5) = 11A -> clamped from 12A to 11A.
    config = _config()
    config["grid_ceiling_a"] = 2.0
    config["grid_safety_offset_a"] = 2.0  # ceiling - offset == 0
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2645.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0)

    # Assert
    assert result.commanded_current == 11.0


async def test_power_mode_behavior_unchanged(hass):
    # Arrange
    adapters = _adapters(status=STATE_CHARGING)

    # Act
    _coord, result = await _run(hass, adapters, _config(), target=10.0)

    # Assert
    assert result.fault is False
    assert result.commanded_current == 10.0
    assert result.active_mode == MODE_POWER


async def test_dispatches_to_captar_when_selected(hass):
    # Arrange: ample R3 headroom (auto-seeded by _run_mode) and ample grid-ceiling headroom.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_CAPTAR, soc_limit_override=80.0
    )

    # Assert: Captar always requests max_current -- no downstream clamp reduces it here.
    assert result.fault is False
    assert result.commanded_current == 16.0
    assert result.active_mode == MODE_CAPTAR


async def test_monthly_peak_tracker_updates_every_cycle_regardless_of_mode(hass):
    """R3's bookkeeping is not Captar-specific -- Off/Power update it too. Bypasses the
    ample-headroom test helpers deliberately, to observe the tracker's own cold-start
    behavior (design doc Sec 6.4)."""
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=3400.0, charger_w=0.0)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=_config(), interval_s=30)
    coord.active_mode = MODE_OFF

    result = await coord._async_update_data()

    assert result.monthly_peak_kw == pytest.approx(3.4)


async def test_effective_peak_limit_resolves_to_the_lesser_of_tracked_and_max(hass):
    config = _config()
    config[CONF_MAX_PEAK_KW] = 4.0
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_OFF
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 3.0  # already-tracked peak is the lesser of the two

    result = await coord._async_update_data()

    assert result.effective_peak_limit_kw == 3.0


async def test_peak_clamp_reduces_captar_below_headroom(hass):
    """A high household baseline load reduces Captar's requested max-current down to the
    available headroom -- a momentary reduction (still above min_a), not a stop."""
    config = _config()
    config[CONF_MAX_PEAK_KW] = 3.56
    config[CONF_SAFETY_MARGIN_W] = 250.0
    # effective_peak_limit(3.56 kW) - margin(250W) - baseline(1000W) = 2310W = 10.04A -> 10A.
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 3.56

    result = await coord._async_update_data()

    assert result.commanded_current == 10.0
    assert result.fault is False


async def test_peak_clamp_reduces_solar_below_headroom(hass):
    """R3 now applies to Solar too -- no opt-out (only Power has one, R17). A tight peak
    budget (below the safety margin) reduces Solar's surplus-based request even though
    the surplus itself is ample, proving R3 isn't Captar-only."""
    config = _config()
    config[CONF_MAX_PEAK_KW] = 0.1  # 100 W -- deliberately below the 250 W safety margin
    config[CONF_SAFETY_MARGIN_W] = 250.0
    # surplus = charger_w(2760) - net_w(0) = 2760 W -> round up -> 12 A ideal.
    # headroom = floor((100 - 250 - (0 - 2760)) / 230) = floor(2610 / 230) = 11 A.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 0.1

    result = await coord._async_update_data()

    assert result.commanded_current == 11.0
    assert result.fault is False


async def test_sustained_peak_breach_at_minimum_stops_captar_and_starts_cooldown(hass):
    """Grace period 0 -- the very first breaching cycle already exceeds it -- forces 0 A
    and CaptarState -> cooldown; the cooldown then blocks a restart until it elapses (R11)."""
    config = _config()
    config[CONF_MAX_PEAK_KW] = 1.0
    config[CONF_SAFETY_MARGIN_W] = 250.0
    config[CONF_PEAK_GRACE_MIN] = 0.0
    config[CONF_CAPTAR_COOLDOWN_MIN] = 5.0
    # effective_peak_limit(1.0 kW) - margin(250W) - baseline(600W) = 150W = 0.65A -> 0A < min_a.
    breaching = _adapters(status=STATE_CHARGING, net_w=600.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(hass, adapters=breaching, config=config, interval_s=30)
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 1.0

    result = await coord._async_update_data()

    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # A second cycle, even with ample headroom restored, stays blocked until the
    # cooldown (5 minutes) elapses -- essentially no wall-clock time has passed.
    ample = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord._adapters = ample
    result = await coord._async_update_data()

    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN


async def test_captar_cooldown_resets_on_mode_switch(hass):
    """Switching away from Captar and back clears its cooldown state (R11)."""
    config = _config()
    config[CONF_MAX_PEAK_KW] = 1.0
    config[CONF_PEAK_GRACE_MIN] = 0.0
    breaching = _adapters(status=STATE_CHARGING, net_w=600.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(hass, adapters=breaching, config=config, interval_s=30)
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 1.0
    await coord._async_update_data()
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # Switch away and back -- both transitions reset _mode_state (R11), same as Solar's.
    # Also restore ample peak headroom so only the cooldown reset is under test here.
    ample = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord._adapters = ample
    coord._config = {**config, CONF_MAX_PEAK_KW: _AMPLE_PEAK_HEADROOM_KW}
    coord._peak_tracked_kw = _AMPLE_PEAK_HEADROOM_KW
    coord.active_mode = MODE_OFF
    await coord._async_update_data()
    coord.active_mode = MODE_CAPTAR
    result = await coord._async_update_data()

    assert result.commanded_current == 16.0  # fresh idle -> charges immediately, no cooldown wait
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_captar_resets_on_disconnect(hass):
    """A disconnect resets Captar's state to idle() -- not a cooldown -- per UC03's state model."""
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_CAPTAR, soc_limit_override=80.0
    )
    assert result.commanded_current == 16.0  # confirm it was charging first

    disconnected = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord, result = await _run_mode(
        hass, disconnected, _config(), MODE_CAPTAR, soc_limit_override=80.0, coord=_coord
    )

    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.IDLE


async def test_power_respects_peak_by_default(hass):
    """Power's own target(16A) would normally be commanded outright (existing MVP
    behavior); with power_respect_peak left at its default (True), R17 now ALSO
    bounds it by the R3 clamp -- a deliberate behavior change (design doc Sec 7)."""
    config = _config()
    config[CONF_MAX_PEAK_KW] = 3.56
    # Same headroom math as test_peak_clamp_reduces_captar_below_headroom: 10A available.
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 16.0
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 3.56

    result = await coord._async_update_data()

    assert result.commanded_current == 10.0


async def test_power_can_opt_out_of_peak_protection(hass):
    """sc_power_respect_peak=False skips the R3 clamp (E5), but the C4 grid-ceiling
    clamp (E6) still applies -- distinct call sites (ADR-0006)."""
    config = _config()
    config[CONF_MAX_PEAK_KW] = 3.56
    config[CONF_POWER_RESPECT_PEAK] = False
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 16.0
    now_dt = dt_util.now()
    coord._peak_tracked_month = (now_dt.year, now_dt.month)
    coord._peak_tracked_kw = 3.56

    result = await coord._async_update_data()

    # R3 skipped entirely -- E6's grid-ceiling headroom (18A) is the only bound left.
    assert result.commanded_current == 16.0


async def test_grid_ceiling_still_clamps_a_captar_request(hass):
    """E6 (unchanged) still reduces a Captar-mode request that would breach the ceiling,
    even with ample R3 headroom (auto-seeded by _run_mode)."""
    config = _config()
    config["grid_ceiling_a"] = 2.0
    config["grid_safety_offset_a"] = 2.0  # ceiling - offset == 0
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2645.0, ev_soc=50.0)

    _coord, result = await _run_mode(hass, adapters, config, MODE_CAPTAR, soc_limit_override=80.0)

    assert result.commanded_current == 11.0
