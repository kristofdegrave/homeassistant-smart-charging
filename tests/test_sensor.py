"""HA-harness test for the Fault/OK status sensor (ADR-0007), the active-mode sensor, and
the peak-protection diagnostic sensors (C3)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import State
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import (
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.const import STATUS_FAULT, STATUS_OK
from custom_components.smart_charging.coordinator_cycle import PeakDemandState
from custom_components.smart_charging.sensor import (
    ActiveModeSensor,
    ActiveSocLimitSensor,
    AdapterReadingsSensor,
    ChargingStatusSensor,
    EffectivePeakLimitSensor,
    MonthlyPeakSensor,
    PeakHeadroomSensor,
    SolarSurplusSensor,
    TimeToFullSensor,
)

_ADAPTER_READINGS_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


async def test_status_reflects_fault_flag(hass):
    coord = SimpleNamespace(data=SimpleNamespace(fault=True))
    sensor = ChargingStatusSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == STATUS_FAULT
    coord.data = SimpleNamespace(fault=False)
    assert sensor.native_value == STATUS_OK


async def test_status_defaults_to_ok_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = ChargingStatusSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == STATUS_OK


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
    CoordinatorEntity.async_added_to_hass, which the restore-path tests below exercise.
    `seed_monthly_peak`/`monthly_peak_period_month` delegate to the real `PeakDemandState`
    (ADR-0012, #496) -- the sensor must call these instead of reaching into `_peak_demand`'s
    private fields directly, and the stub exercises the real semantics rather than a copy."""

    def __init__(self, data=None):
        self.data = data
        self._peak_demand = PeakDemandState()

    def async_add_listener(self, update_callback, context=None):
        return lambda: None

    def seed_monthly_peak(self, kw, month):
        self._peak_demand.seed(kw, month)

    @property
    def monthly_peak_period_month(self):
        return self._peak_demand.period_month


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
    assert coord._peak_demand.tracked_kw == 3.4
    assert coord._peak_demand.tracked_month == (2026, 7)
    assert coord._peak_demand.window == ()
    assert sensor.extra_state_attributes == {"period_month": "2026-07"}


async def test_monthly_peak_sensor_restores_kw_when_period_month_is_malformed(hass):
    """A malformed `period_month` (e.g. from a corrupted store) must not raise out of entity
    setup -- the kW value still restores, tracked_month is simply left untouched (#496)."""
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(entity_id, "3.4"),
                {
                    "native_value": 3.4,
                    "native_unit_of_measurement": "kW",
                    "period_month": "not-a-month",
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
    assert coord._peak_demand.tracked_kw == 3.4
    assert coord._peak_demand.tracked_month is None


async def test_monthly_peak_sensor_starts_cold_when_no_restored_state(hass):
    coord = _StubPeakCoordinator()
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    sensor.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([sensor])

    assert sensor.native_value == 0.0
    assert coord._peak_demand.tracked_kw == 0.0
    assert sensor.extra_state_attributes == {"period_month": None}


async def test_monthly_peak_sensor_extra_state_attributes_reflect_live_coordinator_month(hass):
    """period_month must not freeze at the value restored on startup -- a mid-run month
    rollover the coordinator tracks needs to show up in the exposed attribute too."""
    coord = _StubPeakCoordinator()
    coord._peak_demand.tracked_month = (2026, 7)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.extra_state_attributes == {"period_month": "2026-07"}
    coord._peak_demand.tracked_month = (2026, 8)
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


async def test_solar_surplus_sensor_reflects_the_resolved_value(hass):
    coord = SimpleNamespace(data=SimpleNamespace(solar_surplus_w=1200.0))
    sensor = SolarSurplusSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 1200.0


async def test_solar_surplus_sensor_defaults_to_none_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = SolarSurplusSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None


def test_solar_surplus_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = SolarSurplusSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_solar_surplus_w"


async def test_peak_headroom_sensor_reflects_the_resolved_value(hass):
    coord = SimpleNamespace(data=SimpleNamespace(peak_headroom_a=10.0))
    sensor = PeakHeadroomSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 10.0


async def test_peak_headroom_sensor_defaults_to_none_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = PeakHeadroomSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None


def test_peak_headroom_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = PeakHeadroomSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_peak_headroom_a"


async def test_time_to_full_sensor_reflects_the_resolved_value(hass):
    coord = SimpleNamespace(data=SimpleNamespace(time_to_full_min=42.0))
    sensor = TimeToFullSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 42.0


async def test_time_to_full_sensor_reflects_zero_as_a_real_value(hass):
    """`_CoordinatorFieldSensor`'s `_field_default` only substitutes when the attribute is
    absent, never when present as 0 -- confirms no bespoke class is needed (#602 T3)."""
    coord = SimpleNamespace(data=SimpleNamespace(time_to_full_min=0.0))
    sensor = TimeToFullSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 0.0


async def test_time_to_full_sensor_defaults_to_none_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = TimeToFullSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None


def test_time_to_full_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = TimeToFullSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_time_to_full"


async def test_adapter_readings_sensor_reflects_the_timestamp_and_attributes(hass):
    coord = SimpleNamespace(
        data=SimpleNamespace(
            adapter_readings_at=_ADAPTER_READINGS_AT,
            adapter_readings={"ev_soc": 50.0, "grid_voltage": None},
        )
    )
    sensor = AdapterReadingsSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == _ADAPTER_READINGS_AT
    assert sensor.extra_state_attributes == {"ev_soc": 50.0, "grid_voltage": None}
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP


async def test_adapter_readings_sensor_defaults_to_none_and_empty_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = AdapterReadingsSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_adapter_readings_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = AdapterReadingsSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_adapter_readings"


def test_adapter_readings_sensor_is_diagnostic():
    coord = SimpleNamespace(data=None)
    sensor = AdapterReadingsSensor(entry_id="abc", coordinator=coord)
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_all_sensor_object_id_suffixes_are_unique():
    """T6 integration checkpoint (#602): a static, independent guard for ADR-0013's
    per-entity object_id pin -- two sensor classes sharing an `_object_id_suffix` would
    collide at registration (HA's registry dedupes by unique_id), which the runtime
    `test_every_owned_entity_id_matches_entity_catalog` (test_init.py) would only catch
    indirectly, via a shrunk registered-entity count."""
    coord = SimpleNamespace(data=None)
    sensor_classes = [
        ChargingStatusSensor,
        ActiveModeSensor,
        MonthlyPeakSensor,
        EffectivePeakLimitSensor,
        ActiveSocLimitSensor,
        SolarSurplusSensor,
        PeakHeadroomSensor,
        TimeToFullSensor,
        AdapterReadingsSensor,
    ]
    suffixes = [cls(entry_id="abc", coordinator=coord)._object_id_suffix for cls in sensor_classes]
    assert len(suffixes) == len(set(suffixes))


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
