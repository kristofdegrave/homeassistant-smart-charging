"""Adapter factory: instantiate one adapter per role from config-entry data (ADR-0003)."""

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import (
    CONF_CAR_HOME_ENTITY,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEPARTURE_EXTERNAL_ENTITY,
    CONF_EV_BATTERY_CAPACITY_ENTITY,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_HOME_DAY_EXTERNAL_ENTITY,
    CONF_LOW_TARIFF_ENTITY,
    CONF_LOW_TARIFF_STATES,
    CONF_NET_POWER_ENTITY,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_STATUS_TRANSLATION,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    ROLE_CAR_HOME,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_DEPARTURE_EXTERNAL,
    ROLE_EV_BATTERY_CAPACITY,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_HOME_DAY_EXTERNAL,
    ROLE_LOW_TARIFF,
    ROLE_NET_POWER,
    ROLE_NOTIFICATION_TARGET,
    ROLE_SOLAR_FORECAST,
    ROLE_SUN,
    ROLE_VEHICLE_CHARGE_LIMIT,
)
from .base import Adapter
from .boolean import BooleanReadAdapter
from .notify import NotifyAdapter
from .numeric import NumericReadAdapter, NumericReadWriteAdapter
from .presence import PresenceReadAdapter
from .status import StatusReadAdapter
from .sun import SunReadAdapter
from .tariff import LowTariffReadAdapter
from .time_read import TimeReadAdapter


def build_adapters(hass: HomeAssistant, data: Mapping[str, Any]) -> dict[str, Adapter]:
    """Build the control-cycle adapter set from config-entry data.

    grid_voltage, ev_soc, ev_battery_capacity, departure_external, home_day_external,
    solar_forecast, low_tariff, car_home, vehicle_charge_limit, and notification_target
    are all optional at the factory level (NF4 / RA1 / RA1-VL / RA2 / RA4 extensions);
    sun is built unconditionally with
    no entity mapping at all (`sun.sun` is a core Home Assistant entity, not
    something the user maps); every other role is required. An optional role's absence is
    only a fault where its consuming engine/manager actually needs it (e.g. ev_soc while a
    solar mode is active) -- the factory itself never requires any of them.
    """
    adapters: dict[str, Adapter] = {
        ROLE_CHARGER_CURRENT: NumericReadWriteAdapter(hass, data[CONF_CHARGER_CURRENT_ENTITY]),
        ROLE_CHARGER_STATUS: StatusReadAdapter(
            hass, data[CONF_CHARGER_STATUS_ENTITY], dict(data[CONF_STATUS_TRANSLATION])
        ),
        ROLE_NET_POWER: NumericReadAdapter(hass, data[CONF_NET_POWER_ENTITY]),
        ROLE_CHARGER_POWER: NumericReadAdapter(hass, data[CONF_CHARGER_POWER_ENTITY]),
        ROLE_SUN: SunReadAdapter(hass),  # no entity mapping, always built
    }
    if data.get(CONF_GRID_VOLTAGE_ENTITY):
        adapters[ROLE_GRID_VOLTAGE] = NumericReadAdapter(hass, data[CONF_GRID_VOLTAGE_ENTITY])
    if data.get(CONF_EV_SOC_ENTITY):
        adapters[ROLE_EV_SOC] = NumericReadAdapter(hass, data[CONF_EV_SOC_ENTITY])
    if data.get(CONF_EV_BATTERY_CAPACITY_ENTITY):
        adapters[ROLE_EV_BATTERY_CAPACITY] = NumericReadAdapter(
            hass, data[CONF_EV_BATTERY_CAPACITY_ENTITY]
        )
    if data.get(CONF_DEPARTURE_EXTERNAL_ENTITY):
        adapters[ROLE_DEPARTURE_EXTERNAL] = TimeReadAdapter(
            hass, data[CONF_DEPARTURE_EXTERNAL_ENTITY]
        )
    if data.get(CONF_HOME_DAY_EXTERNAL_ENTITY):
        adapters[ROLE_HOME_DAY_EXTERNAL] = BooleanReadAdapter(
            hass, data[CONF_HOME_DAY_EXTERNAL_ENTITY]
        )
    if data.get(CONF_SOLAR_FORECAST_ENTITY):
        adapters[ROLE_SOLAR_FORECAST] = NumericReadAdapter(hass, data[CONF_SOLAR_FORECAST_ENTITY])
    if data.get(CONF_LOW_TARIFF_ENTITY):
        adapters[ROLE_LOW_TARIFF] = LowTariffReadAdapter(
            hass, data[CONF_LOW_TARIFF_ENTITY], data.get(CONF_LOW_TARIFF_STATES, "")
        )
    if data.get(CONF_CAR_HOME_ENTITY):
        adapters[ROLE_CAR_HOME] = PresenceReadAdapter(hass, data[CONF_CAR_HOME_ENTITY])
    if data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY):
        adapters[ROLE_VEHICLE_CHARGE_LIMIT] = NumericReadWriteAdapter(
            hass, data[CONF_VEHICLE_CHARGE_LIMIT_ENTITY]
        )
    if data.get(CONF_NOTIFICATION_TARGET_ENTITY):
        adapters[ROLE_NOTIFICATION_TARGET] = NotifyAdapter(
            hass, data[CONF_NOTIFICATION_TARGET_ENTITY]
        )
    return adapters
