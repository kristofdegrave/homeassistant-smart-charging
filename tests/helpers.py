"""Shared end-to-end test helpers for the Smart Charging HA-harness suites.

These helpers (``entry_data_base``, ``entry_options_base``, ``seed_charger_states``,
``capture_charger_current_writes``, ``seed_ample_peak_headroom``, ``seed_today_deadline``,
``AMPLE_PEAK_HEADROOM_KW``) are the shared shape promoted from ``tests/test_init.py``,
``tests/test_coordinator.py``, ``tests/test_captar_end_to_end.py``,
``tests/test_deadline_soc_management_end_to_end.py``, and ``tests/test_solar_end_to_end.py``
(issue #411, follow-up from PR #407's code-reviewer findings): those files had each grown
near-verbatim copies of the same config-entry/coordinator seeding helpers. Each importing
suite still owns its own scenario-specific overrides -- these only give the identical common
shape one source of truth.

Deliberately kept out of ``tests/conftest.py``: everything here needs ``homeassistant`` and
the integration package, which would otherwise make ``conftest.py`` -- imported for every test
under ``tests/``, including the pure-logic dirs (ADR-0009) -- transitively require HA at
collection time.
"""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.smart_charging.const import (
    CONF_CHARGER_CURRENT_ENTITY,
    CONF_CHARGER_POWER_ENTITY,
    CONF_CHARGER_STATUS_ENTITY,
    CONF_DEFAULT_SOC_LIMIT,
    CONF_DEFAULT_TARGET_CURRENT,
    CONF_GRID_CEILING_A,
    CONF_GRID_SAFETY_OFFSET_A,
    CONF_GRID_VOLTAGE_ENTITY,
    CONF_MAX_CURRENT,
    CONF_MIN_CURRENT,
    CONF_NET_POWER_ENTITY,
    CONF_NOMINAL_VOLTAGE,
    CONF_STATUS_TRANSLATION,
    OWNED_SUFFIX_DEPARTURE_DOW,
    STATE_CHARGING,
    STATE_CONNECTED,
)

# Keeps R3's clamp out of the way of tests that exercise unrelated behavior, not R3 itself.
AMPLE_PEAK_HEADROOM_KW = 100.0


def entry_data_base(**overrides):
    """DATA bucket -- entity-role mappings + translation only (ADR-0005).

    Callers layer their own scenario-specific keys (or override a base one, e.g. a
    narrower ``CONF_STATUS_TRANSLATION``) via ``overrides`` -- this only fixes the common
    shape every end-to-end suite's config entry starts from.
    """
    data = {
        CONF_CHARGER_CURRENT_ENTITY: "number.charger_current",
        CONF_CHARGER_STATUS_ENTITY: "sensor.evse",
        CONF_STATUS_TRANSLATION: {"Charging": STATE_CHARGING, "Connected": STATE_CONNECTED},
        CONF_NET_POWER_ENTITY: "sensor.net_power",
        CONF_CHARGER_POWER_ENTITY: "sensor.charger_power",
        CONF_GRID_VOLTAGE_ENTITY: "sensor.grid_voltage",
    }
    data.update(overrides)
    return data


def entry_options_base(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005).

    Callers layer their own scenario-specific keys on top via ``overrides``.
    """
    options = {
        CONF_NOMINAL_VOLTAGE: 230.0,
        CONF_MIN_CURRENT: 6.0,
        CONF_MAX_CURRENT: 16.0,
        CONF_GRID_CEILING_A: 25.0,
        CONF_GRID_SAFETY_OFFSET_A: 2.0,
        CONF_DEFAULT_TARGET_CURRENT: 10.0,
        CONF_DEFAULT_SOC_LIMIT: 80.0,
    }
    options.update(overrides)
    return options


def seed_charger_states(hass, *, status, net_w=0.0, charger_w=0.0, ev_soc=50.0, grid_voltage=230.0):
    """Seed the raw entity states a config-entry-driven coordinator cycle reads from.

    Every end-to-end suite seeds the same five/six entities; a suite that doesn't map a
    given role (e.g. no `ev_soc` entity configured, or no `grid_voltage` role -- the NF4
    unmapped-role path) just leaves the corresponding state unused rather than omitting it
    here.
    """
    hass.states.async_set("number.charger_current", "0.0")
    hass.states.async_set("sensor.evse", status)
    hass.states.async_set("sensor.net_power", str(net_w))
    hass.states.async_set("sensor.charger_power", str(charger_w))
    hass.states.async_set("sensor.grid_voltage", str(grid_voltage))
    hass.states.async_set("sensor.ev_soc", str(ev_soc))


def capture_service_calls(hass, domain: str, service: str):
    """Capture every call_service event for one domain/service pair, regardless of which
    entity is targeted or whether any real entity backs it.

    Listening on the bus event itself (rather than registering a fake service handler, or
    checking the target's resulting state) works uniformly whether the target is a real
    owned entity (whose own real handler would otherwise clobber a fake one) or an
    externally-mapped adapter target with no backing entity object at all (whose state
    can't be checked directly) -- `capture_charger_current_writes` below is this function
    specialised to the one domain/service every end-to-end suite already relied on before
    a second call site needed the same shape (issue #340 review).
    """
    calls = []

    def _record(event):
        if event.data["domain"] == domain and event.data["service"] == service:
            calls.append(event.data["service_data"])

    hass.bus.async_listen("call_service", _record)
    return calls


def capture_charger_current_writes(hass):
    """Capture number.set_value calls targeting the charger-current entity."""
    return capture_service_calls(hass, "number", "set_value")


def seed_ample_peak_headroom(coordinator, kw=AMPLE_PEAK_HEADROOM_KW):
    """Pre-seed the Peak-Demand Tracker as though a large historical peak already exists
    (the same shape a MonthlyPeakSensor restore would seed, Task 4.2) -- keeps R3's clamp
    out of the way of tests that exercise unrelated behavior, not R3 itself."""
    now_dt = dt_util.now()
    coordinator.seed_monthly_peak(kw, (now_dt.year, now_dt.month))


def seed_owned_entity(hass, entity_id: str, state: str) -> None:
    """Seed a real owned entity's HA state directly (mirrors seed_charger_states' existing
    pattern for mapped hardware entities) -- what the RA3 Store reads (ADR-0018), replacing a
    test's former direct coordinator.<field> = ... assignment now that the Coordinator reads
    these fields through the Store each cycle instead of taking a pushed value."""
    hass.states.async_set(entity_id, state)


def seed_today_deadline(hass, *, hours_from_now):
    """Seed today's departure-deadline default via the real
    time.smart_charging_departure_<dow> entity (ADR-0018), so it resolves `hours_from_now`
    ahead of real wall-clock now (the deadline/required-current resolution reads
    dt_util.now(), not the mode state machines' injected monotonic clock)."""
    now_dt = dt_util.now()
    entity_id = f"time.smart_charging_{OWNED_SUFFIX_DEPARTURE_DOW[now_dt.weekday()]}"
    seed_owned_entity(
        hass, entity_id, (now_dt + timedelta(hours=hours_from_now)).time().isoformat()
    )
