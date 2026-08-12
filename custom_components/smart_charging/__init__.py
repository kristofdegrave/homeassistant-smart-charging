"""The Smart Charging integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.event import async_track_time_interval

from .adapters.factory import build_adapters
from .adapters.store import Store
from .config import SmartChargingConfig
from .const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_MAX_CURRENT,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_COOLDOWN_MIN,
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
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    DEFAULT_CAPTAR_AVAILABLE,
    DEFAULT_CAPTAR_COOLDOWN_MIN,
    DEFAULT_CONTROL_INTERVAL_S,
    DEFAULT_EV_BATTERY_CAPACITY_KWH,
    DEFAULT_EVENING_PROMPT_ENABLED,
    DEFAULT_EVENING_PROMPT_TIME,
    DEFAULT_GRID_SAFETY_OFFSET_A,
    DEFAULT_MAX_PEAK_KW,
    DEFAULT_MAX_SOLAR_SOC,
    DEFAULT_PEAK_GRACE_MIN,
    DEFAULT_POWER_RESPECT_PEAK,
    DEFAULT_SAFETY_MARGIN_W,
    DEFAULT_SMOOTHING_WINDOW,
    DEFAULT_SOC_LIMIT,
    DEFAULT_SOLAR_COOLDOWN_MIN,
    DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH,
    DEFAULT_SOLAR_HOLD_MIN,
    DEFAULT_SOLAR_INSTALLED,
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
    LABEL_SC_RUNTIME,
    PEAK_WINDOW_SECONDS,
    ROLE_NOTIFICATION_TARGET,
)
from .coordinator import SmartChargingCoordinator
from .dashboard import async_register_dashboard, async_unregister_dashboard
from .managers.notification_manager import NotificationManager
from .managers.vehicle_limit import VehicleLimitManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


@dataclass
class SmartChargingRuntimeData:
    """This entry's config-entry-scoped runtime state, set once onto `entry.runtime_data`.
    `vehicle_limit_manager` (M2) is None when CONF_VEHICLE_CHARGE_LIMIT_ENTITY
    is unmapped -- every other field is always populated."""

    coordinator: SmartChargingCoordinator
    notification_manager: NotificationManager
    vehicle_limit_manager: VehicleLimitManager | None
    min_current: float
    max_current: float
    default_target_current: float
    default_soc_limit: float


# Current HA idiom for a typed entry.runtime_data -- every platform's
# async_setup_entry types its `entry` parameter with this alias instead of a bare ConfigEntry.
type SmartChargingConfigEntry = ConfigEntry[SmartChargingRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SmartChargingConfigEntry) -> bool:
    # C5 (#601): the sc_runtime label must exist before any owned entity references it -- an
    # entity-registry label id with no matching label_registry entry has no display name and
    # nothing for the dashboard's `auto-entities` filter to resolve. Idempotent across reloads.
    label_registry = lr.async_get(hass)
    if label_registry.async_get_label_by_name(LABEL_SC_RUNTIME) is None:
        label_registry.async_create(LABEL_SC_RUNTIME)

    # Mappings/translation live in data; thresholds/defaults + interval in options (ADR-0005).
    adapters = build_adapters(hass, entry.data)
    opts = entry.options
    min_current = opts[CONF_MIN_CURRENT]
    max_current = opts[CONF_MAX_CURRENT]
    default_target_current = opts[CONF_DEFAULT_TARGET_CURRENT]
    default_soc_limit = opts.get(CONF_DEFAULT_SOC_LIMIT, DEFAULT_SOC_LIMIT)
    interval_s = opts.get(CONF_CONTROL_INTERVAL_S, DEFAULT_CONTROL_INTERVAL_S)
    # E5's 15-minute averaging window expressed in cycle counts (design doc Sec 6.4) -- derived
    # here, once, from the same control interval the coordinator ticks on (issue #570: the only
    # other reader of PEAK_WINDOW_SECONDS was coordinator.py's own now-removed duplicate fallback).
    peak_window_size = max(1, round(PEAK_WINDOW_SECONDS / interval_s))
    # Issue #570: the ONE place every option is resolved with its DEFAULT_* fallback (an entry
    # that predates a given key reads that key's default, no config-entry migration needed) --
    # coordinator.py/coordinator_cycle.py read this frozen dataclass's typed fields, never
    # re-defaulting or re-indexing any of them a second time.
    config = SmartChargingConfig(
        solar_installed=entry.data.get(CONF_SOLAR_INSTALLED, DEFAULT_SOLAR_INSTALLED),
        captar_available=entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE),
        min_current=min_current,
        max_current=max_current,
        grid_ceiling_a=opts[CONF_GRID_CEILING_A],
        grid_safety_offset_a=opts.get(CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A),
        nominal_voltage=opts[CONF_NOMINAL_VOLTAGE],
        smoothing_window=opts.get(CONF_SMOOTHING_WINDOW, DEFAULT_SMOOTHING_WINDOW),
        peak_window_size=peak_window_size,
        solar_start_threshold_w=opts.get(
            CONF_SOLAR_START_THRESHOLD_W, DEFAULT_SOLAR_START_THRESHOLD_W
        ),
        solar_only_start_threshold_w=opts.get(
            CONF_SOLAR_ONLY_START_THRESHOLD_W, DEFAULT_SOLAR_ONLY_START_THRESHOLD_W
        ),
        solar_hold_min=opts.get(CONF_SOLAR_HOLD_MIN, DEFAULT_SOLAR_HOLD_MIN),
        solar_cooldown_min=opts.get(CONF_SOLAR_COOLDOWN_MIN, DEFAULT_SOLAR_COOLDOWN_MIN),
        solar_only_strategy=opts.get(CONF_SOLAR_ONLY_STRATEGY, DEFAULT_SOLAR_ONLY_STRATEGY),
        solar_only_midpoint=opts.get(CONF_SOLAR_ONLY_MIDPOINT, DEFAULT_SOLAR_ONLY_MIDPOINT),
        safety_margin_w=opts.get(CONF_SAFETY_MARGIN_W, DEFAULT_SAFETY_MARGIN_W),
        max_peak_kw=opts.get(CONF_MAX_PEAK_KW, DEFAULT_MAX_PEAK_KW),
        peak_grace_min=opts.get(CONF_PEAK_GRACE_MIN, DEFAULT_PEAK_GRACE_MIN),
        captar_cooldown_min=opts.get(CONF_CAPTAR_COOLDOWN_MIN, DEFAULT_CAPTAR_COOLDOWN_MIN),
        power_respect_peak=opts.get(CONF_POWER_RESPECT_PEAK, DEFAULT_POWER_RESPECT_PEAK),
        ev_battery_capacity_kwh=opts.get(
            CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH
        ),
        max_solar_soc=opts.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
        solar_step_pp=opts.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
        solar_step_threshold_pp=opts.get(
            CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP
        ),
        solar_reserve_soc=opts.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
        solar_forecast_threshold_kwh=opts.get(
            CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
        ),
        evening_prompt_enabled=opts.get(
            CONF_EVENING_PROMPT_ENABLED, DEFAULT_EVENING_PROMPT_ENABLED
        ),
        evening_prompt_time=opts.get(CONF_EVENING_PROMPT_TIME, DEFAULT_EVENING_PROMPT_TIME),
    )

    store = Store(hass, entry.entry_id)
    coordinator = SmartChargingCoordinator(
        hass, adapters=adapters, store=store, config=config, interval_s=interval_s
    )
    # M3 (issue #570 scope excludes managers/notification_manager.py) keeps its own small
    # Mapping -- the three VALUES below come from the same, already-resolved
    # SmartChargingConfig fields above, so they can't drift from what the coordinator sees.
    # NotificationManager's own `.get(CONF_X, DEFAULT_X)` on this dict is still a second,
    # separate DEFAULT_* resolution in principle (unreachable today since every key is always
    # supplied here) -- folding M3 onto SmartChargingConfig too is tracked as a follow-up,
    # not this issue's scope.
    notification_manager = NotificationManager(
        hass,
        adapters=adapters,
        entry_id=entry.entry_id,
        store=store,
        config={
            CONF_EVENING_PROMPT_ENABLED: config.evening_prompt_enabled,
            CONF_SOLAR_FORECAST_THRESHOLD_KWH: config.solar_forecast_threshold_kwh,
            CONF_EVENING_PROMPT_TIME: config.evening_prompt_time,
        },
    )
    # M2 is only constructed when vehicle_charge_limit is mapped (UC09 precondition) --
    # design §9.5: M2 self-wires its own three listeners below, mirroring the M1/M3
    # self-wiring precedent in this same function, rather than a dedicated C6 client.
    vehicle_limit_manager = (
        VehicleLimitManager(hass, adapters=adapters, entry_id=entry.entry_id, store=store)
        if entry.data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY)
        else None
    )

    # Typed config-entry-scoped runtime state -- number.py reads the same four
    # values back off entry.runtime_data, so the two sides can't drift apart.
    entry.runtime_data = SmartChargingRuntimeData(
        coordinator=coordinator,
        notification_manager=notification_manager,
        vehicle_limit_manager=vehicle_limit_manager,
        min_current=min_current,
        max_current=max_current,
        default_target_current=default_target_current,
        default_soc_limit=default_soc_limit,
    )

    # NotifyAdapter registers a bus listener at construction; without unsubscribing
    # it here, each reload (setup -> unload -> setup) leaked another one. `async_on_unload`
    # fires on unload (including a reload's own unload half and setup-retry teardown), the
    # same hook already used below for the update listener.
    notify_adapter = adapters.get(ROLE_NOTIFICATION_TARGET)
    if notify_adapter is not None:
        entry.async_on_unload(notify_adapter.close)

    # R5 delivery: M3 subscribes to the Coordinator's own DeadlineUnreachableNotified
    # bus event BEFORE the first refresh below -- unlike the tick/M2's listeners, which are
    # deliberately registered after (they read owned entities the Store/platforms must exist
    # for first), this listener consumes a plain bus event, and the first refresh is exactly
    # the earliest point that event could fire (an already-unreachable deadline at boot).
    # Registering after it would silently lose that first, permanently-latched delivery
    # opportunity (on_deadline_unreachable's notify-once latch) with no re-fire to
    # recover on.
    for unsub in notification_manager.register_listeners():
        entry.async_on_unload(unsub)

    # First refresh AFTER platforms: so the number entity can seed target_current on add, and
    # so the Store's first _read_owned_entities() read (ADR-0018) finds the owned entities
    # already registered. M3's tick is registered here too, for the same reason (its own
    # Store.write is best-effort/never-raises either way, but there is no reason to open the
    # window at all when it costs nothing to close).
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_config_entry_first_refresh()
    entry.async_on_unload(
        async_track_time_interval(
            hass, notification_manager.async_evaluate, timedelta(seconds=interval_s)
        )
    )

    # M2's three listeners (ADR-0008: live only while the entry is loaded -- a reload tears
    # down via async_on_unload and re-registers on the next setup, same as every listener
    # above). Registered after platforms AND after the coordinator's first refresh, so
    # number.smart_charging_soc_limit_override already exists for the disconnect-reset/
    # adoption reactions to read/write through the Store; a consequence is that the first
    # refresh's own active-SOC-limit publication is never itself observed as a "change" by
    # M2 (same as `prime_status` below, C2-gated either way -- it converges on the next
    # real change, not left stale). `prime_status` runs first: a freshly registered listener
    # only observes changes AFTER it subscribes, so without priming, a reload/restart with
    # the vehicle already connected would lose the connected->disconnected edge on the next
    # disconnect (design §5.3).
    if vehicle_limit_manager is not None:
        await vehicle_limit_manager.prime_status()
        for unsub in vehicle_limit_manager.register_listeners(
            vehicle_entity_id=entry.data[CONF_VEHICLE_CHARGE_LIMIT_ENTITY],
            status_entity_id=entry.data[CONF_CHARGER_STATUS_ENTITY],
        ):
            entry.async_on_unload(unsub)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # C5 (#601, ADR-0022): regenerated and re-registered on every setup (including a reload's
    # own setup half) -- after platforms, so the dashboard's fixed tiles/labels reference
    # entities that already exist. A Client with no service of its own (system-design.md)
    # must not take the whole control loop down if the frontend/lovelace internals it depends
    # on (ADR-0022's own accepted risk) ever break -- caught narrowly and logged instead.
    try:
        await async_register_dashboard(hass, entry)
    except Exception:  # deliberately broad -- see comment above
        _LOGGER.exception("Failed to register the runtime dashboard")
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: SmartChargingConfigEntry) -> None:
    # Fires on any entry update, not only options — a reconfigure (data) update also lands
    # here in addition to its own reload, which is harmless since HA serializes reloads.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SmartChargingConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Only torn down once the platform unload actually succeeds -- if it doesn't, the
        # entry stays loaded and the dashboard must stay registered along with it.
        await async_unregister_dashboard(hass, entry)
    return unloaded
