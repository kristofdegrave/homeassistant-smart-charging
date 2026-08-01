"""Config and options flow for Smart Charging (ADR-0005)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_DEPARTURE_EXTERNAL_ENTITY,
    CONF_EV_BATTERY_CAPACITY_ENTITY,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EV_SOC_ENTITY,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_HOME_DAY_EXTERNAL_ENTITY,
    CONF_LOW_TARIFF_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    DEFAULT_CAPTAR_AVAILABLE,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_NOMINAL_VOLTAGE,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_COOLDOWN_MIN,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_HOLD_MIN,
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
    DOMAIN,
    STATE_CHARGING,
    STATE_CONNECTED,
)
from .modes._amp_step import ROUND_DOWN, ROUND_NEAREST, ROUND_UP

# Threshold/default keys stored in config-entry OPTIONS (ADR-0005), not data.
OPTION_KEYS = (
    CONF_NOMINAL_VOLTAGE,
    CONF_MIN_CURRENT,
    CONF_MAX_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_SAFETY_MARGIN_W,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_MAX_SOLAR_SOC,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
)


def _parse_states(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _build_translation(connected: str, charging: str) -> dict[str, str]:
    translation = {s: STATE_CONNECTED for s in _parse_states(connected)}
    # Charging wins on overlap.
    translation.update({s: STATE_CHARGING for s in _parse_states(charging)})
    return translation


def _entity(domain: str | list[str] | None = None):
    cfg = {} if domain is None else {"domain": domain}
    return selector.EntitySelector(selector.EntitySelectorConfig(**cfg))


# DATA fields — entity-role mappings + raw state lists (folded into status_translation).
MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_CURRENT_ENTITY): _entity("number"),
        vol.Required(CONF_CHARGER_STATUS_ENTITY): _entity(["sensor", "binary_sensor"]),
        vol.Required(CONF_CONNECTED_STATES): str,
        vol.Required(CONF_CHARGING_STATES): str,
        vol.Required(CONF_NET_POWER_ENTITY): _entity("sensor"),
        vol.Required(CONF_CHARGER_POWER_ENTITY): _entity("sensor"),
        vol.Optional(CONF_GRID_VOLTAGE_ENTITY): _entity("sensor"),
        vol.Optional(CONF_SOLAR_INSTALLED, default=False): bool,
        vol.Optional(CONF_CAPTAR_AVAILABLE, default=True): bool,
        vol.Optional(CONF_EV_SOC_ENTITY): _entity("sensor"),
        vol.Optional(CONF_SOLAR_FORECAST_ENTITY): _entity("sensor"),
        vol.Optional(CONF_EV_BATTERY_CAPACITY_ENTITY): _entity("sensor"),
        vol.Optional(CONF_DEPARTURE_EXTERNAL_ENTITY): _entity("sensor"),
        vol.Optional(CONF_HOME_DAY_EXTERNAL_ENTITY): _entity(["binary_sensor", "input_boolean"]),
        vol.Optional(CONF_LOW_TARIFF_ENTITY): _entity(["binary_sensor", "input_boolean"]),
    }
)


def _threshold_schema(defaults: dict | None = None) -> vol.Schema:
    """OPTIONS fields — thresholds/defaults, prefilled from `defaults` when editing."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NOMINAL_VOLTAGE, default=d.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE)
            ): vol.Coerce(float),
            vol.Required(CONF_MIN_CURRENT, default=d.get(CONF_MIN_CURRENT, 6.0)): vol.Coerce(float),
            vol.Required(CONF_MAX_CURRENT, default=d.get(CONF_MAX_CURRENT, 16.0)): vol.Coerce(
                float
            ),
            vol.Required(CONF_GRID_CEILING_A, default=d.get(CONF_GRID_CEILING_A, 25.0)): vol.Coerce(
                float
            ),
            vol.Required(
                CONF_GRID_SAFETY_OFFSET_A,
                default=d.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DEFAULT_TARGET_CURRENT, default=d.get(CONF_DEFAULT_TARGET_CURRENT, 10.0)
            ): vol.Coerce(float),
            vol.Required(
                CONF_SMOOTHING_WINDOW,
                default=d.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
            ): vol.Coerce(int),
            vol.Required(
                CONF_SOLAR_START_THRESHOLD_W,
                default=d.get(CONF_SOLAR_START_THRESHOLD_W, DEFAULT_SOLAR_START_THRESHOLD_W),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_ONLY_START_THRESHOLD_W,
                default=d.get(
                    CONF_SOLAR_ONLY_START_THRESHOLD_W, DEFAULT_SOLAR_ONLY_START_THRESHOLD_W
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_HOLD_MIN, default=d.get(CONF_SOLAR_HOLD_MIN, DEFAULT_SOLAR_HOLD_MIN)
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_COOLDOWN_MIN,
                default=d.get(CONF_SOLAR_COOLDOWN_MIN, DEFAULT_SOLAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_ONLY_STRATEGY,
                default=d.get(CONF_SOLAR_ONLY_STRATEGY, DEFAULT_SOLAR_ONLY_STRATEGY),
            ): vol.In([ROUND_UP, ROUND_DOWN, ROUND_NEAREST]),
            vol.Required(
                CONF_SOLAR_ONLY_MIDPOINT,
                default=d.get(CONF_SOLAR_ONLY_MIDPOINT, DEFAULT_SOLAR_ONLY_MIDPOINT),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DEFAULT_SOC_LIMIT, default=d.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_SAFETY_MARGIN_W,
                default=d.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_PEAK_KW, default=d.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW)
            ): vol.Coerce(float),
            vol.Required(
                CONF_PEAK_GRACE_MIN,
                default=d.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_CAPTAR_COOLDOWN_MIN,
                default=d.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
            ): vol.Coerce(float),
            vol.Required(
                CONF_POWER_RESPECT_PEAK,
                default=d.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK),
            ): bool,
            vol.Required(
                CONF_EV_BATTERY_CAPACITY_KWH,
                default=d.get(CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_MAX_SOLAR_SOC,
                default=d.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_STEP_PP,
                default=d.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_STEP_THRESHOLD_PP,
                default=d.get(CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_RESERVE_SOC,
                default=d.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
            ): vol.Coerce(float),
            vol.Required(
                CONF_SOLAR_FORECAST_THRESHOLD_KWH,
                default=d.get(
                    CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
                ),
            ): vol.Coerce(float),
        }
    )


# Install form = mappings + thresholds in one screen; split into data/options on submit.
USER_SCHEMA = MAPPING_SCHEMA.extend(_threshold_schema().schema)


def _ev_soc_missing_error(user_input: dict) -> dict[str, str] | None:
    """R18/design §3: Solar installed=True or CapTar available=True requires ev_soc
    mapped -- a config-time guard, not a runtime fault. Shared by the install and
    reconfigure steps so flipping either toggle through either path is rejected the
    same way. Both must be False for ev_soc to stay optional."""
    if user_input.get(CONF_SOLAR_INSTALLED) and not user_input.get(CONF_EV_SOC_ENTITY):
        return {CONF_EV_SOC_ENTITY: "required_when_solar_installed"}
    if user_input.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE) and not user_input.get(
        CONF_EV_SOC_ENTITY
    ):
        return {CONF_EV_SOC_ENTITY: "required_when_captar_available"}
    return None


def _solar_forecast_missing_error(user_input: dict) -> dict[str, str] | None:
    """Design doc §3: solar_forecast is required only when CONF_SOLAR_INSTALLED is True
    (R9's precondition is inert without the solar capability) -- same
    required_when_solar_installed-style guard ev_soc's own guard uses."""
    if user_input.get(CONF_SOLAR_INSTALLED) and not user_input.get(CONF_SOLAR_FORECAST_ENTITY):
        return {CONF_SOLAR_FORECAST_ENTITY: "required_when_solar_installed"}
    return None


def _mapping_errors(user_input: dict) -> dict[str, str] | None:
    """Combined config-time guards for the mapping step (install + reconfigure)."""
    errors = _ev_soc_missing_error(user_input) or {}
    errors.update(_solar_forecast_missing_error(user_input) or {})
    return errors or None


def _split_data(user_input: dict) -> dict:
    """Extract the DATA bucket (mappings + derived translation) from a submitted form."""
    data = {
        k: v
        for k, v in user_input.items()
        if k not in OPTION_KEYS and k not in (CONF_CONNECTED_STATES, CONF_CHARGING_STATES)
    }
    data[CONF_STATUS_TRANSLATION] = _build_translation(
        user_input[CONF_CONNECTED_STATES], user_input[CONF_CHARGING_STATES]
    )
    return data


class SmartChargingConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the install-time and reconfigure flows (ADR-0005)."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        errors = _mapping_errors(user_input)
        if errors:
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
                errors=errors,
            )

        data = _split_data(user_input)
        options = {k: user_input[k] for k in OPTION_KEYS}
        options[CONF_CONTROL_INTERVAL_S] = DEFAULT_CONTROL_INTERVAL_S
        return self.async_create_entry(title="Smart Charging", data=data, options=options)

    async def async_step_reconfigure(self, user_input=None):
        """Edit the entity-role mappings (DATA) with re-validation; reloads on save (ADR-0005)."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self.async_show_form(step_id="reconfigure", data_schema=MAPPING_SCHEMA)

        errors = _mapping_errors(user_input)
        if errors:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(MAPPING_SCHEMA, user_input),
                errors=errors,
            )

        return self.async_update_reload_and_abort(entry, data=_split_data(user_input))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartChargingOptionsFlow(config_entry)


class SmartChargingOptionsFlow(config_entries.OptionsFlow):
    """Options flow: thresholds/defaults + control interval, editable anytime (ADR-0005)."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = _threshold_schema(opts).extend(
            {
                vol.Required(
                    CONF_CONTROL_INTERVAL_S,
                    default=opts.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S),
                ): vol.All(vol.Coerce(int), vol.Range(min=5))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
