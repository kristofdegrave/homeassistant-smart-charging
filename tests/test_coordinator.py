"""HA-harness tests for the control cycle (M1, ADR-0006/0007)."""

import pytest

from custom_components.smart_charging.const import MODE_OFF, MODE_POWER, MODE_SOLAR, MODE_SOLAR_ONLY
from custom_components.smart_charging.coordinator import SmartChargingCoordinator
from custom_components.smart_charging.modes._amp_step import ROUND_DOWN
from custom_components.smart_charging.modes._phase import Phase


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
    status="charging", net_w=0.0, charger_w=0.0, voltage=230.0, ev_soc_role=True, ev_soc=50.0
):
    adapters = {
        "charger_current": _FakeNumeric(0.0),
        "charger_status": _FakeStatus(status),
        "net_power": _FakeNumeric(net_w),
        "charger_power": _FakeNumeric(charger_w),
        "grid_voltage": _FakeNumeric(voltage),
    }
    if ev_soc_role:
        adapters["ev_soc"] = _FakeNumeric(ev_soc)
    return adapters


def _config():
    return {
        "min_current": 6.0,
        "max_current": 16.0,
        "grid_ceiling_a": 25.0,
        "grid_safety_offset_a": 2.0,
        "nominal_voltage": 230.0,
        "smoothing_window": 1,
        "solar_start_threshold_w": 100.0,
        "solar_only_start_threshold_w": 100.0,
        "solar_hold_min": 5.0,
        "solar_cooldown_min": 2.0,
        "solar_only_strategy": ROUND_DOWN,
        "solar_only_midpoint": 0.5,
    }


async def _run(hass, adapters, config, target):
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.active_mode = MODE_POWER  # M1's original default before mode selection existed (Task 5.1)
    coord.target_current = target
    result = await coord._async_update_data()
    return coord, result


async def _run_mode(hass, adapters, config, active_mode, soc_limit_override=80.0, coord=None):
    if coord is None:
        coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    else:
        coord._adapters = adapters
    coord.active_mode = active_mode
    coord.soc_limit_override = soc_limit_override
    result = await coord._async_update_data()
    return coord, result


async def test_r17_commands_target_when_charging(hass):
    adapters = _adapters(status="charging")
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert adapters["charger_current"].written == [10.0]
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_uc04_zero_when_disconnected(hass):
    adapters = _adapters(status="disconnected")
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.commanded_current == 0.0
    assert result.fault is False
    assert adapters["charger_current"].written == [0.0]


async def test_c4_grid_ceiling_clamps_command(hass):
    # baseline = net 5980 - charger 3680 = 2300 W = 10 A;
    # headroom = (ceiling 25 - offset 2) - 10 = 13 A.
    adapters = _adapters(status="charging", net_w=5980.0, charger_w=3680.0)
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
    adapters = _adapters(status="charging")
    adapters[role] = _FakeNumeric(None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters["charger_current"].written == [0.0]


async def test_adr0007_cycle_exception_is_fault_and_forces_zero(hass):
    adapters = _adapters(status="charging")
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

    adapters["charger_status"] = _FakeStatus("charging")
    result = await coord._async_update_data()
    assert result.fault is False
    assert coord._was_faulted is False


async def test_nf4_grid_voltage_none_is_not_fault(hass):
    adapters = _adapters(status="charging")
    adapters["grid_voltage"] = _FakeNumeric(None)  # NF4 fallback, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_nf4_grid_voltage_unmapped_is_not_fault(hass):
    adapters = _adapters(status="charging")
    del adapters["grid_voltage"]  # role not configured -> nominal voltage, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_dispatches_to_solar_when_selected(hass):
    # surplus = charger_w(2760=12A) - net_w(0) = 2760W = 12A ideal, round-up -> 12A.
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)
    assert result.fault is False
    assert result.commanded_current == 12.0
    assert result.active_mode == MODE_SOLAR


async def test_dispatches_to_solar_only_when_selected(hass):
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_SOLAR_ONLY, soc_limit_override=80.0
    )
    assert result.fault is False
    assert result.commanded_current == 12.0
    assert result.active_mode == MODE_SOLAR_ONLY


@pytest.mark.parametrize("mode", [MODE_SOLAR, MODE_SOLAR_ONLY])
async def test_soc_at_or_above_limit_forces_zero_and_holds_solar_states_at_idle(hass, mode):
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=80.0)
    coord, result = await _run_mode(hass, adapters, _config(), mode, soc_limit_override=80.0)
    assert result.commanded_current == 0.0
    assert coord._mode_state[mode].phase == Phase.IDLE


async def test_resumes_when_the_soc_limit_rises_above_current_soc(hass):
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=80.0)
    coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)
    assert result.commanded_current == 0.0  # gated: ev_soc >= limit

    # R7 resume condition 1: the limit rises above the current SOC, same mode, no reconnect.
    coord, result = await _run_mode(
        hass, adapters, _config(), MODE_SOLAR, soc_limit_override=90.0, coord=coord
    )
    assert result.commanded_current == 12.0


async def test_resumes_after_disconnect_and_reconnect_while_still_at_the_limit(hass):
    config = _config()
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Gated at the limit.
    coord, result = await _run_mode(hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0)
    assert result.commanded_current == 0.0

    # Disconnect -> every mode's state resets to idle (existing R11 reset path).
    adapters = _adapters(status="disconnected", net_w=0.0, charger_w=2760.0, ev_soc=85.0)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )
    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_SOLAR].phase == Phase.IDLE

    # Reconnect while still at the limit -- gate still holds, no stuck Hold/Cooldown either.
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=85.0)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )
    assert result.commanded_current == 0.0

    # SOC finally drops below the limit -- resumes immediately, proving nothing was left
    # latched by the disconnect/reconnect cycle.
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=70.0)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )
    assert result.commanded_current == 12.0


@pytest.mark.parametrize("mode", [MODE_POWER, MODE_OFF])
async def test_power_and_off_ignore_soc_entirely(hass, mode):
    # No ev_soc role configured at all -- Power/Off must not regress to needing one.
    adapters = _adapters(status="charging", net_w=0.0, charger_w=0.0, ev_soc_role=False)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=_config(), interval_s=30)
    coord.active_mode = mode
    coord.soc_limit_override = 80.0
    coord.target_current = 10.0
    result = await coord._async_update_data()
    assert result.fault is False
    assert result.commanded_current == (10.0 if mode == MODE_POWER else 0.0)


async def test_missing_ev_soc_faults_only_while_a_solar_mode_is_selected(hass):
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc_role=False)
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)
    assert result.fault is True
    assert result.commanded_current == 0.0

    adapters = _adapters(status="charging", net_w=0.0, charger_w=0.0, ev_soc_role=False)
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=_config(), interval_s=30)
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0
    result = await coord._async_update_data()
    assert result.fault is False


async def test_disconnect_with_unavailable_ev_soc_is_a_clean_stop_not_a_fault(hass):
    """A disconnected car is always a clean idle stop (UC01/R7), even when its own SOC
    sensor also goes unavailable on unplug -- ev_soc is only required while the car is
    both connected and a solar mode is active."""
    adapters = _adapters(status="disconnected", net_w=0.0, charger_w=0.0, ev_soc_role=False)
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)
    assert result.fault is False
    assert result.commanded_current == 0.0


async def test_mode_switch_resets_the_incoming_modes_state(hass):
    config = _config()
    config["solar_hold_min"] = 0.0  # Hold -> Cooldown transitions on the very next cycle
    config["solar_cooldown_min"] = 5.0  # long enough that real test wall-clock never clears it

    ample = _adapters(status="charging", net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    idle_surplus = _adapters(status="charging", net_w=0.0, charger_w=0.0, ev_soc=50.0)

    coord, result = await _run_mode(hass, ample, config, MODE_SOLAR, soc_limit_override=80.0)
    assert result.commanded_current == 12.0  # charging

    coord, result = await _run_mode(
        hass, idle_surplus, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )
    assert result.commanded_current == 6.0  # hold, floored at min_a

    coord, result = await _run_mode(
        hass, idle_surplus, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )
    assert result.commanded_current == 0.0  # cooldown
    assert coord._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN

    # Switch away and back -- both transitions reset _mode_state (R11).
    coord, result = await _run_mode(
        hass, ample, config, MODE_OFF, soc_limit_override=80.0, coord=coord
    )
    coord, result = await _run_mode(
        hass, ample, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )
    assert result.commanded_current == 12.0  # fresh idle -> charges immediately, no cooldown wait


async def test_grid_ceiling_still_clamps_a_solar_request(hass):
    config = _config()
    config["grid_ceiling_a"] = 2.0
    config["grid_safety_offset_a"] = 2.0  # ceiling - offset == 0
    # surplus = 2645W = 11.5A ideal; Solar rounds up -> 12A pre-clamp.
    # headroom = floor(0 + 11.5) = 11A -> clamped from 12A to 11A.
    adapters = _adapters(status="charging", net_w=0.0, charger_w=2645.0, ev_soc=50.0)
    _coord, result = await _run_mode(hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0)
    assert result.commanded_current == 11.0


async def test_power_mode_behavior_unchanged(hass):
    adapters = _adapters(status="charging")
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0
    assert result.active_mode == MODE_POWER
