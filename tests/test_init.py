"""End-to-end setup test (M1 + C1 + C2 + adapters)."""

from datetime import time, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.smart_charging.adapters.notify import (
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
)
from custom_components.smart_charging.adapters.sun import SUN_STATE_BELOW_HORIZON
from custom_components.smart_charging.const import (
    ATTR_REQUIRED_CURRENT_A,
    CONF_CAPTAR_AVAILABLE,
    CONF_CAPTAR_COOLDOWN_MIN,
    CONF_CAR_HOME_ENTITY,
    CONF_CONTROL_INTERVAL_S,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_EV_BATTERY_CAPACITY_KWH,
    CONF_EV_SOC_ENTITY,
    CONF_EVENING_PROMPT_ENABLED,
    CONF_EVENING_PROMPT_TIME,
    CONF_MAX_PEAK_KW,
    CONF_MAX_SOLAR_SOC,
    CONF_NOTIFICATION_TARGET_ENTITY,
    CONF_PEAK_GRACE_MIN,
    CONF_PEAK_WINDOW_SIZE,
    CONF_POWER_RESPECT_PEAK,
    CONF_SAFETY_MARGIN_W,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    CONF_SOLAR_INSTALLED,
    CONF_SOLAR_RESERVE_SOC,
    CONF_SOLAR_STEP_PP,
    CONF_SOLAR_STEP_THRESHOLD_PP,
    CONF_STATUS_TRANSLATION,
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY,
    DEFAULT_CONTROL_INTERVAL_S,
    DOMAIN,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    EVENT_MANUAL_CHARGE_LIMIT_ADOPTED,
    EVENT_VEHICLE_CHARGE_LIMIT_RESET,
    EVENT_VEHICLE_CHARGE_LIMIT_SYNCED,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    PROFILE_AUTO,
    STATE_CHARGING,
    STATE_CONNECTED,
    STATE_DISCONNECTED,
    STATUS_FAULT,
    STATUS_OK,
)
from tests.helpers import (
    capture_charger_current_writes,
    capture_service_calls,
    entry_data_base,
    entry_options_base,
    seed_ample_peak_headroom,
    seed_charger_states,
    seed_owned_entity,
)

_NOTIFICATION_MANAGER_EVALUATE = (
    "custom_components.smart_charging.managers.notification_manager"
    ".NotificationManager.async_evaluate"
)

# This suite's config entry matches the shared base shape exactly -- no local overrides needed.


async def test_end_to_end_commands_target_current(hass):
    calls = capture_charger_current_writes(hass)
    seed_charger_states(hass, status="Charging")

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The number entity exists; its object_id is pinned (ADR-0013) -- this particular id
    # happens to also match the pre-pin translated name, so this line doesn't itself guard
    # the pin (T2.3's enumeration test does)...
    assert hass.states.get("number.smart_charging_target_current") is not None
    # ...the mode selector defaults to Off when never set (T6.1/design doc §2 criterion 1),
    # so the setup cycle wrote 0 A -- pin that down before selecting Power explicitly, same
    # as a real install's first manual step.
    coordinator = entry.runtime_data.coordinator
    assert coordinator.active_mode == MODE_OFF
    assert calls[-1]["value"] == 0.0
    seed_ample_peak_headroom(coordinator)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # ...and that cycle wrote the target current to the charger.
    assert calls and calls[-1]["entity_id"] == "number.charger_current"
    assert calls[-1]["value"] == 10.0
    # ...and the status sensor is OK.
    assert hass.states.get("sensor.smart_charging_status").state == STATUS_OK


async def test_setup_falls_back_to_default_soc_limit_for_pre_solar_entries(hass):
    """A config entry created before this option existed must still set up (no migration)."""
    seed_charger_states(hass, status="Charging")
    options = entry_options_base()
    del options[CONF_DEFAULT_SOC_LIMIT]

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("number.smart_charging_soc_limit_override")
    assert state is not None
    assert float(state.state) == 80.0


async def test_end_to_end_disconnect_forces_zero_and_fault(hass):
    calls = capture_charger_current_writes(hass)
    seed_charger_states(hass, status="Unplugged")  # unmapped raw state -> None (ADR-0003/0007)

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert calls and calls[-1]["entity_id"] == "number.charger_current"
    assert calls[-1]["value"] == 0.0
    assert hass.states.get("sensor.smart_charging_status").state == STATUS_FAULT


async def test_select_entity_is_registered_on_setup(hass):
    """T6.1: the select platform must be forwarded alongside number/sensor. Looked up by
    unique_id, not entity_id -- the "_mode"-suffixed entity_id is now an explicit pin
    (ADR-0013), not a translation-key dependency. Also carries the ADR-0013 covering
    assertions for the two sensor ids T2.2 flips (`monthly_peak_kw`/`active_soc_limit`) --
    T2.3's `test_every_owned_entity_id_matches_entity_catalog` is the durable, comprehensive
    guard for every owned entity; these two are here only because T2.2 predates it."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_SOLAR_INSTALLED] = True
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"  # seed_charger_states already seeds sensor.ev_soc

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_mode")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    # CONF_CAPTAR_AVAILABLE predates this entry's data too -- defaults to True (design doc
    # §3), so Captar is offered alongside Solar/SolarOnly without being set explicitly.
    assert state.attributes["options"] == ["Off", "Power", "Solar", "SolarOnly", "Captar"]

    # ADR-0013: these two flip a real, catalog-diverging id with no other covering
    # assertion -- guard the pin explicitly (T2.2).
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_monthly_peak_kw")
    assert entity_id == "sensor.smart_charging_monthly_peak_kw"
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_active_soc_limit")
    assert entity_id == "sensor.smart_charging_active_soc_limit"


async def test_end_to_end_solar_mode_uses_configured_thresholds(hass):
    """T6.1: the new Solar/SolarOnly options must be threaded into the coordinator's
    config dict -- without it, dispatching to Solar mode KeyErrors on
    CONF_SOLAR_START_THRESHOLD_W (coordinator.py reads it unconditionally, no default)."""
    calls = capture_charger_current_writes(hass)
    seed_charger_states(hass, status="Charging")
    hass.states.async_set("sensor.charger_power", "2400.0")  # 10.43 A ideal -> round_up -> 11 A,
    # distinguishable from Power mode's unrelated 10.0 A default target current.
    data = entry_data_base()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"  # seed_charger_states already seeds sensor.ev_soc

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    seed_ample_peak_headroom(coordinator)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_SOLAR)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.smart_charging_status").state == STATUS_OK
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_SOLAR
    assert calls[-1]["value"] == 11.0


async def test_setup_threads_captar_and_peak_protection_options_into_coordinator_config(hass):
    """T6.1: setup must wire the Captar-cooldown/peak-protection/R17 options (Phase 3's config
    keys, consumed via `self._config.get(...)` in coordinator.py's Task 5.1 wiring) into the
    coordinator's config dict as non-default overrides, plus a `peak_window_size` derived from
    `control_interval_s` -- not just fall back to the coordinator's own internal defaults."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"
    hass.states.async_set("sensor.ev_soc", "50.0")

    options = entry_options_base()
    options[CONF_CONTROL_INTERVAL_S] = 60
    options[CONF_SAFETY_MARGIN_W] = 500.0
    options[CONF_MAX_PEAK_KW] = 7.5
    options[CONF_PEAK_GRACE_MIN] = 3.0
    options[CONF_CAPTAR_COOLDOWN_MIN] = 15.0
    options[CONF_POWER_RESPECT_PEAK] = False

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    config = coordinator._config
    assert config[CONF_SAFETY_MARGIN_W] == 500.0
    assert config[CONF_MAX_PEAK_KW] == 7.5
    assert config[CONF_PEAK_GRACE_MIN] == 3.0
    assert config[CONF_CAPTAR_COOLDOWN_MIN] == 15.0
    assert config[CONF_POWER_RESPECT_PEAK] is False
    # 900s (15-minute) window / 60s control interval -- design doc Sec 6.4.
    assert config[CONF_PEAK_WINDOW_SIZE] == 15


async def test_power_respect_peak_option_threaded_bypasses_peak_clamp(hass):
    """T6.1: behavioral companion to the dict-wiring test above -- proves
    CONF_POWER_RESPECT_PEAK actually flows from the config entry's options into a live cycle's
    R17 opt-out (coordinator.py's `power_respect_peak` read), not just into an inert dict entry.
    With zero tracked peak headroom, Power would otherwise be clamped to 0 A by R3 (design doc
    Sec 7) -- turning the opt-out on must still command the full default target current."""
    calls = capture_charger_current_writes(hass)
    seed_charger_states(hass, status="Charging")  # net_power/charger_power both 0.0 -- no headroom.
    options = entry_options_base()
    options[CONF_POWER_RESPECT_PEAK] = False

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_POWER)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.smart_charging_status").state == STATUS_OK
    assert calls[-1]["value"] == 10.0  # default_target_current, unclamped by R3.


async def test_setup_threads_deadline_and_soc_management_options_into_coordinator_config(hass):
    """#327 (T6.1): setup must wire the Deadline & SOC Management epic's options (Phase 3's
    CONF_EV_BATTERY_CAPACITY_KWH/CONF_MAX_SOLAR_SOC/CONF_SOLAR_STEP_PP/
    CONF_SOLAR_STEP_THRESHOLD_PP/CONF_SOLAR_RESERVE_SOC/CONF_SOLAR_FORECAST_THRESHOLD_KWH,
    consumed via `self._config.get(...)` in coordinator.py's R8/R9/R15 wiring) into the
    coordinator's config dict as non-default overrides, not just fall back to the coordinator's
    own internal defaults."""
    seed_charger_states(hass, status="Charging")
    options = entry_options_base()
    options[CONF_EV_BATTERY_CAPACITY_KWH] = 60.0
    options[CONF_MAX_SOLAR_SOC] = 90.0
    options[CONF_SOLAR_STEP_PP] = 10.0
    options[CONF_SOLAR_STEP_THRESHOLD_PP] = 5.0
    options[CONF_SOLAR_RESERVE_SOC] = 70.0
    options[CONF_SOLAR_FORECAST_THRESHOLD_KWH] = 20.0

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    config = coordinator._config
    assert config[CONF_EV_BATTERY_CAPACITY_KWH] == 60.0
    assert config[CONF_MAX_SOLAR_SOC] == 90.0
    assert config[CONF_SOLAR_STEP_PP] == 10.0
    assert config[CONF_SOLAR_STEP_THRESHOLD_PP] == 5.0
    assert config[CONF_SOLAR_RESERVE_SOC] == 70.0
    assert config[CONF_SOLAR_FORECAST_THRESHOLD_KWH] == 20.0


async def test_solar_reserve_soc_option_threaded_engages_configured_cap_live(hass, freezer):
    """#327 (T6.1): behavioral companion to the dict-wiring test above -- proves
    CONF_SOLAR_RESERVE_SOC actually flows from the config entry's options into a live cycle's
    R9 reserve cap (coordinator.py's `SocGateResolver.resolve` read, ADR-0012), not just into an
    inert dict entry. Sun down, ample forecast, home day, no departure deadline anywhere -> R9's
    reserve engages (UC07 main success scenario) at the *configured* 70.0, not
    DEFAULT_SOLAR_RESERVE_SOC (60.0).

    Frozen on a Saturday so "no departure deadline anywhere" (Sat/Sun's own R14 default is
    None) is genuinely true of the real departure-time entities (ADR-0018, issue #402) --
    unfrozen, this precondition would depend on the real wall-clock weekday."""
    freezer.move_to("2026-01-17 12:00:00")
    seed_charger_states(hass, status="Charging")
    hass.states.async_set("sun.sun", SUN_STATE_BELOW_HORIZON)
    hass.states.async_set("sensor.solar_forecast", "20.0")  # above the 12 kWh default threshold
    data = entry_data_base()
    data[CONF_SOLAR_FORECAST_ENTITY] = "sensor.solar_forecast"
    options = entry_options_base()
    options[CONF_SOLAR_RESERVE_SOC] = 70.0

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    seed_owned_entity(hass, "select.smart_charging_profile", PROFILE_AUTO)
    seed_owned_entity(hass, "switch.smart_charging_home_day", "on")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_active_soc_limit")
    assert float(hass.states.get(entity_id).state) == 70.0


async def test_select_omits_captar_when_unavailable(hass):
    """T6.1: CONF_CAPTAR_AVAILABLE=False must withhold Captar from the mode selector."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_CAPTAR_AVAILABLE] = False

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_mode")
    state = hass.states.get(entity_id)
    assert MODE_CAPTAR not in state.attributes["options"]


async def test_every_owned_entity_id_matches_entity_catalog(hass):
    """ADR-0013: every owned entity registers under its documented entity-catalog id (or,
    for `target_current`, its pre-existing id -- no catalog row exists for it, design §2),
    independent of the translated display name. Looked up by unique_id so the test asserts
    the GENERATED id equals the catalog id (the property under test)."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    # Solar/EV-SOC config is not required for any owned entity's creation -- none is
    # capability-gated -- but is set anyway so this test exercises the widest entity
    # population, same as test_select_entity_is_registered_on_setup above.
    data[CONF_SOLAR_INSTALLED] = True
    data[CONF_EV_SOC_ENTITY] = "sensor.ev_soc"  # seed_charger_states already seeds sensor.ev_soc
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    # (unique_id suffix, expected catalog entity_id) for all 23 owned entities.
    expected = {
        "mode": "select.smart_charging_mode",
        "profile": "select.smart_charging_profile",
        "target_current": "number.smart_charging_target_current",  # no catalog row (design §2)
        "soc_limit_override": "number.smart_charging_soc_limit_override",
        "status": "sensor.smart_charging_status",
        "active_mode": "sensor.smart_charging_active_mode",
        "monthly_peak_kw": "sensor.smart_charging_monthly_peak_kw",
        "effective_peak_limit": "sensor.smart_charging_effective_peak_limit",
        "active_soc_limit": "sensor.smart_charging_active_soc_limit",
        "solar_surplus_w": "sensor.smart_charging_solar_surplus_w",
        "peak_headroom_a": "sensor.smart_charging_peak_headroom_a",
        "time_to_full": "sensor.smart_charging_time_to_full",
        "adapter_readings": "sensor.smart_charging_adapter_readings",
        "home_day": "switch.smart_charging_home_day",
        "departure_mon": "time.smart_charging_departure_mon",
        "departure_tue": "time.smart_charging_departure_tue",
        "departure_wed": "time.smart_charging_departure_wed",
        "departure_thu": "time.smart_charging_departure_thu",
        "departure_fri": "time.smart_charging_departure_fri",
        "departure_sat": "time.smart_charging_departure_sat",
        "departure_sun": "time.smart_charging_departure_sun",
        "departure_holiday": "time.smart_charging_departure_holiday",
        "departure_home_day": "time.smart_charging_departure_home_day",
    }
    for uid_suffix, want_id in expected.items():
        domain = want_id.split(".", 1)[0]
        got = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{uid_suffix}")
        assert got == want_id, f"{uid_suffix}: {got!r} != {want_id!r}"

    # No owned entity may be missing from `expected` above -- a future owned entity added
    # without a pin here would otherwise pass this test silently (ADR-0013's last consequence).
    # Domain-qualified so a same-suffix entity registered under a *different* platform (e.g.
    # a future sensor.smart_charging_home_day alongside the home_day switch) can't be absorbed
    # into the set and escape the forward loop above undetected.
    expected_by_domain = {
        (want_id.split(".", 1)[0], uid_suffix) for uid_suffix, want_id in expected.items()
    }
    registered = {
        (e.domain, e.unique_id.removeprefix(f"{entry.entry_id}_"))
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert registered == expected_by_domain


async def test_reload_does_not_leak_the_notify_adapters_action_listener(hass):
    """issue #498: `NotifyAdapter._unsub` was stored but never called, so each config-entry
    reload (setup->unload->setup) registered another bus listener without unsubscribing the
    old one -- a per-reload listener leak. Reloads (not just a bare unload) so this actually
    exercises the leak the issue reports."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    baseline = hass.bus.async_listeners().get(EVENT_MOBILE_APP_NOTIFICATION_ACTION, 0)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    after_setup = hass.bus.async_listeners().get(EVENT_MOBILE_APP_NOTIFICATION_ACTION, 0)
    assert after_setup - baseline == 1

    for _ in range(2):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        after_reload = hass.bus.async_listeners().get(EVENT_MOBILE_APP_NOTIFICATION_ACTION, 0)
        assert after_reload - baseline == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    after_unload = hass.bus.async_listeners().get(EVENT_MOBILE_APP_NOTIFICATION_ACTION, 0)
    assert after_unload == baseline


async def test_setup_schedules_the_notification_manager_tick_on_the_configured_interval(hass):
    """Task 5.2: M3's periodic evaluation runs on the same control interval M1 uses (design
    Sec5's C1-style timer, not a bespoke schedule of its own) -- a non-default interval, to
    catch an implementation that hardcodes DEFAULT_CONTROL_INTERVAL_S instead of reading the
    entry's own configured value."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    options = entry_options_base()
    options[CONF_CONTROL_INTERVAL_S] = 60
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options)
    entry.add_to_hass(hass)

    with patch(_NOTIFICATION_MANAGER_EVALUATE, new_callable=AsyncMock) as mock_evaluate:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert mock_evaluate.call_count == 0  # no eager tick at setup itself

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=DEFAULT_CONTROL_INTERVAL_S)
        )
        await hass.async_block_till_done()
        assert mock_evaluate.call_count == 0  # too soon for the configured 60 s interval

        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
        await hass.async_block_till_done()

    assert mock_evaluate.call_count == 1


async def test_unload_cancels_the_notification_manager_tick(hass):
    """Teardown cancels M3's scheduled evaluation cleanly -- no further ticks after unload."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    with patch(_NOTIFICATION_MANAGER_EVALUATE, new_callable=AsyncMock) as mock_evaluate:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=DEFAULT_CONTROL_INTERVAL_S * 2)
        )
        await hass.async_block_till_done()

    assert mock_evaluate.call_count == 0


async def test_reload_does_not_double_schedule_the_notification_manager_tick(hass):
    """issue #498 fixed exactly this class of bug for NotifyAdapter's bus listener -- the
    same per-reload leak risk applies to the tick's own async_on_unload registration.
    Reload twice, then fire one interval: exactly one call, not two or three."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)

    with patch(_NOTIFICATION_MANAGER_EVALUATE, new_callable=AsyncMock) as mock_evaluate:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        for _ in range(2):
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=DEFAULT_CONTROL_INTERVAL_S)
        )
        await hass.async_block_till_done()

    assert mock_evaluate.call_count == 1


async def test_setup_without_a_notification_target_still_schedules_the_tick(hass):
    """Setup schedules the tick unconditionally, the same way the coordinator's own cycle
    runs regardless of which hardware roles are mapped -- M3's own inertness without a
    mapped notification target is that module's own contract (tests/managers/
    test_notification_manager.py), not re-proven here since async_evaluate is mocked out."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)

    with patch(_NOTIFICATION_MANAGER_EVALUATE, new_callable=AsyncMock) as mock_evaluate:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=DEFAULT_CONTROL_INTERVAL_S)
        )
        await hass.async_block_till_done()

    assert mock_evaluate.call_count == 1


async def test_setup_threads_evening_prompt_options_into_notification_manager_config(hass):
    """Task 5.2: the evening-prompt options must reach M3's own config, not just fall back to
    its internal defaults -- deleting the __init__.py lines that thread them would not fail
    any tick/schedule test, since those mock async_evaluate out entirely."""
    seed_charger_states(hass, status="Charging")
    options = entry_options_base()
    options[CONF_EVENING_PROMPT_ENABLED] = False
    options[CONF_EVENING_PROMPT_TIME] = "20:30:00"
    options[CONF_SOLAR_FORECAST_THRESHOLD_KWH] = 9.0

    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    manager = entry.runtime_data.notification_manager
    assert manager._enabled is False
    assert manager._prompt_time == time(20, 30, 0)
    assert manager._threshold_kwh == 9.0


async def test_setup_registers_the_deadline_unreachable_listener(hass):
    """Task 6.1: M3 subscribes to the Coordinator's own DeadlineUnreachableNotified event at
    setup and delivers the R5 notice via RA4 on receipt."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    hass.services.async_register("notify", "send_message", AsyncMock())
    calls = capture_service_calls(hass, "notify", "send_message")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: 12.5})
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0]["entity_id"] == "notify.mobile_app_phone"


async def test_unload_cancels_the_deadline_unreachable_listener(hass):
    """Teardown unsubscribes M3's DeadlineUnreachableNotified listener cleanly (ADR-0008) --
    no delivery after unload."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    hass.services.async_register("notify", "send_message", AsyncMock())
    calls = capture_service_calls(hass, "notify", "send_message")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: 12.5})
    await hass.async_block_till_done()

    assert calls == []


async def test_deadline_unreachable_notice_is_delivered_only_once_through_setup(hass):
    """End-to-end confirmation of the manager's own notify-once latch (tests/managers/
    test_notification_manager.py's unit-level coverage) -- two events through the real
    wiring still deliver only the first."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    hass.services.async_register("notify", "send_message", AsyncMock())
    calls = capture_service_calls(hass, "notify", "send_message")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: 12.5})
    await hass.async_block_till_done()
    hass.bus.async_fire(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: 14.0})
    await hass.async_block_till_done()

    assert len(calls) == 1


async def test_reload_does_not_double_deliver_the_deadline_unreachable_notice(hass):
    """The same per-reload leak class issue #498 fixed for NotifyAdapter's own bus listener,
    and #534's tick registration already guards against -- reload twice, fire once: exactly
    one delivery, not two or three."""
    seed_charger_states(hass, status="Charging")
    data = entry_data_base()
    data[CONF_NOTIFICATION_TARGET_ENTITY] = "notify.mobile_app_phone"
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    hass.services.async_register("notify", "send_message", AsyncMock())
    calls = capture_service_calls(hass, "notify", "send_message")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for _ in range(2):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    hass.bus.async_fire(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, {ATTR_REQUIRED_CURRENT_A: 12.5})
    await hass.async_block_till_done()

    assert len(calls) == 1


async def test_unload_without_a_notification_target_mapped_still_succeeds(hass):
    """Every existing entry predates the notify-target mapping (it's optional, NF3) -- the
    common no-`NotifyAdapter` case must unload cleanly too, not just the mapped case above."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # HA's own ConfigEntry.async_unload deletes `entry.runtime_data` after a successful
    # unload (object.__delattr__) -- the direct successor to the old assertion that this
    # entry's `hass.data[DOMAIN]` bookkeeping was cleaned up (issue #568 removed that
    # bookkeeping entirely in favor of runtime_data).
    assert not hasattr(entry, "runtime_data")
    assert entry.state is ConfigEntryState.NOT_LOADED


# --- Task 5.1: M2 (Vehicle-Limit Manager) construction + its three state-change listeners ---

_VEHICLE_LIMIT_DATA_OVERRIDES = {
    CONF_VEHICLE_CHARGE_LIMIT_ENTITY: "number.car_limit",
    CONF_CAR_HOME_ENTITY: "device_tracker.car",
    CONF_STATUS_TRANSLATION: {
        "Charging": STATE_CHARGING,
        "Connected": STATE_CONNECTED,
        "Disconnected": STATE_DISCONNECTED,
    },
}


def _vehicle_writes(calls):
    """Filter a live number.set_value capture (tests/helpers.py's capture_service_calls) down
    to the mapped vehicle entity, so they aren't confused with the real
    number.charger_current writes M1 also issues during the same setup cycle. A plain
    filter, not its own capture, so it can be called after the actions under test append to
    the still-live `calls` list (issue #340 review)."""
    return [call for call in calls if call.get("entity_id") == "number.car_limit"]


async def _setup_vehicle_limit_entry(hass, *, status="Connected", home="home"):
    data = entry_data_base(**_VEHICLE_LIMIT_DATA_OVERRIDES)
    seed_charger_states(hass, status=status)
    hass.states.async_set("number.car_limit", "65")
    hass.states.async_set("device_tracker.car", home)

    entry = MockConfigEntry(domain=DOMAIN, data=data, options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_vehicle_limit_manager_constructed_when_mapped(hass):
    """Task 5.1: setup constructs M2 only when vehicle_charge_limit is mapped."""
    entry = await _setup_vehicle_limit_entry(hass)

    assert entry.runtime_data.vehicle_limit_manager is not None


async def test_no_vehicle_limit_manager_when_unmapped(hass):
    """UC09 precondition / design §5.4 success criterion 6: no vehicle_charge_limit mapping
    -> M2 stays uninstantiated and registers no listeners at all -- driving the
    active-SOC-limit sensor afterwards must not raise (no manager to react) or write
    anything (there is no vehicle adapter to write through in the first place)."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.vehicle_limit_manager is None

    hass.states.async_set("sensor.smart_charging_active_soc_limit", "90")
    await hass.async_block_till_done()  # must not raise


async def test_vehicle_limit_listener_adopts_a_manual_vehicle_change(hass):
    """UC09 steps 4-6 / R6 AC 5: driving the mapped vehicle_charge_limit entity reaches M2's
    adoption reaction, writing the real owned soc_limit_override entity through the Store."""
    await _setup_vehicle_limit_entry(hass)
    events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)

    hass.states.async_set("number.car_limit", "55")
    await hass.async_block_till_done()

    assert len(events) == 1
    assert hass.states.get("number.smart_charging_soc_limit_override").state == "55.0"


async def test_vehicle_limit_listener_ignores_an_unavailable_vehicle_reading(hass):
    """ADR-0003: the vehicle-change listener re-reads through ROLE_VEHICLE_CHARGE_LIMIT
    (NumericReadAdapter's own None-coercion for missing/unavailable/non-numeric) rather than
    parsing `event.data["new_state"].state` directly -- a raw "unavailable" transition would
    otherwise reach `on_vehicle_limit_changed` as the literal string "unavailable", not
    `None`, and crash on `float(...)` inside the reaction -- this pins the
    read-through-the-adapter choice at the wiring layer, distinguishing it from that
    regression."""
    await _setup_vehicle_limit_entry(hass)
    events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)

    hass.states.async_set("number.car_limit", "unavailable")
    await hass.async_block_till_done()

    assert len(events) == 0
    assert hass.states.get("number.smart_charging_soc_limit_override").state == "80.0"


async def test_vehicle_limit_listener_resets_vehicle_on_disconnect(hass):
    """UC09 steps 7-8 / R6 AC 3: driving the mapped charger_status entity to a disconnect
    edge reaches M2's reset reaction, which reads the canonical status through the
    ROLE_CHARGER_STATUS adapter (translation applied) and writes the vehicle's default.

    Setup seeds `_last_status` from the already-current "Connected" reading via
    `prime_status` (Task 5.1) -- without it, a freshly registered listener would only ever
    observe changes after subscription, never the state that was already current, and this
    single disconnect transition would be silently missed (design §5.3)."""
    await _setup_vehicle_limit_entry(hass, status="Connected")
    calls = capture_service_calls(hass, "number", "set_value")
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_RESET)

    hass.states.async_set("sensor.evse", "Disconnected")
    await hass.async_block_till_done()

    assert len(events) == 1
    assert _vehicle_writes(calls) == [{"entity_id": "number.car_limit", "value": 80.0}]


async def test_vehicle_limit_listener_writes_vehicle_on_active_soc_limit_change(hass):
    """UC09 step 2 / R6 AC 2: driving the materialized active-SOC-limit sensor reaches M2's
    System->vehicle write reaction (connected + at home, C2)."""
    await _setup_vehicle_limit_entry(hass, status="Charging", home="home")
    calls = capture_service_calls(hass, "number", "set_value")
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_SYNCED)

    hass.states.async_set("sensor.smart_charging_active_soc_limit", "90")
    await hass.async_block_till_done()

    assert len(events) == 1
    assert _vehicle_writes(calls) == [{"entity_id": "number.car_limit", "value": 90.0}]


async def test_vehicle_limit_listener_survives_active_soc_limit_id_collision(hass):
    """Issue #562 regression: register_listeners must resolve the active-SOC-limit sensor's
    real entity_id through the Store's registry lookup (by unique_id), not a hardcoded
    literal (ADR-0013's locale/rename concern). Pre-claiming the literal
    `sensor.smart_charging_active_soc_limit` object_id with an unrelated entity forces HA to
    assign our sensor a suffixed id (`_2`) instead -- a hardcoded-literal listener would
    silently watch the wrong (unrelated) entity and never observe the real sensor's changes."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        "other_integration",
        "unrelated_unique_id",
        suggested_object_id="smart_charging_active_soc_limit",
    )

    entry = await _setup_vehicle_limit_entry(hass, status="Charging", home="home")
    calls = capture_service_calls(hass, "number", "set_value")
    events = async_capture_events(hass, EVENT_VEHICLE_CHARGE_LIMIT_SYNCED)

    real_entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_active_soc_limit"
    )
    assert real_entity_id == "sensor.smart_charging_active_soc_limit_2"

    hass.states.async_set(real_entity_id, "90")
    await hass.async_block_till_done()

    assert len(events) == 1
    assert _vehicle_writes(calls) == [{"entity_id": "number.car_limit", "value": 90.0}]


async def test_vehicle_limit_listener_does_not_write_when_away(hass):
    """UC09 alt 2a / R6 AC 4 / C2: away -> the active-SOC-limit listener must not write."""
    await _setup_vehicle_limit_entry(hass, status="Charging", home="not_home")
    calls = capture_service_calls(hass, "number", "set_value")

    hass.states.async_set("sensor.smart_charging_active_soc_limit", "90")
    await hass.async_block_till_done()

    assert _vehicle_writes(calls) == []


async def test_unload_cancels_vehicle_limit_listeners(hass):
    """ADR-0008: M2's listeners live only while the entry is loaded -- unload tears them
    down, so a subsequent vehicle-side change no longer reaches the manager's reaction at
    all. Spies on the reaction itself (not the resulting event/Store write) so a
    leaked-but-failing write can't make this pass for the wrong reason -- Store.write
    swallows every failure and returns False, which would otherwise also read as "no
    event fired"."""
    entry = await _setup_vehicle_limit_entry(hass)
    manager = entry.runtime_data.vehicle_limit_manager

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    with patch.object(manager, "on_vehicle_limit_changed", AsyncMock()) as reaction:
        hass.states.async_set("number.car_limit", "55")
        await hass.async_block_till_done()

    reaction.assert_not_called()


async def test_reload_does_not_double_register_vehicle_limit_listeners(hass):
    """ADR-0008: a reload tears down and re-registers exactly once -- two reloads followed by
    one vehicle-side change must adopt exactly once, not two or three times (the same
    per-reload leak class issue #498 fixed for NotifyAdapter's bus listener)."""
    entry = await _setup_vehicle_limit_entry(hass)

    for _ in range(2):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    events = async_capture_events(hass, EVENT_MANUAL_CHARGE_LIMIT_ADOPTED)
    hass.states.async_set("number.car_limit", "55")
    await hass.async_block_till_done()

    assert len(events) == 1
