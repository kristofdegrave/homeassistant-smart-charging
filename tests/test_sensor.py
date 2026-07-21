"""HA-harness test for the Fault/OK status sensor (ADR-0007), the active-mode sensor, and
the peak-protection diagnostic sensors (C3)."""

from types import SimpleNamespace

from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.sensor import (
    ActiveModeSensor,
    ChargingStatusSensor,
    EffectivePeakLimitSensor,
    MonthlyPeakSensor,
)


async def test_status_reflects_fault_flag(hass):
    coord = SimpleNamespace(data=SimpleNamespace(fault=True))
    sensor = ChargingStatusSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == "Fault"
    coord.data = SimpleNamespace(fault=False)
    assert sensor.native_value == "OK"


async def test_status_defaults_to_ok_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = ChargingStatusSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == "OK"


def test_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = ChargingStatusSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_status"


async def test_active_mode_reflects_last_cycle_result(hass):
    coord = SimpleNamespace(data=SimpleNamespace(active_mode="Solar"))
    sensor = ActiveModeSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == "Solar"
    coord.data = SimpleNamespace(active_mode="Power")
    assert sensor.native_value == "Power"


async def test_active_mode_defaults_to_off_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = ActiveModeSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == "Off"


async def test_active_mode_defaults_to_off_when_coordinator_data_lacks_field(hass):
    """Today's CycleResult has no active_mode field yet (added in Task 5.1)."""
    coord = SimpleNamespace(data=SimpleNamespace())
    sensor = ActiveModeSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == "Off"


async def test_monthly_peak_sensor_reflects_the_tracked_value(hass):
    coord = SimpleNamespace(data=SimpleNamespace(monthly_peak_kw=3.4))
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 3.4


async def test_monthly_peak_sensor_defaults_to_zero_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 0.0


async def test_monthly_peak_sensor_defaults_to_zero_when_coordinator_data_lacks_field(hass):
    """Today's CycleResult has no monthly_peak_kw field yet (added in Task 5.1)."""
    coord = SimpleNamespace(data=SimpleNamespace())
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 0.0


async def test_monthly_peak_sensor_restores_value_and_period_across_restart(hass):
    """A restored kW value + `period_month` attribute seeds the coordinator's Peak-Demand
    Tracker instead of it starting cold at 0 kW across a restart (design doc Sec 6.4)."""
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    mock_restore_cache_with_extra_data(
        hass, ((State(entity_id, "3.4", {"period_month": [2026, 7]}), None),)
    )
    coord = SimpleNamespace(data=None)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    sensor.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([sensor])

    assert sensor.native_value == 3.4
    assert coord._peak_tracked_kw == 3.4
    assert coord._peak_tracked_month == (2026, 7)
    assert coord._peak_window == (3.4,)


async def test_monthly_peak_sensor_starts_cold_when_no_restored_state(hass):
    coord = SimpleNamespace(data=None)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    sensor.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([sensor])

    assert sensor.native_value == 0.0
    assert getattr(coord, "_peak_tracked_kw", None) is None


def test_monthly_peak_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_monthly_peak_kw"


async def test_effective_peak_limit_sensor_reflects_the_resolved_value(hass):
    coord = SimpleNamespace(data=SimpleNamespace(effective_peak_limit_kw=4.0))
    sensor = EffectivePeakLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 4.0


async def test_effective_peak_limit_sensor_defaults_to_none_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = EffectivePeakLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None


def test_effective_peak_limit_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = EffectivePeakLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_effective_peak_limit"


def test_active_mode_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = ActiveModeSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_active_mode"
