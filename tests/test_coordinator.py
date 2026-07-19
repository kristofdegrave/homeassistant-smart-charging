"""HA-harness tests for the control cycle (M1, ADR-0006/0007)."""

import pytest

from custom_components.smart_charging.coordinator import SmartChargingCoordinator


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


def _adapters(status="charging", net_w=0.0, charger_w=0.0, voltage=230.0):
    return {
        "charger_current": _FakeNumeric(0.0),
        "charger_status": _FakeStatus(status),
        "net_power": _FakeNumeric(net_w),
        "charger_power": _FakeNumeric(charger_w),
        "grid_voltage": _FakeNumeric(voltage),
    }


def _config():
    return {
        "min_current": 6.0,
        "max_current": 16.0,
        "grid_ceiling_a": 25.0,
        "grid_safety_offset_a": 2.0,
        "nominal_voltage": 230.0,
    }


async def _run(hass, adapters, config, target):
    coord = SmartChargingCoordinator(hass, adapters=adapters, config=config, interval_s=30)
    coord.target_current = target
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
