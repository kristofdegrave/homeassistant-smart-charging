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
    assert adapters["charger_current"]._entity_id == "number.charger_current"

    assert isinstance(adapters["charger_status"], StatusReadAdapter)
    assert adapters["charger_status"]._entity_id == "sensor.evse"
    assert adapters["charger_status"]._translation == {"Charging": "charging"}

    assert isinstance(adapters["net_power"], NumericReadAdapter)
    assert adapters["net_power"]._entity_id == "sensor.net_power"

    assert isinstance(adapters["charger_power"], NumericReadAdapter)
    assert adapters["charger_power"]._entity_id == "sensor.charger_power"

    assert isinstance(adapters["grid_voltage"], NumericReadAdapter)
    assert adapters["grid_voltage"]._entity_id == "sensor.grid_voltage"


async def test_grid_voltage_optional(hass):
    data = _data()
    del data[CONF_GRID_VOLTAGE_ENTITY]
    adapters = build_adapters(hass, data)
    assert "grid_voltage" not in adapters


async def test_grid_voltage_empty_string_treated_as_absent(hass):
    data = _data()
    data[CONF_GRID_VOLTAGE_ENTITY] = ""
    adapters = build_adapters(hass, data)
    assert "grid_voltage" not in adapters


async def test_missing_required_role_raises_key_error(hass):
    data = _data()
    del data[CONF_CHARGER_CURRENT_ENTITY]
    with pytest.raises(KeyError):
        build_adapters(hass, data)


async def test_factory_builds_ev_soc_role_when_configured(hass):
    data = _data()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    adapters = build_adapters(hass, data)
    assert isinstance(adapters["ev_soc"], NumericReadAdapter)
    assert adapters["ev_soc"]._entity_id == "sensor.ev_soc"


async def test_ev_soc_role_absent_when_not_configured(hass):
    # An existing Power-MVP entry predates this field entirely (design doc §8/§9) --
    # build_adapters must not KeyError on it.
    adapters = build_adapters(hass, _data())
    assert "ev_soc" not in adapters


async def test_ev_soc_empty_string_treated_as_absent(hass):
    data = _data()
    data[CONF_EV_SOC_ENTITY] = ""
    adapters = build_adapters(hass, data)
    assert "ev_soc" not in adapters
