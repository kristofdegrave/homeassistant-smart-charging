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
    ActiveSocLimitSensor,
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


class _StubPeakCoordinator:
    """Minimal CoordinatorEntity-compatible stub -- `async_add_listener` is required by
    CoordinatorEntity.async_added_to_hass, which the restore-path tests below exercise."""

    def __init__(self, data=None):
        self.data = data

    def async_add_listener(self, update_callback, context=None):
        return lambda: None


async def test_monthly_peak_sensor_restores_value_and_period_across_restart(hass):
    """A restored kW value + `period_month` attribute seeds the coordinator's Peak-Demand
    Tracker's (tracked_kw, tracked_month) across a restart (design doc Sec 6.4) -- the
    15-minute smoothing window is deliberately NOT seeded (Sec 6.4: rebuilds from scratch)."""
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, "3.4"),
                {
                    "native_value": 3.4,
                    "native_unit_of_measurement": "kW",
                    "period_month": "2026-07",
                },
            ),
        ),
    )
    coord = _StubPeakCoordinator()
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    sensor.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([sensor])

    assert sensor.native_value == 3.4
    assert coord._peak_tracked_kw == 3.4
    assert coord._peak_tracked_month == (2026, 7)
    assert not hasattr(coord, "_peak_window")
    assert sensor.extra_state_attributes == {"period_month": "2026-07"}


async def test_monthly_peak_sensor_starts_cold_when_no_restored_state(hass):
    coord = _StubPeakCoordinator()
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    sensor.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([sensor])

    assert sensor.native_value == 0.0
    assert getattr(coord, "_peak_tracked_kw", None) is None
    assert sensor.extra_state_attributes == {"period_month": None}


async def test_monthly_peak_sensor_extra_state_attributes_reflect_live_coordinator_month(hass):
    """period_month must not freeze at the value restored on startup -- a mid-run month
    rollover the coordinator tracks needs to show up in the exposed attribute too."""
    coord = _StubPeakCoordinator()
    coord._peak_tracked_month = (2026, 7)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.extra_state_attributes == {"period_month": "2026-07"}
    coord._peak_tracked_month = (2026, 8)
    assert sensor.extra_state_attributes == {"period_month": "2026-08"}


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


async def test_active_soc_limit_sensor_reflects_the_resolved_value(hass):
    """After a cycle, sensor.smart_charging_active_soc_limit's native_value equals the
    coordinator's resolved R7 value this cycle."""
    coord = SimpleNamespace(data=SimpleNamespace(active_soc_limit=80.0))
    sensor = ActiveSocLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 80.0

    coord.data = SimpleNamespace(active_soc_limit=60.0)
    assert sensor.native_value == 60.0


async def test_active_soc_limit_sensor_defaults_to_none_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = ActiveSocLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None


async def test_active_soc_limit_sensor_defaults_to_none_when_coordinator_data_lacks_field(hass):
    coord = SimpleNamespace(data=SimpleNamespace())
    sensor = ActiveSocLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None


def test_active_soc_limit_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = ActiveSocLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_active_soc_limit"
