"""Adapter factory: instantiate one adapter per role from config-entry data (ADR-0003)."""

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_NET_POWER_ENTITY,
    CONF_STATUS_TRANSLATION,
    ROLE_EV_SOC,
)
from .base import Adapter
from .numeric import NumericReadAdapter, NumericReadWriteAdapter
from .status import StatusReadAdapter


def build_adapters(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Adapter]:
    """Build the control-cycle adapter set from config-entry data.

    grid_voltage and ev_soc are optional (NF4 / RA1 extension); every other role is
    required. ev_soc's absence is only a fault while a solar mode is active (Task
    5.1's job) -- the factory itself never requires it.
    """
    adapters: dict[str, Adapter] = {
        "charger_current": NumericReadWriteAdapter(hass, data[CONF_CHARGER_CURRENT_ENTITY]),
        "charger_status": StatusReadAdapter(
            hass, data[CONF_CHARGER_STATUS_ENTITY], dict(data[CONF_STATUS_TRANSLATION])
        ),
        "net_power": NumericReadAdapter(hass, data[CONF_NET_POWER_ENTITY]),
        "charger_power": NumericReadAdapter(hass, data[CONF_CHARGER_POWER_ENTITY]),
    }
    if data.get(CONF_GRID_VOLTAGE_ENTITY):
        adapters["grid_voltage"] = NumericReadAdapter(hass, data[CONF_GRID_VOLTAGE_ENTITY])
    if data.get(CONF_EV_SOC_ENTITY):
        adapters[ROLE_EV_SOC] = NumericReadAdapter(hass, data[CONF_EV_SOC_ENTITY])
    return adapters
