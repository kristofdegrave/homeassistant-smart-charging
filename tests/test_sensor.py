"""HA-harness test for the Fault/OK status sensor (ADR-0007)."""

from types import SimpleNamespace

from custom_components.smart_charging.sensor import ChargingStatusSensor


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
