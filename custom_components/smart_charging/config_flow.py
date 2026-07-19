"""Config and options flow for Smart Charging (ADR-0005)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_CHARGING_STATES,
    CONF_CONNECTED_STATES,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_STATUS_TRANSLATION,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_NOMINAL_VOLTAGE,
    DOMAIN,
    STATE_CHARGING,
    STATE_CONNECTED,
)

# Threshold/default keys stored in config-entry OPTIONS (ADR-0005), not data.
OPTION_KEYS = (
    CONF_NOMINAL_VOLTAGE,
    CONF_MIN_CURRENT,
    CONF_MAX_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_DEFAULT_TARGET_CURRENT,
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
        }
    )


# Install form = mappings + thresholds in one screen; split into data/options on submit.
USER_SCHEMA = MAPPING_SCHEMA.extend(_threshold_schema().schema)


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

        data = _split_data(user_input)
        options = {k: user_input[k] for k in OPTION_KEYS}
        options[CONF_CONTROL_INTERVAL_S] = DEFAULT_CONTROL_INTERVAL_S
        return self.async_create_entry(title="Smart Charging", data=data, options=options)

    async def async_step_reconfigure(self, user_input=None):
        """Edit the entity-role mappings (DATA) with re-validation; reloads on save (ADR-0005)."""
        entry = self._get_reconfigure_entry()
        if user_input is None:
            return self.async_show_form(step_id="reconfigure", data_schema=MAPPING_SCHEMA)
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
                ): vol.All(int, vol.Range(min=5))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
