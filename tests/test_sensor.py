"""HA-harness test for the Fault/OK status sensor (ADR-0007), the active-mode sensor, and
the peak-protection diagnostic sensors (C3)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, Platform, UnitOfPower
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging import sensor as sensor_module
from custom_components.smart_charging.const import (
    ATTR_PERIOD_MONTH,
    CONF_DEADLINE_AVAILABLE,
    CONF_NOTIFICATIONS_AVAILABLE,
    CONF_SOLAR_AVAILABLE,
    DEFAULT_DEADLINE_AVAILABLE,
    DEFAULT_NOTIFICATIONS_AVAILABLE,
    DOMAIN,
    OWNED_SUFFIX_SOLAR_SURPLUS_W,
    STATUS_FAULT,
    STATUS_OK,
)
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
    _ConfigMirrorSensor,
    _ConfigMirrorSpec,
    _format_mirror_value,
)
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

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


async def test_status_raises_when_coordinator_data_lacks_fault_field(hass):
    """Direct attribute access (issue #565): a renamed/removed `fault` field on
    `CycleResult` must raise `AttributeError`, not silently report OK."""
    coord = SimpleNamespace(data=SimpleNamespace())
    sensor = ChargingStatusSensor(entry_id="abc", coordinator=coord)
    with pytest.raises(AttributeError):
        _ = sensor.native_value


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


@pytest.mark.parametrize(
    "sensor_cls",
    [
        ActiveModeSensor,
        EffectivePeakLimitSensor,
        ActiveSocLimitSensor,
        SolarSurplusSensor,
        PeakHeadroomSensor,
        TimeToFullSensor,
    ],
)
async def test_coordinator_field_sensor_raises_when_data_lacks_its_field(hass, sensor_cls):
    """Direct attribute access (issue #565): every `_CoordinatorFieldSensor` subclass must
    raise `AttributeError` when its CycleResult field is renamed/removed, instead of
    silently falling back to `_field_default`."""
    coord = SimpleNamespace(data=SimpleNamespace())
    sensor = sensor_cls(entry_id="abc", coordinator=coord)
    with pytest.raises(AttributeError):
        _ = sensor.native_value


@pytest.mark.parametrize(
    "sensor_cls, device_class, unit",
    [
        (MonthlyPeakSensor, SensorDeviceClass.POWER, "kW"),
        (EffectivePeakLimitSensor, SensorDeviceClass.POWER, "kW"),
        (SolarSurplusSensor, SensorDeviceClass.POWER, "W"),
        (PeakHeadroomSensor, SensorDeviceClass.CURRENT, "A"),
    ],
)
def test_diagnostic_sensor_has_statistics_and_diagnostic_classification(
    sensor_cls, device_class, unit
):
    """#649: without device_class/state_class HA records no long-term statistics for these
    sensors; each one's own docstring calls itself diagnostic, so entity_category must
    match. The unit is pinned alongside device_class since HA statistics only make sense
    for a unit/device_class pair that agree."""
    coord = SimpleNamespace(data=None)
    sensor = sensor_cls(entry_id="abc", coordinator=coord)
    assert sensor.device_class == device_class
    assert sensor.native_unit_of_measurement == unit
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


async def test_monthly_peak_sensor_is_registered_with_valid_statistics_metadata(hass):
    """Platform-level guard (code-reviewer finding on #649): asserting the bare class
    attributes cannot catch an invalid unit/device_class/state_class combination, since
    HA only validates that triple when the entity's state is actually written. Registering
    through a real platform confirms HA accepts it."""
    coord = _StubPeakCoordinator(data=SimpleNamespace(monthly_peak_kw=3.4))
    coord.last_update_success = True
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    entity_id = "sensor.smart_charging_monthly_peak_kw"
    sensor.entity_id = entity_id
    platform = MockEntityPlatform(hass, domain="sensor")
    await platform.async_add_entities([sensor])

    state = hass.states.get(entity_id)
    assert state.attributes["device_class"] == SensorDeviceClass.POWER
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT
    assert state.attributes["unit_of_measurement"] == "kW"


async def test_monthly_peak_sensor_reflects_the_tracked_value(hass):
    coord = SimpleNamespace(data=SimpleNamespace(monthly_peak_kw=3.4))
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 3.4


async def test_monthly_peak_sensor_defaults_to_zero_when_no_data_yet(hass):
    coord = SimpleNamespace(data=None)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.native_value == 0.0


async def test_monthly_peak_sensor_raises_when_coordinator_data_lacks_field(hass):
    """Direct attribute access (issue #565): a renamed/removed `monthly_peak_kw` field on
    `CycleResult` must raise `AttributeError` instead of silently reporting 0.0."""
    coord = SimpleNamespace(data=SimpleNamespace())
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    with pytest.raises(AttributeError):
        _ = sensor.native_value


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
                    ATTR_PERIOD_MONTH: "2026-07",
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
    assert sensor.extra_state_attributes == {ATTR_PERIOD_MONTH: "2026-07"}


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
                    ATTR_PERIOD_MONTH: "not-a-month",
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
    assert sensor.extra_state_attributes == {ATTR_PERIOD_MONTH: None}


async def test_monthly_peak_sensor_extra_state_attributes_reflect_live_coordinator_month(hass):
    """period_month must not freeze at the value restored on startup -- a mid-run month
    rollover the coordinator tracks needs to show up in the exposed attribute too."""
    coord = _StubPeakCoordinator()
    coord._peak_demand.tracked_month = (2026, 7)
    sensor = MonthlyPeakSensor(entry_id="abc", coordinator=coord)
    assert sensor.extra_state_attributes == {ATTR_PERIOD_MONTH: "2026-07"}
    coord._peak_demand.tracked_month = (2026, 8)
    assert sensor.extra_state_attributes == {ATTR_PERIOD_MONTH: "2026-08"}


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
    """`_CoordinatorFieldSensor`'s `_field_default` only substitutes when there is no cycle
    result yet (`coordinator.data is None`), never when the field is present as 0 (#602 T3)."""
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


async def test_solar_surplus_sensor_disabled_by_default_when_solar_unavailable(hass):
    """ADR-0028: a fresh install with solar_available=False registers the sensor disabled."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_SOLAR_SURPLUS_W}"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_solar_surplus_sensor_enabled_when_solar_available(hass):
    """ADR-0028: solar_available=True registers the sensor enabled."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_SOLAR_AVAILABLE] = True
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_SOLAR_SURPLUS_W}"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is None


async def test_solar_surplus_sensor_reenables_on_reload_when_capability_returns(hass):
    """ADR-0028: a reload (ADR-0008) with solar_available flipped to True clears disabled_by
    on the entity that already exists in the registry from the prior (disabled) setup, and the
    entity is live again (design doc §5: not just a registry-field flip)."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_SOLAR_SURPLUS_W}"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None

    data = entry_data_base()
    data[CONF_SOLAR_AVAILABLE] = True
    hass.config_entries.async_update_entry(entry, data=data)
    await hass.async_block_till_done()

    assert registry.async_get(entity_id).disabled_by is None
    assert hass.states.get(entity_id) is not None


async def test_solar_surplus_sensor_disables_on_reload_when_capability_removed(hass):
    """ADR-0028: reverse of the above -- a reload with solar_available flipped to False
    disables the previously-enabled entity and removes it from hass (design doc §5)."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_SOLAR_AVAILABLE] = True
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_SOLAR_SURPLUS_W}"
    )
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is None
    assert hass.states.get(entity_id) is not None

    off_data = entry_data_base()
    off_data[CONF_SOLAR_AVAILABLE] = False
    hass.config_entries.async_update_entry(entry, data=off_data)
    await hass.async_block_till_done()

    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    # A previously-live entity leaves a restored/unavailable ghost state behind on removal
    # rather than disappearing from the state machine outright -- unlike the sibling test's
    # fresh-install case (never live, so genuinely no state at all).
    disabled_state = hass.states.get(entity_id)
    assert disabled_state is None or disabled_state.state == STATE_UNAVAILABLE


async def test_solar_surplus_sensor_config_read_matches_other_platforms(hass):
    """Regression guard (design doc §3.1): async_setup_entry must resolve solar_available via
    entry.data.get(CONF_SOLAR_AVAILABLE, ...) -- the same pattern select.py/time.py already use
    -- and NOT via entry.runtime_data.coordinator._config, a private Client->Manager access
    path no platform file uses today. Rigs entry.data and a stubbed private attribute to
    disagree and captures the exact `capability_met` sync_disabled_by is called with (not just
    the constructor argument), so reading either the constructor OR the disabled_by sync from
    the wrong source flips this assertion."""
    captured_entities = []
    captured_calls = []

    def _capture(entities):
        captured_entities.extend(entities)

    def _fake_sync_disabled_by(registry, domain, unique_id, *, capability_met):
        captured_calls.append(capability_met)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sensor_module, "sync_disabled_by", _fake_sync_disabled_by)
    try:
        entry = SimpleNamespace(
            entry_id="entry1",
            data={CONF_SOLAR_AVAILABLE: True},
            runtime_data=SimpleNamespace(
                coordinator=SimpleNamespace(_config=SimpleNamespace(solar_available=False)),
                config=SimpleNamespace(solar_available=False, captar_available=False),
            ),
        )

        await sensor_module.async_setup_entry(hass, entry, _capture)
    finally:
        monkeypatch.undo()

    solar_sensor = next(e for e in captured_entities if isinstance(e, SolarSurplusSensor))
    assert solar_sensor.entity_registry_enabled_default is True
    assert captured_calls == [True]


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


def test_active_soc_limit_sensor_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = ActiveSocLimitSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_active_soc_limit"


# --- Config-mirror diagnostic sensors (ADR-0031, #888) -------------------------------------


def test_format_mirror_value_maps_bool_to_state_on_off_else_passthrough():
    assert _format_mirror_value(True) == STATE_ON
    assert _format_mirror_value(False) == STATE_OFF
    assert _format_mirror_value(4.0) == 4.0
    assert _format_mirror_value("round_down") == "round_down"


def test_config_mirror_sensor_reads_from_its_spec():
    """A _ConfigMirrorSensor holds its value verbatim from the spec (resolved once by
    async_setup_entry, never re-read) -- pinned to a non-bool value since _format_mirror_value
    changes a bool's own representation (see test above), so `native_value == spec.value` would
    be false for a bool spec."""
    spec = _ConfigMirrorSpec(
        object_id_suffix="grid_supply_ceiling_a",
        unit=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        value=4.0,
    )
    sensor = _ConfigMirrorSensor(entry_id="abc", spec=spec)

    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.entity_registry_enabled_default is False
    assert sensor.unique_id == "abc_grid_supply_ceiling_a"
    assert sensor.translation_key == "grid_supply_ceiling_a"
    assert sensor.native_value == 4.0
    assert sensor.native_unit_of_measurement == UnitOfPower.WATT
    assert sensor.device_class == SensorDeviceClass.POWER


def test_config_mirror_sensor_formats_a_bool_spec_value():
    spec = _ConfigMirrorSpec(
        object_id_suffix="power_respect_peak", unit=None, device_class=None, value=True
    )
    sensor = _ConfigMirrorSensor(entry_id="abc", spec=spec)
    assert sensor.native_value == STATE_ON


async def test_async_setup_entry_registers_capability_config_mirror_sensors(hass):
    """Proves both non-options source buckets in one setup call: solar_available/
    captar_available come off entry.runtime_data.config (they ARE SmartChargingConfig fields);
    deadline_available/notifications_available come off entry.data directly (they are NOT --
    entity-catalog.md/#888's design doc)."""
    captured_entities = []

    def _capture(entities):
        captured_entities.extend(entities)

    entry = SimpleNamespace(
        entry_id="entry1",
        data={
            CONF_SOLAR_AVAILABLE: True,
            CONF_DEADLINE_AVAILABLE: False,
            CONF_NOTIFICATIONS_AVAILABLE: True,
        },
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(_config=SimpleNamespace(solar_available=True)),
            config=SimpleNamespace(solar_available=True, captar_available=False),
        ),
    )

    await sensor_module.async_setup_entry(hass, entry, _capture)

    mirrors = {
        e._object_id_suffix: e for e in captured_entities if isinstance(e, _ConfigMirrorSensor)
    }
    assert mirrors["solar_available"].native_value == STATE_ON
    assert mirrors["captar_available"].native_value == STATE_OFF
    assert mirrors["deadline_available"].native_value == STATE_OFF
    assert mirrors["notifications_available"].native_value == STATE_ON


async def test_async_setup_entry_registers_capability_config_mirror_sensors_all_off(hass):
    """The inverse-value companion to the test above -- an all-off entry, so neither test could
    pass by coincidentally reading the same source bucket's default for both cases."""
    captured_entities = []

    def _capture(entities):
        captured_entities.extend(entities)

    entry = SimpleNamespace(
        entry_id="entry1",
        data={},  # DEFAULT_DEADLINE_AVAILABLE is True -- this alone would NOT prove the read
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(_config=SimpleNamespace(solar_available=False)),
            config=SimpleNamespace(solar_available=False, captar_available=False),
        ),
    )

    await sensor_module.async_setup_entry(hass, entry, _capture)

    mirrors = {
        e._object_id_suffix: e for e in captured_entities if isinstance(e, _ConfigMirrorSensor)
    }
    assert mirrors["solar_available"].native_value == STATE_OFF
    assert mirrors["captar_available"].native_value == STATE_OFF
    # entry.data has neither key -- both must fall back to their own DEFAULT_*, not each other's.
    assert mirrors["deadline_available"].native_value == _format_mirror_value(
        DEFAULT_DEADLINE_AVAILABLE
    )
    assert mirrors["notifications_available"].native_value == _format_mirror_value(
        DEFAULT_NOTIFICATIONS_AVAILABLE
    )
