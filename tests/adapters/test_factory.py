"""HA-harness tests for the adapter factory (ADR-0003)."""

import pytest

from custom_components.smart_charging.adapters.factory import build_adapters
from custom_components.smart_charging.adapters.numeric import (
    NumericReadAdapter,
    NumericReadWriteAdapter,
)
from custom_components.smart_charging.adapters.status import StatusReadAdapter
from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_NET_POWER_ENTITY,
    CONF_STATUS_TRANSLATION,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_NET_POWER,
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

    assert isinstance(adapters[ROLE_CHARGER_CURRENT], NumericReadWriteAdapter)
    assert adapters[ROLE_CHARGER_CURRENT]._entity_id == "number.charger_current"

    assert isinstance(adapters[ROLE_CHARGER_STATUS], StatusReadAdapter)
    assert adapters[ROLE_CHARGER_STATUS]._entity_id == "sensor.evse"
    assert adapters[ROLE_CHARGER_STATUS]._translation == {"Charging": "charging"}

    assert isinstance(adapters[ROLE_NET_POWER], NumericReadAdapter)
    assert adapters[ROLE_NET_POWER]._entity_id == "sensor.net_power"

    assert isinstance(adapters[ROLE_CHARGER_POWER], NumericReadAdapter)
    assert adapters[ROLE_CHARGER_POWER]._entity_id == "sensor.charger_power"

    assert isinstance(adapters[ROLE_GRID_VOLTAGE], NumericReadAdapter)
    assert adapters[ROLE_GRID_VOLTAGE]._entity_id == "sensor.grid_voltage"


async def test_grid_voltage_optional(hass):
    data = _data()
    del data[CONF_GRID_VOLTAGE_ENTITY]
    adapters = build_adapters(hass, data)
    assert ROLE_GRID_VOLTAGE not in adapters


async def test_grid_voltage_empty_string_treated_as_absent(hass):
    data = _data()
    data[CONF_GRID_VOLTAGE_ENTITY] = ""
    adapters = build_adapters(hass, data)
    assert ROLE_GRID_VOLTAGE not in adapters


async def test_missing_required_role_raises_key_error(hass):
    data = _data()
    del data[CONF_CHARGER_CURRENT_ENTITY]
    with pytest.raises(KeyError):
        build_adapters(hass, data)


async def test_factory_builds_ev_soc_role_when_configured(hass):
    data = _data()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    adapters = build_adapters(hass, data)
    assert isinstance(adapters[ROLE_EV_SOC], NumericReadAdapter)
    assert adapters[ROLE_EV_SOC]._entity_id == "sensor.ev_soc"


async def test_ev_soc_role_absent_when_not_configured(hass):
    # An existing Power-MVP entry predates this field entirely (design doc §8/§9) --
    # build_adapters must not KeyError on it.
    adapters = build_adapters(hass, _data())
    assert ROLE_EV_SOC not in adapters


async def test_ev_soc_empty_string_treated_as_absent(hass):
    data = _data()
    data[CONF_EV_SOC_ENTITY] = ""
    adapters = build_adapters(hass, data)
    assert ROLE_EV_SOC not in adapters
