"""HA-harness test for the Fault/OK status sensor (ADR-0007) and the active-mode sensor."""

from types import SimpleNamespace

from custom_components.smart_charging.sensor import ActiveModeSensor, ChargingStatusSensor


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


def test_active_mode_unique_id_scoped_to_entry():
    coord = SimpleNamespace(data=None)
    sensor = ActiveModeSensor(entry_id="abc", coordinator=coord)
    assert sensor.unique_id == "abc_active_mode"
