"""The Smart Charging integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .adapters.factory import build_adapters
from .const import (
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
    CONF_SOLAR_HOLD_MIN,
    CONF_SOLAR_ONLY_MIDPOINT,
    CONF_SOLAR_ONLY_START_THRESHOLD_W,
    CONF_SOLAR_ONLY_STRATEGY,
    CONF_SOLAR_START_THRESHOLD_W,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_COOLDOWN_MIN,
    DEFAULT_SOLAR_HOLD_MIN,
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DOMAIN,
    PEAK_WINDOW_SECONDS,
)
from .coordinator import SmartChargingCoordinator

PLATFORMS = [Platform.NUMBER, Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Mappings/translation live in data; thresholds/defaults + interval in options (ADR-0005).
    adapters = build_adapters(hass, entry.data)
    opts = entry.options
    min_current = opts[CONF_MIN_CURRENT]
    max_current = opts[CONF_MAX_CURRENT]
    default_target_current = opts[CONF_DEFAULT_TARGET_CURRENT]
    default_soc_limit = opts.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT)
    interval_s = opts.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S)
    # E5's 15-minute averaging window expressed in cycle counts (design doc Sec 6.4) -- derived
    # here, once, from the same control interval the coordinator ticks on, so it can't drift from
    # coordinator.py's own fallback (PEAK_WINDOW_SECONDS, shared).
    peak_window_size = max(1, round(PEAK_WINDOW_SECONDS / interval_s))
    config = {
        "min_current": min_current,
        "max_current": max_current,
        "grid_ceiling_a": opts[CONF_GRID_CEILING_A],
        "grid_safety_offset_a": opts.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
        "nominal_voltage": opts[CONF_NOMINAL_VOLTAGE],
        CONF_SMOOTHING_WINDOW: opts.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
        CONF_PEAK_WINDOW_SIZE: peak_window_size,
        CONF_SOLAR_START_THRESHOLD_W: opts.get(
            CONF_SOLAR_START_THRESHOLD_W, DEFAULT_SOLAR_START_THRESHOLD_W
        ),
        CONF_SOLAR_ONLY_START_THRESHOLD_W: opts.get(
            CONF_SOLAR_ONLY_START_THRESHOLD_W, DEFAULT_SOLAR_ONLY_START_THRESHOLD_W
        ),
        CONF_SOLAR_HOLD_MIN: opts.get(CONF_SOLAR_HOLD_MIN, DEFAULT_SOLAR_HOLD_MIN),
        CONF_SOLAR_COOLDOWN_MIN: opts.get(CONF_SOLAR_COOLDOWN_MIN, DEFAULT_SOLAR_COOLDOWN_MIN),
        CONF_SOLAR_ONLY_STRATEGY: opts.get(CONF_SOLAR_ONLY_STRATEGY, DEFAULT_SOLAR_ONLY_STRATEGY),
        CONF_SOLAR_ONLY_MIDPOINT: opts.get(CONF_SOLAR_ONLY_MIDPOINT, DEFAULT_SOLAR_ONLY_MIDPOINT),
        CONF_SAFETY_MARGIN_W: opts.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
        CONF_MAX_PEAK_KW: opts.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW),
        CONF_PEAK_GRACE_MIN: opts.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN),
        CONF_CAPTAR_COOLDOWN_MIN: opts.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
        CONF_POWER_RESPECT_PEAK: opts.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK),
    }

    coordinator = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=interval_s
    )

    # Keyed by the same CONF_* constants number.py reads, so the two sides can't drift apart.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        CONF_MIN_CURRENT: min_current,
        CONF_MAX_CURRENT: max_current,
        CONF_DEFAULT_TARGET_CURRENT: default_target_current,
        CONF_DEFAULT_SOC_LIMIT: default_soc_limit,
    }

    # First refresh AFTER platforms so the number entity can seed target_current on add.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Fires on any entry update, not only options — a reconfigure (data) update also lands
    # here in addition to its own reload, which is harmless since HA serializes reloads.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
