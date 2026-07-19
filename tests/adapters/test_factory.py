"""HA-harness tests for the adapter factory (ADR-0003)."""

from custom_components.smart_charging.adapters.factory import build_adapters
from custom_components.smart_charging.adapters.numeric import (
    NumericReadAdapter,
    NumericReadWriteAdapter,
)
from custom_components.smart_charging.adapters.status import StatusAdapter
from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_NET_POWER_ENTITY,
    CONF_STATUS_TRANSLATION,
)


def _data():
    return {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
        CONF_STATUS_TRANSLATION: {"Charging": "charging"},
        CONF_NET_POWER_ENTITY: "sensor.net_power",
        CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    }


async def test_factory_builds_expected_roles(hass):
    adapters = build_adapters(hass, _data())
    assert isinstance(adapters["charger_current"], NumericReadWriteAdapter)
    assert isinstance(adapters["charger_status"], StatusAdapter)
    assert isinstance(adapters["net_power"], NumericReadAdapter)
    assert isinstance(adapters["charger_power"], NumericReadAdapter)
    assert isinstance(adapters["grid_voltage"], NumericReadAdapter)


async def test_grid_voltage_optional(hass):
    data = _data()
    del data[CONF_GRID_VOLTAGE_ENTITY]
    adapters = build_adapters(hass, data)
    assert "grid_voltage" not in adapters
