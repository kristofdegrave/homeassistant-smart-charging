"""HA-harness tests for the control cycle (M1, ADR-0006/0007)."""

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.smart_charging.const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    DEFAULT_CAPTAR_AVAILABLE,
    EVENT_ACTIVE_SOC_LIMIT_CHANGED,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    PROFILE_AUTO,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_EV_BATTERY_CAPACITY,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_LOW_TARIFF,
    ROLE_NET_POWER,
    ROLE_SOLAR_FORECAST,
    ROLE_SUN,
    STATE_CHARGING,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.coordinator import SmartChargingCoordinator
from custom_components.smart_charging.engines.soc_target import SolarStepUpState
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
    status=STATE_CHARGING,
    net_w=0.0,
    charger_w=0.0,
    voltage=230.0,
    ev_soc_role=True,
    ev_soc=50.0,
    sun_state=None,
    low_tariff=None,
):
    adapters = {
        ROLE_CHARGER_CURRENT: _FakeNumeric(0.0),
        ROLE_CHARGER_STATUS: _FakeStatus(status),
        ROLE_NET_POWER: _FakeNumeric(net_w),
        ROLE_CHARGER_POWER: _FakeNumeric(charger_w),
        ROLE_GRID_VOLTAGE: _FakeNumeric(voltage),
        # ROLE_SUN is built unconditionally by the real factory (issue #376) -- present
        # here too, `sun_state=None` (both sun_is_up/sun_is_down False) matching the prior
        # default behavior of an unset sun.sun entity.
        ROLE_SUN: _FakeNumeric(sun_state),
    }
    if ev_soc_role:
        adapters[ROLE_EV_SOC] = _FakeNumeric(ev_soc)
    if low_tariff is not None:
        adapters[ROLE_LOW_TARIFF] = _FakeNumeric(low_tariff)
    return adapters


def _config():
    return {
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_NOMINAL_VOLTAGE: 230.0,
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
        CONF_MAX_SOLAR_SOC: 100.0,
        CONF_SOLAR_STEP_PP: 5.0,
        CONF_SOLAR_STEP_THRESHOLD_PP: 2.0,
    }


def _seed_today_deadline(coord, hours_from_now):
    """Seed today's departure-deadline default so it resolves `hours_from_now` ahead of
    real wall-clock now (Task 5.2's deadline/required-current resolution reads dt_util.now(),
    not the mode state machines' injected monotonic clock)."""
    now_dt = dt_util.now()
    coord.departure_dow_defaults[now_dt.weekday()] = (
        now_dt + timedelta(hours=hours_from_now)
    ).time()


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
    assert adapters[ROLE_CHARGER_CURRENT].written == [10.0]
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_uc04_zero_when_disconnected(hass):
    adapters = _adapters(status=STATE_DISCONNECTED)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.commanded_current == 0.0
    assert result.fault is False
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


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
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


@pytest.mark.parametrize("role", [ROLE_NET_POWER, ROLE_CHARGER_POWER])
async def test_adr0007_other_required_roles_none_is_fault(hass, role):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[role] = _FakeNumeric(None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


async def test_adr0007_cycle_exception_is_fault_and_forces_zero(hass):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[ROLE_CHARGER_STATUS] = _RaisingNumeric()
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


async def test_adr0007_recovers_after_fault(hass):
    adapters = _adapters(status=None)
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert coord._was_faulted is True

    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_CHARGING)
    result = await coord._async_update_data()
    assert result.fault is False
    assert coord._was_faulted is False


async def test_nf4_grid_voltage_none_is_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[ROLE_GRID_VOLTAGE] = _FakeNumeric(None)  # NF4 fallback, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_nf4_grid_voltage_unmapped_is_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING)
    del adapters[ROLE_GRID_VOLTAGE]  # role not configured -> nominal voltage, not a fault
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
    config[CONF_GRID_CEILING_A] = 2.0
    config[CONF_GRID_SAFETY_OFFSET_A] = 2.0  # ceiling - offset == 0
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
    config[CONF_GRID_CEILING_A] = 2.0
    config[CONF_GRID_SAFETY_OFFSET_A] = 2.0  # ceiling - offset == 0
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2645.0, ev_soc=50.0)

    _coord, result = await _run_mode(hass, adapters, config, MODE_CAPTAR, soc_limit_override=80.0)

    assert result.commanded_current == 11.0


# --- Task 5.1: full active-SOC-limit resolution + ActiveSocLimitChanged (R7/R8/R9) ---


async def test_active_soc_limit_resolves_via_the_three_row_table(hass):
    """With a solar step-up already in effect, active_soc_limit reflects the stepped
    value, not the raw soc_limit_override (E3 row 2)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_soc_limit == 85.0


async def test_solar_step_up_applies_a_fresh_step_when_soc_nears_the_current_limit(hass):
    """No step-up in effect yet: SOC within step_threshold_pp of soc_limit_override triggers
    a fresh step, proving the coordinator wires ev_soc (not some other value) into
    resolve_solar_step_up's soc parameter (R8/UC06 main success)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=79.0)
    config = _config()  # step_threshold_pp=2.0, step_pp=5.0
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_soc_limit == 85.0
    assert coord._step_up_state.stepped_pct == 85.0


async def test_solar_step_up_clears_on_mode_switch_away_from_solar(hass):
    """Switching from Solar to Power resets self._step_up_state (UC06 exception flow)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    coord.active_mode = MODE_POWER
    await coord._async_update_data()

    assert coord._step_up_state == SolarStepUpState()


async def test_solar_step_up_clears_on_disconnect(hass):
    """A disconnect clears the step-up state even while Solar is still selected (UC06)."""
    adapters = _adapters(status=STATE_DISCONNECTED, ev_soc_role=False)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._step_up_state == SolarStepUpState()


async def test_solar_step_up_survives_solar_to_solaronly_switch(hass):
    """R7/UC06 alternate flow 4a: a Solar<->SolarOnly switch preserves an in-effect
    step-up -- only the generic per-mode-switch reset is scoped to _mode_state, not this."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    coord.active_mode = MODE_SOLAR_ONLY
    await coord._async_update_data()

    assert coord._step_up_state == SolarStepUpState(stepped_pct=85.0)


async def test_active_soc_limit_changed_event_fires_on_change(hass):
    """ADR-0011: ActiveSocLimitChanged fires only when the resolved value differs from
    the prior cycle's, not on every cycle."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)

    events = []
    hass.bus.async_listen(EVENT_ACTIVE_SOC_LIMIT_CHANGED, lambda event: events.append(event))

    await coord._async_update_data()  # first resolution: 80.0, no prior value -> fires
    assert len(events) == 1
    assert events[0].data[ATTR_ACTIVE_SOC_LIMIT] == 80.0

    await coord._async_update_data()  # unchanged -> no second event
    assert len(events) == 1

    coord.soc_limit_override = 90.0
    await coord._async_update_data()  # changed -> fires again
    assert len(events) == 2
    assert events[1].data[ATTR_ACTIVE_SOC_LIMIT] == 90.0


# --- Task 5.2: deadline resolution, required-current/urgency, baseline-mode comparison ---


async def test_urgency_engages_when_required_current_exceeds_baseline(hass, freezer):
    """Manual profile: baseline is simply the manually selected mode's own desired current
    (Power's target_current here) -- a required current above it is urgent (R5)."""
    freezer.move_to("2026-01-15 12:00:00")  # fixed, away from midnight (no rollover semantics)
    adapters = _adapters(status=STATE_CHARGING, ev_soc=79.0)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 2.0  # well below the ~3.26 A the deadline below will require
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is True
    assert coord._required_current.unreachable is False


async def test_urgency_reverts_when_baseline_alone_would_meet_the_deadline(hass, freezer):
    """Same deadline as above, but Power's own target current already exceeds what's
    required -- urgency never engages (R16's revert case)."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=79.0)
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 5.0  # above the ~3.26 A the deadline below requires
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is False


async def test_baseline_comparison_uses_rows_3_5_not_the_escalated_mode(hass, freezer):
    """Regression per resolution-rules.md's own warning: comparing against Captar's own
    (already-maximum) desired current would make urgency look satisfied instantly and
    revert every cycle -- this test drives that exact scenario and asserts urgency holds."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=78.0, sun_state="above_horizon")
    config = _config()
    config[CONF_SOLAR_INSTALLED] = False
    config[CONF_CAPTAR_AVAILABLE] = DEFAULT_CAPTAR_AVAILABLE
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_CAPTAR  # already escalated from a prior cycle
    coord.soc_limit_override = 80.0
    # No solar capability and sun up -> Auto's own baseline (rows 3-5, urgent=False) falls
    # through to Off, not Captar -- the required current below (~3.26 A) only exceeds a
    # baseline of 0 A, never Captar's own (already-maximum, 16 A) desired current.
    _seed_today_deadline(coord, hours_from_now=2)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is True


async def test_tomorrow_deadline_resolved_disables_solar_reserve(hass):
    """The one-day-ahead deadline resolution feeds resolve_solar_reserve_active (R9's
    mutual-exclusivity clause)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0, sun_state="below_horizon")
    adapters[ROLE_SOLAR_FORECAST] = _FakeNumeric(20.0)  # above the 12 kWh default threshold
    config = _config()
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    coord.home_day_flag = True
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()
    assert result.active_soc_limit == 60.0  # DEFAULT_SOLAR_RESERVE_SOC -- reserve engaged

    # R14 row 3 (home_day_flag already True above) wins over the day-of-week default, so the
    # home-day override -- not departure_dow_defaults -- is what must resolve for the
    # one-day-ahead evaluation to stop returning "no deadline".
    coord.departure_home_day_override = dt_util.now().time()
    result = await coord._async_update_data()
    assert result.active_soc_limit == 80.0  # tomorrow deadline resolved -> reserve lifted


async def test_ev_battery_capacity_prefers_the_sensed_role_over_the_configured_value(hass, freezer):
    """R15: with `ev_battery_capacity` role mapped and reading 60.0 kWh, the required-current
    computation uses 60.0, not CONF_EV_BATTERY_CAPACITY_KWH's configured default."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    adapters[ROLE_EV_BATTERY_CAPACITY] = _FakeNumeric(60.0)
    config = _config()
    config[CONF_EV_BATTERY_CAPACITY_KWH] = 75.0
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    expected_required_a = (60.0 * 30 / 100 * 1000) / 3 / 230.0
    assert coord._required_current.required_a == pytest.approx(expected_required_a)


async def test_ev_battery_capacity_falls_back_to_configured_when_sensor_unavailable(hass, freezer):
    """R15: with the role mapped but currently reading None, the required-current
    computation falls back to CONF_EV_BATTERY_CAPACITY_KWH."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    adapters[ROLE_EV_BATTERY_CAPACITY] = _FakeNumeric(None)
    config = _config()
    config[CONF_EV_BATTERY_CAPACITY_KWH] = 75.0
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    expected_required_a = (75.0 * 30 / 100 * 1000) / 3 / 230.0
    assert coord._required_current.required_a == pytest.approx(expected_required_a)


async def test_deadline_unreachable_notified_fires_while_required_current_exceeds_max_rate(
    hass, freezer
):
    """R5/ADR-0011: DeadlineUnreachableNotified is published every cycle
    resolve_required_current's `unreachable` flag is True -- including re-firing on a
    later cycle that is still Unreachable, not only on the Normal/Urgent -> Unreachable
    transition edge (UC05's domain-events section)."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    config = _config()  # CONF_MAX_CURRENT=16.0
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)  # tight deadline -> required current >> 16 A
    _seed_ample_peak_headroom(coord)

    events = []
    hass.bus.async_listen(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, lambda event: events.append(event))

    await coord._async_update_data()
    assert len(events) == 1
    assert coord._required_current.unreachable is True
    assert events[0].data[ATTR_REQUIRED_CURRENT_A] == pytest.approx(
        coord._required_current.required_a
    )

    await coord._async_update_data()  # still Unreachable -- fires again, not just on the edge
    assert len(events) == 2


# --- ROLE_LOW_TARIFF (issue #376): Auto row 4's low-tariff input ---


async def test_low_tariff_defaults_active_when_role_unmapped(hass, freezer):
    """Glossary's own single-tariff default: with ROLE_LOW_TARIFF unmapped, row 4 behaves
    as though low_tariff_active is always True -- baseline selects Captar (16 A, exceeds
    the ~10.87 A the deadline below requires), so urgency never engages."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0, sun_state="below_horizon")
    config = _config()
    config[CONF_SOLAR_INSTALLED] = False
    config[CONF_CAPTAR_AVAILABLE] = DEFAULT_CAPTAR_AVAILABLE
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is False


async def test_low_tariff_inactive_withholds_baseline_row4(hass, freezer):
    """With ROLE_LOW_TARIFF mapped and reading False, row 4 never matches -- baseline
    falls through to Off (0 A), so the same deadline as above now reads urgent."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(
        status=STATE_CHARGING, ev_soc=70.0, sun_state="below_horizon", low_tariff=False
    )
    config = _config()
    config[CONF_SOLAR_INSTALLED] = False
    config[CONF_CAPTAR_AVAILABLE] = DEFAULT_CAPTAR_AVAILABLE
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is True


async def test_low_tariff_mapped_true_matches_default(hass, freezer):
    """A mapped ROLE_LOW_TARIFF reading True behaves the same as the unmapped default."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(
        status=STATE_CHARGING, ev_soc=70.0, sun_state="below_horizon", low_tariff=True
    )
    config = _config()
    config[CONF_SOLAR_INSTALLED] = False
    config[CONF_CAPTAR_AVAILABLE] = DEFAULT_CAPTAR_AVAILABLE
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is False
