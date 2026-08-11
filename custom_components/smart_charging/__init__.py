"""The Smart Charging integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.event import async_track_time_interval

from .adapters.factory import build_adapters
from .adapters.store import Store
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
    CONF_PEAK_WINDOW_SIZE,
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
    DATA_COORDINATOR,
    DATA_NOTIFICATION_MANAGER,
    DATA_VEHICLE_LIMIT_MANAGER,
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
    DEFAULT_SOLAR_ONLY_MIDPOINT,
    DEFAULT_SOLAR_ONLY_START_THRESHOLD_W,
    DEFAULT_SOLAR_ONLY_STRATEGY,
    DEFAULT_SOLAR_RESERVE_SOC,
    DEFAULT_SOLAR_START_THRESHOLD_W,
    DEFAULT_SOLAR_STEP_PP,
    DEFAULT_SOLAR_STEP_THRESHOLD_PP,
    DOMAIN,
    LABEL_SC_RUNTIME,
    PEAK_WINDOW_SECONDS,
    ROLE_NOTIFICATION_TARGET,
)
from .coordinator import SmartChargingCoordinator
from .dashboard import async_register_dashboard, async_unregister_dashboard
from .managers.notification_manager import NotificationManager
from .managers.vehicle_limit import VehicleLimitManager

PLATFORMS = [
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
    # here, once, from the same control interval the coordinator ticks on, so it can't drift from
    # coordinator.py's own fallback (PEAK_WINDOW_SECONDS, shared).
    peak_window_size = max(1, round(PEAK_WINDOW_SECONDS / interval_s))
    config = {
        CONF_SOLAR_INSTALLED: entry.data.get(CONF_SOLAR_INSTALLED, False),
        CONF_CAPTAR_AVAILABLE: entry.data.get(CONF_CAPTAR_AVAILABLE, DEFAULT_CAPTAR_AVAILABLE),
        CONF_MIN_CURRENT: min_current,
        CONF_MAX_CURRENT: max_current,
        CONF_GRID_CEILING_A: opts[CONF_GRID_CEILING_A],
        CONF_GRID_SAFETY_OFFSET_A: opts.get(
            CONF_GRID_SAFETY_OFFSET_A, DEFAULT_GRID_SAFETY_OFFSET_A
        ),
        CONF_NOMINAL_VOLTAGE: opts[CONF_NOMINAL_VOLTAGE],
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
        CONF_EV_BATTERY_CAPACITY_KWH: opts.get(
            CONF_EV_BATTERY_CAPACITY_KWH, DEFAULT_EV_BATTERY_CAPACITY_KWH
        ),
        CONF_MAX_SOLAR_SOC: opts.get(CONF_MAX_SOLAR_SOC, DEFAULT_MAX_SOLAR_SOC),
        CONF_SOLAR_STEP_PP: opts.get(CONF_SOLAR_STEP_PP, DEFAULT_SOLAR_STEP_PP),
        CONF_SOLAR_STEP_THRESHOLD_PP: opts.get(
            CONF_SOLAR_STEP_THRESHOLD_PP, DEFAULT_SOLAR_STEP_THRESHOLD_PP
        ),
        CONF_SOLAR_RESERVE_SOC: opts.get(CONF_SOLAR_RESERVE_SOC, DEFAULT_SOLAR_RESERVE_SOC),
        CONF_SOLAR_FORECAST_THRESHOLD_KWH: opts.get(
            CONF_SOLAR_FORECAST_THRESHOLD_KWH, DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH
        ),
        # M3's own options (UC08) -- share the same config dict rather than a second one,
        # since CONF_SOLAR_FORECAST_THRESHOLD_KWH above is already common to both M1 and M3.
        CONF_EVENING_PROMPT_ENABLED: opts.get(
            CONF_EVENING_PROMPT_ENABLED, DEFAULT_EVENING_PROMPT_ENABLED
        ),
        CONF_EVENING_PROMPT_TIME: opts.get(CONF_EVENING_PROMPT_TIME, DEFAULT_EVENING_PROMPT_TIME),
    }

    store = Store(hass, entry.entry_id)
    coordinator = SmartChargingCoordinator(
        hass, adapters=adapters, store=store, config=config, interval_s=interval_s
    )
    notification_manager = NotificationManager(
        hass, adapters=adapters, entry_id=entry.entry_id, store=store, config=config
    )
    # M2 is only constructed when vehicle_charge_limit is mapped (UC09 precondition) --
    # design §9.5: M2 self-wires its own three listeners below, mirroring the M1/M3
    # self-wiring precedent in this same function, rather than a dedicated C6 client.
    vehicle_limit_manager = (
        VehicleLimitManager(hass, adapters=adapters, entry_id=entry.entry_id, store=store)
        if entry.data.get(CONF_VEHICLE_CHARGE_LIMIT_ENTITY)
        else None
    )

    # Keyed by the same CONF_* constants number.py reads, so the two sides can't drift apart.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_NOTIFICATION_MANAGER: notification_manager,
        DATA_VEHICLE_LIMIT_MANAGER: vehicle_limit_manager,
        CONF_MIN_CURRENT: min_current,
        CONF_MAX_CURRENT: max_current,
        CONF_DEFAULT_TARGET_CURRENT: default_target_current,
        CONF_DEFAULT_SOC_LIMIT: default_soc_limit,
    }

    # issue #498: NotifyAdapter registers a bus listener at construction; without unsubscribing
    # it here, each reload (setup -> unload -> setup) leaked another one. `async_on_unload`
    # fires on unload (including a reload's own unload half and setup-retry teardown), the
    # same hook already used below for the update listener.
    notify_adapter = adapters.get(ROLE_NOTIFICATION_TARGET)
    if notify_adapter is not None:
        entry.async_on_unload(notify_adapter.close)

    # R5 delivery (Task 6.1): M3 subscribes to the Coordinator's own DeadlineUnreachableNotified
    # bus event BEFORE the first refresh below -- unlike the tick/M2's listeners, which are
    # deliberately registered after (they read owned entities the Store/platforms must exist
    # for first), this listener consumes a plain bus event, and the first refresh is exactly
    # the earliest point that event could fire (an already-unreachable deadline at boot).
    # Registering after it would silently lose that first, permanently-latched delivery
    # opportunity (on_deadline_unreachable's notify-once latch, Task 6.1) with no re-fire to
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
    # entities that already exist.
    await async_register_dashboard(hass, entry)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Fires on any entry update, not only options — a reconfigure (data) update also lands
    # here in addition to its own reload, which is harmless since HA serializes reloads.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await async_unregister_dashboard(hass, entry)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
