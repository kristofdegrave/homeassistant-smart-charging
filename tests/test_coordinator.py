"""HA-harness tests for the control cycle (M1, ADR-0006/0007)."""

import dataclasses
import logging
from datetime import time as time_of_day
from datetime import timedelta

import pytest
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from custom_components.smart_charging import coordinator as coordinator_module
from custom_components.smart_charging.adapters.sun import (
    SUN_STATE_ABOVE_HORIZON,
    SUN_STATE_BELOW_HORIZON,
)
from custom_components.smart_charging.config import SmartChargingConfig
from custom_components.smart_charging.const import (
    ATTR_ACTIVE_SOC_LIMIT,
    ATTR_REQUIRED_CURRENT_A,
    DEFAULT_CAPTAR_AVAILABLE,
    EVENT_ACTIVE_SOC_LIMIT_CHANGED,
    EVENT_DEADLINE_UNREACHABLE_CLEARED,
    EVENT_DEADLINE_UNREACHABLE_NOTIFIED,
    MODE_CAPTAR,
    MODE_OFF,
    MODE_POWER,
    MODE_SOLAR,
    MODE_SOLAR_ONLY,
    OWNED_SUFFIX_DEPARTURE_DOW,
    OWNED_SUFFIX_DEPARTURE_HOLIDAY,
    OWNED_SUFFIX_DEPARTURE_HOME_DAY,
    OWNED_SUFFIX_HOME_DAY,
    OWNED_SUFFIX_MODE,
    OWNED_SUFFIX_PROFILE,
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    OWNED_SUFFIX_TARGET_CURRENT,
    PROFILE_AUTO,
    PROFILE_MANUAL,
    ROLE_CHARGER_CURRENT,
    ROLE_CHARGER_POWER,
    ROLE_CHARGER_STATUS,
    ROLE_DEPARTURE_EXTERNAL,
    ROLE_EV_BATTERY_CAPACITY,
    ROLE_EV_SOC,
    ROLE_GRID_VOLTAGE,
    ROLE_LOW_TARIFF,
    ROLE_NET_POWER,
    ROLE_NOTIFICATION_TARGET,
    ROLE_SOLAR_FORECAST,
    ROLE_SUN,
    ROLES_ADAPTER_READINGS_EXCLUDED,
    SOC_LIMIT_OVERRIDE_MAX,
    SOC_LIMIT_OVERRIDE_MIN,
    STATE_CHARGING,
    STATE_DISCONNECTED,
)
from custom_components.smart_charging.coordinator import SmartChargingCoordinator
from custom_components.smart_charging.engines.soc_target import SolarStepUpState
from custom_components.smart_charging.modes._phase import Phase
from custom_components.smart_charging.modes.captar import CaptarState
from custom_components.smart_charging.modes.solar import SolarState
from custom_components.smart_charging.modes.solar_only import SolarOnlyState
from tests.config_factory import make_test_config
from tests.helpers import AMPLE_PEAK_HEADROOM_KW, seed_ample_peak_headroom

# ADR-0007 fault-path log text (issue #504) -- named here, not repeated as bare literals,
# since two tests below assert against the exact strings coordinator.py logs.
_FAULT_WRITE_SWALLOW_LOG = "smart_charging failed to write 0 A during fault"
_REQUIRED_ADAPTER_NONE_REASON = "required adapter returned None"
_EV_SOC_MISSING_REASON = "ev_soc required while a solar mode is active but missing/None"


class _FakeNumeric:
    def __init__(self, value):
        self._value = value
        self.written = []

    async def read(self):
        return self._value

    async def write(self, value):
        self.written.append(value)


class _FakeStatus:
    def __init__(self, canonical):
        self._canonical = canonical

    async def read(self):
        return self._canonical


class _RaisingNumeric:
    async def read(self):
        raise RuntimeError("adapter unavailable")

    async def write(self, value):
        raise AssertionError("should not be called by a raising read")


class _RaisingWriteNumeric:
    """Read succeeds; write raises -- for testing _safe_write_zero's exception swallow and
    the write-adapter-faults-during-early-fault-return paths (ADR-0007, issue #504). Unlike
    _RaisingNumeric (which fails the *read* and is never expected to reach write()), this
    fakes a charger current adapter whose write-back itself fails while ROLE_CHARGER_CURRENT
    is being force-zeroed during an already-detected fault. Mirrors _FakeNumeric by recording
    every write attempt (before raising), so a test can still assert how many zero-write
    attempts a fault path made."""

    def __init__(self, value=0.0):
        self._value = value
        self.written = []

    async def read(self):
        return self._value

    async def write(self, value):
        self.written.append(value)
        raise RuntimeError("charger write failed")


class _FakeStore:
    """Returns a fixed value per (entity_domain, unique_id_suffix) key, None otherwise --
    stands in for adapters/store.py's Store without touching the entity registry. {} means
    every read() returns None, so _read_owned_entities() is a no-op -- every existing
    SmartChargingCoordinator(...) construction in this file passes store=_FakeStore({})
    precisely so it never disturbs a test's own direct field assignments.

    Asserts the caller's requested value_type against the fixture's own stored value --
    unlike the real Store (which coerces a raw HA state string), this fake stores already-typed
    Python values, so it cannot coerce; but it can and does catch a caller passing the wrong
    value_type for a given (entity_domain, unique_id_suffix) key, which the real Store would
    silently turn into a permanent None (a coercion failure, e.g. float() on a time string) --
    exactly the failure mode a mis-paired row in _read_owned_entities' `simple_reads` table
    (#652) would otherwise produce without any test noticing."""

    def __init__(self, values: dict[tuple[str, str], object]) -> None:
        self._values = values

    async def read(self, entity_domain, unique_id_suffix, value_type):
        value = self._values.get((entity_domain, unique_id_suffix))
        if value is not None and not isinstance(value, value_type):
            raise AssertionError(
                f"_FakeStore: {entity_domain}/{unique_id_suffix} was read as {value_type!r} "
                f"but the fixture holds a {type(value)!r} value -- likely a mis-paired "
                f"(platform, suffix, value_type) row"
            )
        return value


def _adapters(
    status=STATE_CHARGING,
    net_w=0.0,
    charger_w=0.0,
    voltage=230.0,
    ev_soc_role=True,
    ev_soc=50.0,
    sun_state=None,
    low_tariff=None,
):
    adapters = {
        ROLE_CHARGER_CURRENT: _FakeNumeric(0.0),
        ROLE_CHARGER_STATUS: _FakeStatus(status),
        ROLE_NET_POWER: _FakeNumeric(net_w),
        ROLE_CHARGER_POWER: _FakeNumeric(charger_w),
        ROLE_GRID_VOLTAGE: _FakeNumeric(voltage),
        # ROLE_SUN is built unconditionally by the real factory (issue #376) -- present
        # here too, `sun_state=None` (both sun_is_up/sun_is_down False) matching the prior
        # default behavior of an unset sun.sun entity.
        ROLE_SUN: _FakeNumeric(sun_state),
    }
    if ev_soc_role:
        adapters[ROLE_EV_SOC] = _FakeNumeric(ev_soc)
    if low_tariff is not None:
        adapters[ROLE_LOW_TARIFF] = _FakeNumeric(low_tariff)
    return adapters


def _config(**overrides) -> SmartChargingConfig:
    """This suite's own SmartChargingConfig baseline, layered on tests/config_factory.py's
    shared production-DEFAULT_*-seeded factory (issue #570 follow-up: three near-identical
    per-suite factories collapsed to one). The four overrides below are THIS file's own
    long-standing baseline values, deliberately distinct from the production defaults
    `make_test_config` otherwise uses, so existing test expectations are unchanged. `**overrides`
    takes the dataclass's own field names (not CONF_* constants) -- pass e.g.
    `_config(max_peak_kw=7.5)` for a non-default value, or mutate an already-built config with
    `dataclasses.replace`."""
    return make_test_config(
        smoothing_window=1,
        solar_start_threshold_w=100.0,
        solar_only_start_threshold_w=100.0,
        captar_cooldown_min=5.0,
        **overrides,
    )


def _seed_today_deadline(coord, hours_from_now):
    """This file constructs SmartChargingCoordinator directly with a _FakeStore, so there is
    no real time.smart_charging_departure_<dow> entity for tests.helpers.seed_today_deadline
    to seed -- seed the coordinator's own field directly instead, same as this file's other
    direct-construction tests."""
    now_dt = dt_util.now()
    coord.departure_dow_defaults[now_dt.weekday()] = (
        now_dt + timedelta(hours=hours_from_now)
    ).time()


def _seed_ample_peak_headroom(coord, kw=AMPLE_PEAK_HEADROOM_KW):
    seed_ample_peak_headroom(coord, kw=kw)


async def _run(hass, adapters, config, target):
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER  # M1's original default before mode selection existed (Task 5.1)
    coord.target_current = target
    _seed_ample_peak_headroom(coord)
    result = await coord._async_update_data()
    return coord, result


async def _run_mode(hass, adapters, config, active_mode, soc_limit_override=80.0, coord=None):
    if coord is None:
        coord = SmartChargingCoordinator(
            hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
        )
    else:
        coord._adapters = adapters
    coord.active_mode = active_mode
    coord.soc_limit_override = soc_limit_override
    _seed_ample_peak_headroom(coord)
    result = await coord._async_update_data()
    return coord, result


async def test_set_active_profile_sets_the_field(hass):
    """ADR-0014: set_active_profile is the coordinator's own boundary for active_profile."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_active_profile(PROFILE_AUTO)
    assert coord.active_profile == PROFILE_AUTO


async def test_r17_commands_target_when_charging(hass):
    adapters = _adapters(status=STATE_CHARGING)
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert adapters[ROLE_CHARGER_CURRENT].written == [10.0]
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_uc04_zero_when_disconnected(hass):
    adapters = _adapters(status=STATE_DISCONNECTED)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.commanded_current == 0.0
    assert result.fault is False
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


async def test_c4_grid_ceiling_clamps_command(hass):
    # baseline = net 5980 - charger 3680 = 2300 W = 10 A;
    # headroom = (ceiling 25 - offset 2) - 10 = 13 A.
    adapters = _adapters(status=STATE_CHARGING, net_w=5980.0, charger_w=3680.0)
    _coord, result = await _run(hass, adapters, _config(), target=20.0)
    assert result.commanded_current == 13.0


async def test_adr0007_status_none_is_fault_and_forces_zero(hass):
    adapters = _adapters(status=None)  # unmapped/unavailable -> fault
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


@pytest.mark.parametrize("role", [ROLE_NET_POWER, ROLE_CHARGER_POWER])
async def test_adr0007_other_required_roles_none_is_fault(hass, role):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[role] = _FakeNumeric(None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


async def test_adr0007_cycle_exception_is_fault_and_forces_zero(hass):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[ROLE_CHARGER_STATUS] = _RaisingNumeric()
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert result.commanded_current == 0.0
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0]


async def test_adr0007_recovers_after_fault(hass):
    adapters = _adapters(status=None)
    coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is True
    assert coord._was_faulted is True

    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_CHARGING)
    result = await coord._async_update_data()
    assert result.fault is False
    assert coord._was_faulted is False


def _fault_warnings(caplog):
    """Only this module's own WARNING records -- excludes anything an unrelated logger (e.g.
    HA framework) might emit during a cycle, which would otherwise inflate/deflate the count
    this file's caplog assertions rely on."""
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == coordinator_module.__name__
    ]


async def test_adr0007_logs_fault_once_per_outage_not_per_cycle(hass, caplog):
    """ADR-0007: 'each outage logs once at warning level (not once per cycle, to avoid log
    spam)'. Drive three consecutive faulted cycles of the SAME outage and assert the WARNING
    is logged exactly once -- a regression to per-cycle logging (i.e. `_log_fault` warning on
    every faulted cycle instead of only the first) would currently pass green, since no
    existing test inspects caplog (issue #504). A new outage after a recovery must still log
    again, proving this is "once per outage", not "once ever"; the recovery itself must log
    its own once-only INFO message (the ADR's other half of this same sentence)."""
    adapters = _adapters(status=None)  # unmapped/unavailable -> fault
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0
    _seed_ample_peak_headroom(coord)

    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        for _ in range(3):  # same outage, three consecutive cycles
            result = await coord._async_update_data()
            assert result.fault is True

    warnings = _fault_warnings(caplog)
    assert len(warnings) == 1, "expected one WARNING for the whole outage, not one per cycle"
    assert _REQUIRED_ADAPTER_NONE_REASON in warnings[0].getMessage()

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=coordinator_module.__name__):
        adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_CHARGING)  # recover
        result = await coord._async_update_data()
    assert result.fault is False
    recovery_infos = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and r.name == coordinator_module.__name__
    ]
    assert len(recovery_infos) == 1, "recovery must log its own once-only INFO message"
    assert "recovered from fault" in recovery_infos[0].getMessage()

    caplog.clear()
    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(None)  # a new outage, after the recovery above
    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        result = await coord._async_update_data()
        assert result.fault is True

    warnings = _fault_warnings(caplog)
    assert len(warnings) == 1, "a new outage after a recovery must log again, not stay suppressed"


async def test_adr0007_safe_write_zero_swallows_write_exception(hass, caplog):
    """ADR-0007's fault path must not itself raise if the write-back adapter is unavailable:
    _safe_write_zero's try/except must swallow the write exception (logged via
    _LOGGER.exception) rather than let it escape _async_update_data (issue #504)."""
    adapters = _adapters(status=STATE_CHARGING)
    adapters[ROLE_CHARGER_STATUS] = _RaisingNumeric()  # forces the outer cycle-exception fault path
    adapters[ROLE_CHARGER_CURRENT] = _RaisingWriteNumeric()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0
    _seed_ample_peak_headroom(coord)

    with caplog.at_level(logging.ERROR, logger=coordinator_module.__name__):
        result = await coord._async_update_data()  # must not raise

    assert result.fault is True
    assert result.commanded_current == 0.0
    assert _FAULT_WRITE_SWALLOW_LOG in caplog.text


@pytest.mark.parametrize(
    "status,ev_soc,expected_reason",
    [
        # required-adapter-None early-fault return (coordinator.py's `status is None or
        # net_w is None or charger_w is None` branch).
        (None, 50.0, _REQUIRED_ADAPTER_NONE_REASON),
        # ev_soc-missing early-fault return, only reachable with a solar mode active.
        (STATE_CHARGING, None, _EV_SOC_MISSING_REASON),
    ],
)
async def test_adr0007_write_adapter_fault_during_run_cycle_early_fault_return_does_not_escape(
    hass, caplog, status, ev_soc, expected_reason
):
    """Neither of `_run_cycle`'s early-fault returns (the required-adapter-None branch and the
    ev_soc-missing-while-a-solar-mode-is-active branch) call `_safe_write_zero` -- they call
    `self._write(0.0)` directly. If ROLE_CHARGER_CURRENT's write itself raises during one of
    these, the exception must still be rescued (by the outer `_async_update_data` try/except,
    which re-attempts the zero-write via `_safe_write_zero` and swallows it there) rather than
    propagate out of `_async_update_data` -- previously untested for this specific path
    (issue #504). Asserting `expected_reason`'s branch-specific WARNING (logged by `_log_fault`
    before either early return ever reaches its `self._write(0.0)` call) is what binds this
    test to the intended branch -- without it, a fall-through to the normal end-of-cycle write
    (which raises the same way and produces the same fault=True/0.0/swallow-log outcome) would
    pass just as easily, silently no longer exercising the early return at all."""
    adapters = _adapters(status=status, ev_soc=ev_soc)
    adapters[ROLE_CHARGER_CURRENT] = _RaisingWriteNumeric()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_SOLAR  # SOC-gated mode, so the ev_soc-missing branch also faults
    coord.target_current = 10.0
    _seed_ample_peak_headroom(coord)

    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        result = await coord._async_update_data()  # must not raise

    assert result.fault is True
    assert result.commanded_current == 0.0
    assert expected_reason in caplog.text, "expected reason implies the early-return branch fired"
    assert _FAULT_WRITE_SWALLOW_LOG in caplog.text
    # Two zero-write attempts: the early return's own `self._write(0.0)` (which raised), then
    # the outer handler's `_safe_write_zero` retry (which also raised and was swallowed there).
    assert adapters[ROLE_CHARGER_CURRENT].written == [0.0, 0.0]


async def test_nf4_grid_voltage_none_is_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING)
    adapters[ROLE_GRID_VOLTAGE] = _FakeNumeric(None)  # NF4 fallback, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_nf4_grid_voltage_unmapped_is_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING)
    del adapters[ROLE_GRID_VOLTAGE]  # role not configured -> nominal voltage, not a fault
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.fault is False
    assert result.commanded_current == 10.0


async def test_dispatches_to_solar_when_selected(hass):
    # Arrange: surplus = charger_w(2760=12A) - net_w(0) = 2760W = 12A ideal, round-up -> 12A.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert
    assert result.fault is False
    assert result.commanded_current == 12.0
    assert result.active_mode == MODE_SOLAR


async def test_dispatches_to_solar_only_when_selected(hass):
    # Arrange
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_SOLAR_ONLY, soc_limit_override=80.0
    )

    # Assert
    assert result.fault is False
    assert result.commanded_current == 12.0
    assert result.active_mode == MODE_SOLAR_ONLY


@pytest.mark.parametrize(
    ("mode", "idle_state_type"),
    [
        (MODE_SOLAR, SolarState),
        (MODE_SOLAR_ONLY, SolarOnlyState),
        (MODE_CAPTAR, CaptarState),
    ],
)
async def test_soc_at_or_above_limit_forces_zero_and_holds_solar_states_at_idle(
    hass, mode, idle_state_type
):
    # Arrange: ev_soc at the configured limit, with ample surplus that would otherwise charge.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=80.0)

    # Act
    coord, result = await _run_mode(hass, adapters, _config(), mode, soc_limit_override=80.0)

    # Assert
    assert result.commanded_current == 0.0
    # issue #561: pins the state's own TYPE, not just its `.phase` -- a mis-wired
    # ModeHandler.idle_state() returning the wrong mode's state would still have
    # phase == Phase.IDLE (all three *State dataclasses expose it) but fail this isinstance.
    assert isinstance(coord._mode_state[mode], idle_state_type)
    assert coord._mode_state[mode].phase == Phase.IDLE


async def test_resumes_when_the_soc_limit_rises_above_current_soc(hass):
    """R7 resume condition 1. Multi-cycle by nature (a resume is only observable across two
    cycles of the same coordinator), so Arrange/Act/Assert repeats once per cycle below."""
    # Arrange: gated at the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=80.0)

    # Act (cycle 1)
    coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert (cycle 1)
    assert result.commanded_current == 0.0  # gated: ev_soc >= limit

    # Act (cycle 2): the limit rises above the current SOC, same mode, no reconnect.
    coord, result = await _run_mode(
        hass, adapters, _config(), MODE_SOLAR, soc_limit_override=90.0, coord=coord
    )

    # Assert (cycle 2)
    assert result.commanded_current == 12.0


async def test_resumes_after_disconnect_and_reconnect_while_still_at_the_limit(hass):
    """R7 resume condition 2. Multi-cycle by nature (see test above); each phase below is its
    own Arrange/Act/Assert."""
    config = _config()

    # Arrange (cycle 1): gated at the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Act (cycle 1)
    coord, result = await _run_mode(hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0)

    # Assert (cycle 1)
    assert result.commanded_current == 0.0

    # Arrange (cycle 2): disconnect.
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Act (cycle 2)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 2): every mode's state resets to idle (existing R11 reset path).
    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_SOLAR].phase == Phase.IDLE

    # Arrange (cycle 3): reconnect while still at the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=85.0)

    # Act (cycle 3)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 3): gate still holds, no stuck Hold/Cooldown either.
    assert result.commanded_current == 0.0

    # Arrange (cycle 4): SOC finally drops below the limit.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=70.0)

    # Act (cycle 4)
    coord, result = await _run_mode(
        hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 4): resumes immediately, proving nothing was left latched by the
    # disconnect/reconnect cycle.
    assert result.commanded_current == 12.0


@pytest.mark.parametrize("mode", [MODE_POWER, MODE_OFF])
async def test_power_and_off_ignore_soc_entirely(hass, mode):
    # Arrange: no ev_soc role configured at all -- Power/Off must not regress to needing one.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc_role=False)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = mode
    coord.soc_limit_override = 80.0
    coord.target_current = 10.0
    _seed_ample_peak_headroom(coord)

    # Act
    result = await coord._async_update_data()

    # Assert
    assert result.fault is False
    assert result.commanded_current == (10.0 if mode == MODE_POWER else 0.0)
    # ADR-0012 (coordinator decomposition Task 3.2): MODE_POWER/MODE_OFF have no entry in
    # _fresh_mode_state() and must never gain one -- the ModeHandler registry lookup for these
    # two modes discards its returned state rather than writing it to _mode_state.
    assert mode not in coord._mode_state


async def test_missing_ev_soc_faults_only_while_a_solar_mode_is_selected(hass):
    """Two independent modes exercised in one test since they're the same behavior
    ('does this mode require ev_soc') viewed from each side; each is its own Act/Assert."""
    # Arrange (Solar): ev_soc role unmapped.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc_role=False)

    # Act (Solar)
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert (Solar): faults, since a solar mode requires ev_soc.
    assert result.fault is True
    assert result.commanded_current == 0.0

    # Arrange (Power): same unmapped ev_soc role.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc_role=False)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0

    # Act (Power)
    result = await coord._async_update_data()

    # Assert (Power): no fault, since Power never needs ev_soc.
    assert result.fault is False


async def test_disconnect_with_unavailable_ev_soc_is_a_clean_stop_not_a_fault(hass):
    """A disconnected car is always a clean idle stop (UC01/R7), even when its own SOC
    sensor also goes unavailable on unplug -- ev_soc is only required while the car is
    both connected and a solar mode is active."""
    # Arrange
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0, ev_soc_role=False)

    # Act
    _coord, result = await _run_mode(hass, adapters, _config(), MODE_SOLAR, soc_limit_override=80.0)

    # Assert
    assert result.fault is False
    assert result.commanded_current == 0.0


async def test_mode_switch_resets_the_incoming_modes_state(hass):
    """Multi-cycle by nature (a reset is only observable by comparing state across a
    switch); each phase below is its own Arrange/Act/Assert."""
    config = _config()
    # Hold -> Cooldown transitions on the very next cycle.
    config = dataclasses.replace(config, solar_hold_min=0.0)
    # Long enough that the real test wall-clock never clears it.
    config = dataclasses.replace(config, solar_cooldown_min=5.0)

    ample = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    idle_surplus = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)

    # Act (cycle 1): ample surplus.
    coord, result = await _run_mode(hass, ample, config, MODE_SOLAR, soc_limit_override=80.0)

    # Assert (cycle 1)
    assert result.commanded_current == 12.0  # charging

    # Act (cycle 2): surplus drops below the start threshold.
    coord, result = await _run_mode(
        hass, idle_surplus, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 2)
    assert result.commanded_current == 6.0  # hold, floored at min_a

    # Act (cycle 3): still no surplus, hold_min elapsed (0).
    coord, result = await _run_mode(
        hass, idle_surplus, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycle 3)
    assert result.commanded_current == 0.0  # cooldown
    assert coord._mode_state[MODE_SOLAR].phase == Phase.COOLDOWN

    # Act (cycles 4-5): switch away and back -- both transitions reset _mode_state (R11).
    coord, result = await _run_mode(
        hass, ample, config, MODE_OFF, soc_limit_override=80.0, coord=coord
    )
    coord, result = await _run_mode(
        hass, ample, config, MODE_SOLAR, soc_limit_override=80.0, coord=coord
    )

    # Assert (cycles 4-5)
    assert result.commanded_current == 12.0  # fresh idle -> charges immediately, no cooldown wait


async def test_grid_ceiling_still_clamps_a_solar_request(hass):
    # Arrange: surplus = 2645W = 11.5A ideal; Solar rounds up -> 12A pre-clamp.
    # headroom = floor(0 + 11.5) = 11A -> clamped from 12A to 11A.
    config = _config()
    config = dataclasses.replace(config, grid_ceiling_a=2.0)
    config = dataclasses.replace(config, grid_safety_offset_a=2.0)  # ceiling - offset == 0
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2645.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(hass, adapters, config, MODE_SOLAR, soc_limit_override=80.0)

    # Assert
    assert result.commanded_current == 11.0


async def test_power_mode_behavior_unchanged(hass):
    # Arrange
    adapters = _adapters(status=STATE_CHARGING)

    # Act
    _coord, result = await _run(hass, adapters, _config(), target=10.0)

    # Assert
    assert result.fault is False
    assert result.commanded_current == 10.0
    assert result.active_mode == MODE_POWER


async def test_dispatches_to_captar_when_selected(hass):
    # Arrange: ample R3 headroom (auto-seeded by _run_mode) and ample grid-ceiling headroom.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)

    # Act
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_CAPTAR, soc_limit_override=80.0
    )

    # Assert: Captar always requests max_current -- no downstream clamp reduces it here.
    assert result.fault is False
    assert result.commanded_current == 16.0
    assert result.active_mode == MODE_CAPTAR


async def test_monthly_peak_tracker_updates_every_cycle_regardless_of_mode(hass):
    """R3's bookkeeping is not Captar-specific -- Off/Power update it too. Bypasses the
    ample-headroom test helpers deliberately, to observe the tracker's own cold-start
    behavior (design doc Sec 6.4)."""
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=3400.0, charger_w=0.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_OFF

    result = await coord._async_update_data()

    assert result.monthly_peak_kw == pytest.approx(3.4)


async def test_solar_surplus_w_uses_raw_not_smoothed_net_power(hass):
    """entity-catalog.md:151/glossary -- `charger_power - net_power`, raw, distinct from R10's
    smoothed control-path `surplus_w` (#602 T1)."""
    config = _config()
    config = dataclasses.replace(config, smoothing_window=2)
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=3000.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 10.0
    _seed_ample_peak_headroom(coord)
    await coord._async_update_data()  # cycle 1: window=(1000.0,), smoothed==raw==1000.0

    adapters[ROLE_NET_POWER] = _FakeNumeric(2000.0)  # cycle 2: smoothed(1500) != raw(2000)
    result = await coord._async_update_data()

    assert result.solar_surplus_w == 3000.0 - 2000.0


async def test_solar_surplus_w_defaults_to_zero_on_required_role_fault(hass):
    adapters = _adapters(status=None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.solar_surplus_w == 0.0


async def test_effective_peak_limit_resolves_to_the_lesser_of_tracked_and_max(hass):
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=4.0)
    adapters = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_OFF
    seed_ample_peak_headroom(coord, kw=3.0)  # already-tracked peak is the lesser of the two

    result = await coord._async_update_data()

    assert result.effective_peak_limit_kw == 3.0


async def test_adapter_readings_contains_every_currently_wired_role(hass):
    """entity-catalog.md:154/ADR-0021 -- one key per currently-wired *read* role, excluding
    ROLES_ADAPTER_READINGS_EXCLUDED (#602 T4)."""
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=2000.0, ev_soc=50.0)
    adapters[ROLE_NOTIFICATION_TARGET] = _FakeNumeric("notify.mobile_app")  # write-only role
    _coord, result = await _run(hass, adapters, _config(), target=8.0)
    assert result.adapter_readings[ROLE_CHARGER_STATUS] == STATE_CHARGING
    assert result.adapter_readings[ROLE_NET_POWER] == 1000.0
    assert result.adapter_readings[ROLE_CHARGER_POWER] == 2000.0
    assert result.adapter_readings[ROLE_EV_SOC] == 50.0
    assert result.adapter_readings[ROLE_GRID_VOLTAGE] == 230.0
    assert result.adapter_readings[ROLE_SUN] is None  # sun_state=None default -> read as None
    assert set(result.adapter_readings) == set(adapters) - ROLES_ADAPTER_READINGS_EXCLUDED
    assert ROLE_NOTIFICATION_TARGET not in result.adapter_readings
    assert result.adapter_readings_at is not None


async def test_adapter_readings_caches_deadline_and_reserve_block_reads(hass):
    """ADR-0021/#602 T4's per-role cache must keep mirroring ROLE_DEPARTURE_EXTERNAL/ROLE_SUN/
    ROLE_LOW_TARIFF/ROLE_SOLAR_FORECAST even though their reads live in
    `_resolve_deadline_and_reserve` (ADR-0023, #616) rather than `_read_cycle_inputs` --
    regression test for #621, which found that extraction had silently dropped these four
    `self._role_readings[...]` writes (they still exist, unwritten, on `_run_cycle`'s old
    inline block's git history) while `_read_cycle_inputs`/`_read_deadline_urgency_inputs`'s
    own reads kept caching correctly. A non-None value for each role is asserted so a
    regression back to "cached as None" (indistinguishable from "never cached") would fail
    this test, unlike the vacuous `sun_state=None` default the ROLE_SUN row in
    `test_adapter_readings_contains_every_currently_wired_role` exercises."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0, sun_state=SUN_STATE_ABOVE_HORIZON)
    adapters[ROLE_DEPARTURE_EXTERNAL] = _FakeNumeric(time_of_day(20, 0))
    adapters[ROLE_LOW_TARIFF] = _FakeNumeric(True)
    adapters[ROLE_SOLAR_FORECAST] = _FakeNumeric(15.0)
    _coord, result = await _run(hass, adapters, _config(), target=8.0)

    assert result.adapter_readings[ROLE_DEPARTURE_EXTERNAL] == time_of_day(20, 0)
    assert result.adapter_readings[ROLE_SUN] == SUN_STATE_ABOVE_HORIZON
    assert result.adapter_readings[ROLE_LOW_TARIFF] is True
    assert result.adapter_readings[ROLE_SOLAR_FORECAST] == 15.0


async def test_adapter_readings_caches_a_role_not_read_this_cycle(hass):
    """A role wired but not read on a given cycle (car disconnected -> ev_soc not read this
    time) keeps its last-read value rather than disappearing (ADR-0021's "most recently read
    value") (#602 T4)."""
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 8.0
    _seed_ample_peak_headroom(coord)
    await coord._async_update_data()  # cycle 1: ev_soc read and cached

    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_DISCONNECTED)  # ev_soc no longer read
    result = await coord._async_update_data()

    assert result.adapter_readings[ROLE_EV_SOC] == 50.0  # still the cycle-1 cached value


async def test_adapter_readings_role_never_read_is_none(hass):
    adapters = _adapters(status=STATE_DISCONNECTED, ev_soc_role=True, ev_soc=50.0)
    _coord, result = await _run(hass, adapters, _config(), target=8.0)
    assert result.adapter_readings[ROLE_EV_SOC] is None  # car never connected -> never read


async def test_adapter_readings_role_returning_none_does_not_fault(hass):
    adapters = _adapters(status=STATE_CHARGING, ev_soc_role=True, ev_soc=None)
    _coord, result = await _run(hass, adapters, _config(), target=8.0)
    assert result.fault is False
    assert result.adapter_readings[ROLE_EV_SOC] is None


async def test_adapter_readings_survives_a_faulted_cycle(hass):
    """A cycle that faults on a required role still reports whichever roles were cached
    before the fault, not `{}` -- ADR-0021's "last successful read" (#602 T4)."""
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 8.0
    _seed_ample_peak_headroom(coord)
    await coord._async_update_data()  # cycle 1: healthy, populates the cache

    adapters[ROLE_CHARGER_STATUS] = _FakeNumeric(None)  # cycle 2: required role faults
    result = await coord._async_update_data()

    assert result.fault is True
    assert result.adapter_readings[ROLE_NET_POWER] == 1000.0  # cycle-1 cache survives


async def test_ev_soc_fault_does_not_advance_adapter_readings_at(hass, freezer):
    """Issue #648: the ev_soc-fault early return must NOT advance `_role_readings_at` to this
    cycle's own timestamp, exactly like the required-role fault path a few lines above it
    (coordinator.py's own comment: "the cache keeps whichever timestamp a prior successful
    cycle set"). ADR-0021/entity-catalog.md:154 define
    `sensor.smart_charging_adapter_readings`'s state as the timestamp of the LAST SUCCESSFUL
    cycle -- an ev_soc fault means this cycle wasn't one, so the timestamp must stay at
    cycle 1's value, not jump to cycle 2's, even though cycle 2's required-adapter read (status/
    net_w/charger_w) itself succeeded."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)
    healthy = await coord._async_update_data()  # cycle 1: healthy, records the timestamp
    assert healthy.fault is False
    assert healthy.adapter_readings_at is not None

    freezer.move_to("2026-01-15 12:00:30")  # cycle 2: one interval later
    adapters[ROLE_EV_SOC] = _FakeNumeric(None)  # car still connected, ev_soc goes unavailable
    result = await coord._async_update_data()

    assert result.fault is True
    # Must stay at cycle 1's timestamp, not advance to cycle 2's -- repro: solar mode active,
    # car connected, sensor.ev_soc unavailable -> adapter_readings_at must NOT show a fresh
    # timestamp while status is Fault.
    assert result.adapter_readings_at == healthy.adapter_readings_at


async def test_adapter_readings_at_advances_on_a_second_successful_cycle(hass, freezer):
    """Regression guard for #648's fix: a genuinely successful second cycle must still
    advance `adapter_readings_at` to its own timestamp -- the positive-direction counterpart
    to `test_ev_soc_fault_does_not_advance_adapter_readings_at`, so a future change that moves
    the assignment into a branch that never runs on a healthy cycle would be caught here."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)
    cycle1 = await coord._async_update_data()
    assert cycle1.fault is False

    freezer.move_to("2026-01-15 12:00:30")
    cycle2 = await coord._async_update_data()

    assert cycle2.fault is False
    assert cycle2.adapter_readings_at > cycle1.adapter_readings_at


async def test_time_to_full_min_matches_the_glossary_formula(hass):
    """system-overview.md glossary/entity-catalog.md:152 -- capacity * (limit - soc) / 100,
    projected at this cycle's own commanded (pre-clamp) current (#602 T3)."""
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord, result = await _run(hass, adapters, _config(), target=8.0)
    assert coord.active_mode == MODE_POWER

    # capacity 75 kWh (default), soc 50, limit 80 -> energy_needed = 75*(80-50)/100 = 22.5 kWh
    # minutes = 22500 Wh / (8 A * 230 V) * 60 = 733.695...
    assert result.time_to_full_min == pytest.approx(22.5 * 1000 / (8.0 * 230.0) * 60)
    assert result.commanded_current == 8.0


async def test_time_to_full_min_is_none_when_commanded_current_is_zero(hass):
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    _coord, result = await _run(hass, adapters, _config(), target=0.0)
    assert result.commanded_current == 0.0
    assert result.time_to_full_min is None


async def test_time_to_full_min_is_zero_once_soc_at_or_above_active_limit(hass):
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=80.0)
    _coord, result = await _run(hass, adapters, _config(), target=8.0)
    assert result.time_to_full_min == 0.0


async def test_time_to_full_min_defaults_to_none_on_required_role_fault(hass):
    adapters = _adapters(status=None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.time_to_full_min is None


async def test_time_to_full_min_promoted_capacity_read_does_not_change_deadline_urgency(hass):
    """Regression guard (#602 T3): promoting the ev_battery_capacity read to run
    unconditionally must not change deadline-urgency's own resolved value for a cycle where
    it was already being computed -- mirrors
    test_effective_peak_limit_raises_to_maximum_during_urgency's known-working shape so this
    guard actually exercises the deadline branch, not just `fault is False`."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_MANUAL
    coord.active_mode = MODE_POWER
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord, kw=1.0)

    result = await coord._async_update_data()

    assert result.fault is False
    assert coord._required_current.urgent is True
    assert result.effective_peak_limit_kw == 10.0


async def test_peak_headroom_a_matches_the_r3_clamp_target(hass):
    """entity-catalog.md:153/control-cycle.md step 5 -- same raw-reading headroom the R3
    clamp itself computes (#602 T2)."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=3.56)
    config = dataclasses.replace(config, safety_margin_w=250.0)
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 8.0  # below headroom (10 A) and above CONF_MIN_CURRENT -- no clamp
    _seed_ample_peak_headroom(coord, kw=3.56)

    result = await coord._async_update_data()

    # headroom = floor((3560 - 250 - (1000 - 0)) / 230) = floor(2310 / 230) = 10
    assert result.peak_headroom_a == 10.0
    assert result.commanded_current == 8.0  # not the clamp outcome -- headroom is unclamped


async def test_peak_headroom_a_matches_apply_peak_clamps_own_clamped_outcome(hass):
    """Drift guard: when the mode's request exceeds headroom (and the clamped result still
    clears min_a, so no breach/grace-period logic engages), apply_peak_clamp's own clamped
    output equals its internal headroom_a -- proving the coordinator's duplicated formula
    (#602 T2) hasn't drifted from engines/billing_protection.py's real behavior."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=3.56)
    config = dataclasses.replace(config, safety_margin_w=250.0)
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 16.0  # well above the 10 A headroom -- the clamp engages
    _seed_ample_peak_headroom(coord, kw=3.56)

    result = await coord._async_update_data()

    assert result.commanded_current == 10.0  # apply_peak_clamp's own clamped outcome
    assert result.peak_headroom_a == result.commanded_current


async def test_peak_headroom_a_defaults_to_zero_on_required_role_fault(hass):
    adapters = _adapters(status=None)
    _coord, result = await _run(hass, adapters, _config(), target=10.0)
    assert result.peak_headroom_a == 0.0


async def test_peak_clamp_reduces_captar_below_headroom(hass):
    """A high household baseline load reduces Captar's requested max-current down to the
    available headroom -- a momentary reduction (still above min_a), not a stop."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=3.56)
    config = dataclasses.replace(config, safety_margin_w=250.0)
    # effective_peak_limit(3.56 kW) - margin(250W) - baseline(1000W) = 2310W = 10.04A -> 10A.
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    seed_ample_peak_headroom(coord, kw=3.56)

    result = await coord._async_update_data()

    assert result.commanded_current == 10.0
    assert result.fault is False


async def test_peak_clamp_reduces_solar_below_headroom(hass):
    """R3 now applies to Solar too -- no opt-out (only Power has one, R17). A tight peak
    budget (below the safety margin) reduces Solar's surplus-based request even though
    the surplus itself is ample, proving R3 isn't Captar-only."""
    config = _config()
    # 100 W -- deliberately below the 250 W safety margin.
    config = dataclasses.replace(config, max_peak_kw=0.1)
    config = dataclasses.replace(config, safety_margin_w=250.0)
    # surplus = charger_w(2760) - net_w(0) = 2760 W -> round up -> 12 A ideal.
    # headroom = floor((100 - 250 - (0 - 2760)) / 230) = floor(2610 / 230) = 11 A.
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2760.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    seed_ample_peak_headroom(coord, kw=0.1)

    result = await coord._async_update_data()

    assert result.commanded_current == 11.0
    assert result.fault is False


async def test_set_active_mode_sets_the_field(hass):
    """ADR-0014: set_active_mode is the coordinator's own boundary for active_mode --
    encapsulation, plus (issue #569) a registry-membership guard; a recognized value simply
    passes through."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_active_mode(MODE_SOLAR)
    assert coord.active_mode == MODE_SOLAR


async def test_set_active_mode_falls_back_to_off_on_unrecognized_value(hass, caplog):
    """Issue #569: an unexpected stored `active_mode` value (e.g. a stale/corrupted restored
    option) must not silently become the coordinator's own field only to KeyError later at
    `self._mode_handlers[self.active_mode]` inside the cycle (issue #561's fault-loop risk).
    set_active_mode must reject anything outside `self._mode_handlers`' own keys, falling back
    to MODE_OFF and logging a WARNING -- the same fail-safe outcome as the fault path
    (ADR-0007), reached explicitly here instead of via a raised KeyError."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        coord.set_active_mode("not_a_real_mode")

    assert coord.active_mode == MODE_OFF
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == coordinator_module.__name__
    ]
    assert len(warnings) == 1
    assert "not_a_real_mode" in warnings[0].getMessage()


async def test_set_active_mode_warns_once_per_rejected_value_not_per_call(hass, caplog):
    """ADR-0007's once-per-outage discipline applies here too (mirroring `_log_fault`): a
    Store-read corrupted mode value is re-read and re-rejected every cycle, so warning on every
    call would spam the log once per control interval forever. Re-rejecting the SAME bad value
    logs once; a DIFFERENT bad value (or recovery to a valid mode, then a new bad value) logs
    again -- the latch tracks the specific rejected value, not just "currently rejecting"."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        coord.set_active_mode("bad_one")
        coord.set_active_mode("bad_one")
        coord.set_active_mode("bad_one")
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "same rejected value repeated must warn only once"

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        coord.set_active_mode("bad_two")  # a different bad value -> warns again
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "a newly-different rejected value must warn again"

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        coord.set_active_mode(MODE_SOLAR)  # recovers
        coord.set_active_mode("bad_one")  # same raw value as before, but after a recovery
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "recovering then re-rejecting the same value must warn again"


async def test_read_owned_entities_falls_back_to_off_on_unrecognized_stored_mode(hass, caplog):
    """Same fallback, driven through the real call path (_read_owned_entities, ADR-0018) rather
    than calling set_active_mode directly -- confirms an unrecognized value read back from the
    Store can't reach `self._mode_handlers[self.active_mode]` and KeyError the whole cycle, and
    that a full cycle completes cleanly (no fault, 0 A) rather than raising."""
    store = _FakeStore({(Platform.SELECT, OWNED_SUFFIX_MODE): "not_a_real_mode"})
    adapters = _adapters()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, store=store, config=_config(), interval_s=30
    )
    _seed_ample_peak_headroom(coord)

    with caplog.at_level(logging.WARNING, logger=coordinator_module.__name__):
        result = await coord._async_update_data()

    assert coord.active_mode == MODE_OFF
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name == coordinator_module.__name__
    ]
    assert len(warnings) == 1
    assert "not_a_real_mode" in warnings[0].getMessage()
    # The whole cycle must complete cleanly -- MODE_OFF dispatches to 0 A, no fault -- not
    # raise KeyError and fall through to the generic cycle-exception fault path (issue #569).
    assert result.fault is False
    assert result.commanded_current == 0.0


async def test_sustained_peak_breach_at_minimum_stops_captar_and_starts_cooldown(hass):
    """Grace period 0 -- the very first breaching cycle already exceeds it -- forces 0 A
    and CaptarState -> cooldown; the cooldown then blocks a restart until it elapses (R11)."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=1.0)
    config = dataclasses.replace(config, safety_margin_w=250.0)
    config = dataclasses.replace(config, peak_grace_min=0.0)
    config = dataclasses.replace(config, captar_cooldown_min=5.0)
    # effective_peak_limit(1.0 kW) - margin(250W) - baseline(600W) = 150W = 0.65A -> 0A < min_a.
    breaching = _adapters(status=STATE_CHARGING, net_w=600.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=breaching, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    seed_ample_peak_headroom(coord, kw=1.0)

    result = await coord._async_update_data()

    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # A second cycle, even with ample headroom restored, stays blocked until the
    # cooldown (5 minutes) elapses -- essentially no wall-clock time has passed.
    ample = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord._adapters = ample
    result = await coord._async_update_data()

    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN


async def test_captar_cooldown_resets_on_mode_switch(hass):
    """Switching away from Captar and back clears its cooldown state (R11)."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=1.0)
    config = dataclasses.replace(config, peak_grace_min=0.0)
    breaching = _adapters(status=STATE_CHARGING, net_w=600.0, charger_w=0.0, ev_soc=50.0)
    coord = SmartChargingCoordinator(
        hass, adapters=breaching, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    seed_ample_peak_headroom(coord, kw=1.0)
    await coord._async_update_data()
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # Switch away and back -- both transitions reset _mode_state (R11), same as Solar's.
    # Also restore ample peak headroom so only the cooldown reset is under test here.
    ample = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord._adapters = ample
    coord._config = dataclasses.replace(config, max_peak_kw=AMPLE_PEAK_HEADROOM_KW)
    coord._peak_demand.tracked_kw = AMPLE_PEAK_HEADROOM_KW
    coord.active_mode = MODE_OFF
    await coord._async_update_data()
    coord.active_mode = MODE_CAPTAR
    result = await coord._async_update_data()

    assert result.commanded_current == 16.0  # fresh idle -> charges immediately, no cooldown wait
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_captar_resets_on_disconnect(hass):
    """A disconnect resets Captar's state to idle() -- not a cooldown -- per UC03's state model."""
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    _coord, result = await _run_mode(
        hass, adapters, _config(), MODE_CAPTAR, soc_limit_override=80.0
    )
    assert result.commanded_current == 16.0  # confirm it was charging first

    disconnected = _adapters(status=STATE_DISCONNECTED, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    coord, result = await _run_mode(
        hass, disconnected, _config(), MODE_CAPTAR, soc_limit_override=80.0, coord=_coord
    )

    assert result.commanded_current == 0.0
    assert coord._mode_state[MODE_CAPTAR].phase == Phase.IDLE


async def test_power_respects_peak_by_default(hass):
    """Power's own target(16A) would normally be commanded outright (existing MVP
    behavior); with power_respect_peak left at its default (True), R17 now ALSO
    bounds it by the R3 clamp -- a deliberate behavior change (design doc Sec 7)."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=3.56)
    # Same headroom math as test_peak_clamp_reduces_captar_below_headroom: 10A available.
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 16.0
    seed_ample_peak_headroom(coord, kw=3.56)

    result = await coord._async_update_data()

    assert result.commanded_current == 10.0


async def test_power_can_opt_out_of_peak_protection(hass):
    """sc_power_respect_peak=False skips the R3 clamp (E5), but the C4 grid-ceiling
    clamp (E6) still applies -- distinct call sites (ADR-0006)."""
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=3.56)
    config = dataclasses.replace(config, power_respect_peak=False)
    adapters = _adapters(status=STATE_CHARGING, net_w=1000.0, charger_w=0.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 16.0
    seed_ample_peak_headroom(coord, kw=3.56)

    result = await coord._async_update_data()

    # R3 skipped entirely -- E6's grid-ceiling headroom (18A) is the only bound left.
    assert result.commanded_current == 16.0


async def test_grid_ceiling_still_clamps_a_captar_request(hass):
    """E6 (unchanged) still reduces a Captar-mode request that would breach the ceiling,
    even with ample R3 headroom (auto-seeded by _run_mode)."""
    config = _config()
    config = dataclasses.replace(config, grid_ceiling_a=2.0)
    config = dataclasses.replace(config, grid_safety_offset_a=2.0)  # ceiling - offset == 0
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=2645.0, ev_soc=50.0)

    _coord, result = await _run_mode(hass, adapters, config, MODE_CAPTAR, soc_limit_override=80.0)

    assert result.commanded_current == 11.0


# --- Task 5.1: full active-SOC-limit resolution + ActiveSocLimitChanged (R7/R8/R9) ---


async def test_active_soc_limit_resolves_via_the_three_row_table(hass):
    """With a solar step-up already in effect, active_soc_limit reflects the stepped
    value, not the raw soc_limit_override (E3 row 2)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_gate.state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_soc_limit == 85.0


async def test_solar_step_up_applies_a_fresh_step_when_soc_nears_the_current_limit(hass):
    """No step-up in effect yet: SOC within step_threshold_pp of soc_limit_override triggers
    a fresh step, proving the coordinator wires ev_soc (not some other value) into
    resolve_solar_step_up's soc parameter (R8/UC06 main success)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=79.0)
    config = _config()  # step_threshold_pp=2.0, step_pp=5.0
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_soc_limit == 85.0
    assert coord._step_up_gate.state.stepped_pct == 85.0


async def test_solar_step_up_clears_on_mode_switch_away_from_solar(hass):
    """Switching from Solar to Power resets self._step_up_gate.state (UC06 exception flow)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_gate.state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    coord.active_mode = MODE_POWER
    await coord._async_update_data()

    assert coord._step_up_gate.state == SolarStepUpState()


async def test_solar_step_up_clears_on_disconnect(hass):
    """A disconnect clears the step-up state even while Solar is still selected (UC06)."""
    adapters = _adapters(status=STATE_DISCONNECTED, ev_soc_role=False)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_gate.state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._step_up_gate.state == SolarStepUpState()


async def test_solar_step_up_survives_solar_to_solaronly_switch(hass):
    """R7/UC06 alternate flow 4a: a Solar<->SolarOnly switch preserves an in-effect
    step-up -- only the generic per-mode-switch reset is scoped to _mode_state, not this."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    coord._step_up_gate.state = SolarStepUpState(stepped_pct=85.0)
    _seed_ample_peak_headroom(coord)

    coord.active_mode = MODE_SOLAR_ONLY
    await coord._async_update_data()

    assert coord._step_up_gate.state == SolarStepUpState(stepped_pct=85.0)


async def test_active_soc_limit_changed_event_fires_on_change(hass):
    """ADR-0011: ActiveSocLimitChanged fires only when the resolved value differs from
    the prior cycle's, not on every cycle."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)

    events = []

    @callback
    def _record(event):
        # A plain (non-@callback) listener is dispatched as an executor job -- appending
        # from a worker thread races the assertions below. @callback keeps it synchronous.
        events.append(event)

    hass.bus.async_listen(EVENT_ACTIVE_SOC_LIMIT_CHANGED, _record)

    await coord._async_update_data()  # first resolution: 80.0, no prior value -> fires
    assert len(events) == 1
    assert events[0].data[ATTR_ACTIVE_SOC_LIMIT] == 80.0

    await coord._async_update_data()  # unchanged -> no second event
    assert len(events) == 1

    coord.soc_limit_override = 90.0
    await coord._async_update_data()  # changed -> fires again
    assert len(events) == 2
    assert events[1].data[ATTR_ACTIVE_SOC_LIMIT] == 90.0


# --- Task 5.2: deadline resolution, required-current/urgency, baseline-mode comparison ---


async def test_urgency_engages_when_required_current_exceeds_baseline(hass, freezer):
    """Manual profile: baseline is simply the manually selected mode's own desired current
    (Power's target_current here) -- a required current above it is urgent (R5)."""
    freezer.move_to("2026-01-15 12:00:00")  # fixed, away from midnight (no rollover semantics)
    adapters = _adapters(status=STATE_CHARGING, ev_soc=79.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 2.0  # well below the ~3.26 A the deadline below will require
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is True
    assert coord._required_current.unreachable is False


async def test_urgency_reverts_when_baseline_alone_would_meet_the_deadline(hass, freezer):
    """Same deadline as above, but Power's own target current already exceeds what's
    required -- urgency never engages (R16's revert case)."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=79.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 5.0  # above the ~3.26 A the deadline below requires
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is False


async def test_baseline_comparison_uses_rows_3_5_not_the_escalated_mode(hass, freezer):
    """Regression per resolution-rules.md's own warning: comparing against Captar's own
    (already-maximum) desired current would make urgency look satisfied instantly and
    revert every cycle -- this test drives that exact scenario and asserts urgency holds."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=78.0, sun_state=SUN_STATE_ABOVE_HORIZON)
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=DEFAULT_CAPTAR_AVAILABLE)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_CAPTAR  # already escalated from a prior cycle
    coord.soc_limit_override = 80.0
    # No solar capability and sun up -> Auto's own baseline (rows 3-5, urgent=False) falls
    # through to Off, not Captar -- the required current below (~3.26 A) only exceeds a
    # baseline of 0 A, never Captar's own (already-maximum, 16 A) desired current.
    _seed_today_deadline(coord, hours_from_now=2)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is True


async def test_tomorrow_deadline_resolved_disables_solar_reserve(hass):
    """The one-day-ahead deadline resolution feeds resolve_solar_reserve_active (R9's
    mutual-exclusivity clause)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0, sun_state=SUN_STATE_BELOW_HORIZON)
    adapters[ROLE_SOLAR_FORECAST] = _FakeNumeric(20.0)  # above the 12 kWh default threshold
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    coord.home_day_flag = True
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()
    assert result.active_soc_limit == 60.0  # DEFAULT_SOLAR_RESERVE_SOC -- reserve engaged

    # R14 row 3 (home_day_flag already True above) wins over the day-of-week default, so the
    # home-day override -- not departure_dow_defaults -- is what must resolve for the
    # one-day-ahead evaluation to stop returning "no deadline".
    coord.departure_home_day_override = dt_util.now().time()
    result = await coord._async_update_data()
    assert result.active_soc_limit == 80.0  # tomorrow deadline resolved -> reserve lifted


async def test_ev_battery_capacity_prefers_the_sensed_role_over_the_configured_value(hass, freezer):
    """R15: with `ev_battery_capacity` role mapped and reading 60.0 kWh, the required-current
    computation uses 60.0, not CONF_EV_BATTERY_CAPACITY_KWH's configured default."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    adapters[ROLE_EV_BATTERY_CAPACITY] = _FakeNumeric(60.0)
    config = _config()
    config = dataclasses.replace(config, ev_battery_capacity_kwh=75.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    expected_required_a = (60.0 * 30 / 100 * 1000) / 3 / 230.0
    assert coord._required_current.required_a == pytest.approx(expected_required_a)


async def test_ev_battery_capacity_falls_back_to_configured_when_sensor_unavailable(hass, freezer):
    """R15: with the role mapped but currently reading None, the required-current
    computation falls back to CONF_EV_BATTERY_CAPACITY_KWH."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    adapters[ROLE_EV_BATTERY_CAPACITY] = _FakeNumeric(None)
    config = _config()
    config = dataclasses.replace(config, ev_battery_capacity_kwh=75.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    expected_required_a = (75.0 * 30 / 100 * 1000) / 3 / 230.0
    assert coord._required_current.required_a == pytest.approx(expected_required_a)


async def test_deadline_unreachable_notified_fires_while_required_current_exceeds_max_rate(
    hass, freezer
):
    """R5/ADR-0011: DeadlineUnreachableNotified is published every cycle
    resolve_required_current's `unreachable` flag is True -- including re-firing on a
    later cycle that is still Unreachable, not only on the Normal/Urgent -> Unreachable
    transition edge (UC05's domain-events section)."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    config = _config()  # CONF_MAX_CURRENT=16.0
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)  # tight deadline -> required current >> 16 A
    _seed_ample_peak_headroom(coord)

    events = []

    @callback
    def _record(event):
        # A plain (non-@callback) listener is dispatched as an executor job -- appending
        # from a worker thread races the assertions below. @callback keeps it synchronous.
        events.append(event)

    hass.bus.async_listen(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, _record)

    await coord._async_update_data()
    assert len(events) == 1
    assert coord._required_current.unreachable is True
    assert events[0].data[ATTR_REQUIRED_CURRENT_A] == pytest.approx(
        coord._required_current.required_a
    )

    await coord._async_update_data()  # still Unreachable -- fires again, not just on the edge
    assert len(events) == 2


async def test_deadline_unreachable_notified_caps_saturated_required_a_at_max_current(
    hass, freezer
):
    """Issue #650: engines/deadline.py deliberately saturates `required_a` to
    `float('inf')` once a same-day deadline has already passed (its own documented
    design-doc-Sec6 behavior, left unchanged here). But `float('inf')` must never reach
    the `DeadlineUnreachableNotified` payload -- it doesn't round-trip through HA's JSON
    websocket encoding, and notification_manager.py formats it directly into user-facing
    text ('would need inf A'). The boundary cap belongs here, in the coordinator, at the
    point the engine's pure output crosses into the published event payload -- not inside
    the engine itself."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    config = _config()  # CONF_MAX_CURRENT=16.0
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=-1)  # deadline already passed -> engine saturates
    _seed_ample_peak_headroom(coord)

    events = []

    @callback
    def _record(event):
        events.append(event)

    hass.bus.async_listen(EVENT_DEADLINE_UNREACHABLE_NOTIFIED, _record)

    await coord._async_update_data()

    # The engine's own result is untouched (still saturates to inf, per its documented
    # contract) -- only the published payload is capped.
    assert coord._required_current.required_a == float("inf")
    assert len(events) == 1
    assert events[0].data[ATTR_REQUIRED_CURRENT_A] == pytest.approx(config.max_current)
    assert events[0].data[ATTR_REQUIRED_CURRENT_A] != float("inf")


def _listen_cleared(hass):
    events = []

    @callback
    def _record(event):
        # A plain (non-@callback) listener is dispatched as an executor job -- appending
        # from a worker thread races the assertions below. @callback keeps it synchronous.
        events.append(event)

    hass.bus.async_listen(EVENT_DEADLINE_UNREACHABLE_CLEARED, _record)
    return events


async def test_deadline_unreachable_cleared_fires_when_required_current_falls_back(hass, freezer):
    """ADR-0024 exit row 1: a tight deadline makes `unreachable` True (cycle 1, no clear), then
    the deadline is pushed out so `resolve_required_current` returns within the maximum
    permitted rate -- cycle 2 fires EVENT_DEADLINE_UNREACHABLE_CLEARED exactly once, on the
    same hass.bus, and cycle 3 (still reachable) fires nothing more."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    config = _config()  # CONF_MAX_CURRENT=16.0
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)  # tight deadline -> required current >> 16 A
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, no clear yet
    assert coord._required_current.unreachable is True
    assert len(events) == 0

    # cycle 2: same day, plenty of time, and the state of charge has caught up -> reachable
    adapters[ROLE_EV_SOC] = _FakeNumeric(70.0)
    _seed_today_deadline(coord, hours_from_now=3)
    await coord._async_update_data()
    assert coord._required_current.unreachable is False
    assert len(events) == 1

    await coord._async_update_data()  # cycle 3: still reachable -> no further clear
    assert len(events) == 1


async def test_deadline_unreachable_cleared_fires_on_disconnect(hass, freezer):
    """ADR-0024 exit row 2: the car disconnects, so `deadline_resolvable` goes False and
    resolve_deadline_urgency returns its early RequiredCurrentResult(unreachable=False)
    without calling the engine at all -- the clear still fires, because the detector reads
    `RequiredCurrentResult.unreachable` itself, not any one guard."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, no clear yet
    assert coord._required_current.unreachable is True
    assert len(events) == 0

    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_DISCONNECTED)  # cycle 2: disconnect
    await coord._async_update_data()
    assert coord._required_current.unreachable is False
    assert len(events) == 1


async def test_deadline_unreachable_cleared_fires_when_the_deadline_capability_is_withdrawn(
    hass, freezer
):
    """ADR-0024 exit row 3 (R18): `deadline_resolvable` stays True (car connected, ev_soc
    readable) but every R14 row resolves to no deadline, so `deadline_today` is None and
    resolve_required_current's own `if deadline is None` guard yields unreachable=False. A
    different mechanism from the disconnect above, deliberately covered separately."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, no clear yet
    assert coord._required_current.unreachable is True
    assert len(events) == 0

    # cycle 2: every R14 row now resolves to "no deadline" (capability withdrawn, R18) --
    # car is still connected and ev_soc still reads fine, so this is NOT a disconnect.
    coord.departure_dow_defaults[dt_util.now().weekday()] = None
    await coord._async_update_data()
    assert coord._required_current.unreachable is False
    assert len(events) == 1


async def test_required_adapter_fault_fires_no_clear_on_the_fault_cycle(hass, freezer):
    """ADR-0024's fault-cycle-hold rule, path 1 (the *negative* half): with `unreachable`
    True on cycle 1, a cycle whose required-adapter read returns None returns early (before
    the deadline-urgency block runs), so no clear is fired on that cycle -- and a subsequent
    healthy cycle that is STILL unreachable fires no clear either. Same 'a fault cycle is not
    a successful cycle' rule `adapter_readings_at` already follows on this exact return
    (#648). NOTE: this assertion set alone does NOT pin the hold -- see the discriminating
    test below."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, edge armed
    assert coord._required_current.unreachable is True

    adapters[ROLE_CHARGER_STATUS] = _FakeNumeric(None)  # cycle 2: required-adapter fault
    fault_result = await coord._async_update_data()
    assert fault_result.fault is True
    assert len(events) == 0

    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_CHARGING)  # cycle 3: healthy, still tight
    healthy_result = await coord._async_update_data()
    assert healthy_result.fault is False
    assert coord._required_current.unreachable is True
    assert len(events) == 0


async def test_required_adapter_fault_holds_the_flag_so_a_later_genuine_resolve_still_clears(
    hass, freezer
):
    """ADR-0024's fault-cycle-hold rule, path 1 (the *discriminating* half -- the test that
    actually distinguishes HOLD from RESET, and the reason this task exists at all):

      cycle 1: tight deadline -> unreachable True, no clear (the edge is now armed)
      cycle 2: required-adapter read returns None -> fault early-return, no clear
      cycle 3: healthy again AND the deadline genuinely resolves (unreachable False)
               -> EVENT_DEADLINE_UNREACHABLE_CLEARED MUST fire exactly once

    Under the correct HOLD behavior the detector's prior-cycle flag survived cycle 2
    untouched, so cycle 3 is a genuine True->False edge and the clear fires. Under a broken
    `self._unreachable_edge.reset()`-on-fault implementation the flag would be False entering
    cycle 3, no edge would be seen, and the clear would NEVER fire -- leaving M3's
    `_deadline_unreachable_notified` latch armed forever and silently suppressing the next
    occasion's R5 notice. That is exactly the silent failure ADR-0024 exists to prevent, and
    the two negative-only assertions above would pass against that broken implementation, so
    this test is the one that pins the rule."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_POWER
    coord.target_current = 0.0
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, edge armed
    assert coord._required_current.unreachable is True

    adapters[ROLE_CHARGER_STATUS] = _FakeNumeric(None)  # cycle 2: required-adapter fault
    fault_result = await coord._async_update_data()
    assert fault_result.fault is True
    assert len(events) == 0

    adapters[ROLE_CHARGER_STATUS] = _FakeStatus(STATE_CHARGING)  # cycle 3: healthy again
    adapters[ROLE_EV_SOC] = _FakeNumeric(70.0)  # ...state of charge has caught up...
    _seed_today_deadline(coord, hours_from_now=3)  # ...and the deadline genuinely resolves
    await coord._async_update_data()
    assert coord._required_current.unreachable is False
    assert len(events) == 1


async def test_ev_soc_fault_fires_no_clear_on_the_fault_cycle(hass, freezer):
    """ADR-0024's fault-cycle-hold rule, path 2: same negative assertions against the *other*
    early return -- a solar mode selected, car connected, ev_soc reading None. Resetting the
    flag here would emit a spurious clear on a cycle that established nothing about the
    deadline and then re-notify the driver on the next healthy cycle."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, edge armed
    assert coord._required_current.unreachable is True

    adapters[ROLE_EV_SOC] = _FakeNumeric(None)  # cycle 2: car connected, ev_soc unavailable
    fault_result = await coord._async_update_data()
    assert fault_result.fault is True
    assert len(events) == 0

    adapters[ROLE_EV_SOC] = _FakeNumeric(10.0)  # cycle 3: healthy again, still tight deadline
    healthy_result = await coord._async_update_data()
    assert healthy_result.fault is False
    assert coord._required_current.unreachable is True
    assert len(events) == 0


async def test_ev_soc_fault_holds_the_flag_so_a_later_genuine_resolve_still_clears(hass, freezer):
    """ADR-0024's fault-cycle-hold rule, path 2 discriminating half: the same
    unreachable -> fault -> genuine-resolve sequence as the required-adapter version above,
    driven through the ev_soc early return instead. Both early returns are separate code
    paths, so each gets its own discriminating test -- a future refactor could plausibly add
    a reset to one and not the other."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0, ev_soc=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=0.5)
    _seed_ample_peak_headroom(coord)
    events = _listen_cleared(hass)

    await coord._async_update_data()  # cycle 1: unreachable, edge armed
    assert coord._required_current.unreachable is True

    adapters[ROLE_EV_SOC] = _FakeNumeric(None)  # cycle 2: ev_soc fault
    fault_result = await coord._async_update_data()
    assert fault_result.fault is True
    assert len(events) == 0

    adapters[ROLE_EV_SOC] = _FakeNumeric(70.0)  # cycle 3: healthy again, state of charge caught up
    _seed_today_deadline(coord, hours_from_now=3)  # ...and the deadline genuinely resolves
    await coord._async_update_data()
    assert coord._required_current.unreachable is False
    assert len(events) == 1


# --- ROLE_LOW_TARIFF (issue #376): Auto row 4's low-tariff input ---


async def test_low_tariff_defaults_active_when_role_unmapped(hass, freezer):
    """Glossary's own single-tariff default: with ROLE_LOW_TARIFF unmapped, row 4 behaves
    as though low_tariff_active is always True -- baseline selects Captar (16 A, exceeds
    the ~10.87 A the deadline below requires), so urgency never engages."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0, sun_state=SUN_STATE_BELOW_HORIZON)
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=DEFAULT_CAPTAR_AVAILABLE)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is False


async def test_low_tariff_inactive_withholds_baseline_row4(hass, freezer):
    """With ROLE_LOW_TARIFF mapped and reading False, row 4 never matches -- baseline
    falls through to Off (0 A), so the same deadline as above now reads urgent."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(
        status=STATE_CHARGING, ev_soc=70.0, sun_state=SUN_STATE_BELOW_HORIZON, low_tariff=False
    )
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=DEFAULT_CAPTAR_AVAILABLE)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is True


async def test_low_tariff_mapped_true_matches_default(hass, freezer):
    """A mapped ROLE_LOW_TARIFF reading True behaves the same as the unmapped default."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(
        status=STATE_CHARGING, ev_soc=70.0, sun_state=SUN_STATE_BELOW_HORIZON, low_tariff=True
    )
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=DEFAULT_CAPTAR_AVAILABLE)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=3)
    _seed_ample_peak_headroom(coord)

    await coord._async_update_data()

    assert coord._required_current.urgent is False


# --- Task 5.3: Auto mode-selection dispatch, Capability-Gate, peak-limit row-1 raise ---


async def test_auto_profile_selects_solar_when_surplus_sufficient(hass):
    """Row 3: solar capability present, sun up, surplus above threshold -> Solar, no
    urgency in the way (no deadline seeded)."""
    adapters = _adapters(
        status=STATE_CHARGING,
        ev_soc=50.0,
        net_w=100.0,
        charger_w=500.0,
        sun_state=SUN_STATE_ABOVE_HORIZON,
    )
    config = _config()
    config = dataclasses.replace(config, solar_available=True)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_mode == MODE_SOLAR


async def test_auto_profile_escalates_to_captar_under_urgency(hass, freezer):
    """Row 2: a tight deadline the baseline (Off, no solar/low-tariff match) can't meet
    escalates Auto to Captar, the available urgency-capable mode."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=True)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_mode == MODE_CAPTAR


async def test_auto_escalation_resets_captar_state_the_same_cycle(hass, freezer):
    """Regression: the mode-switch reset (R11) must fire the SAME cycle Auto escalates into
    Captar, not one cycle late -- otherwise a stale leftover CaptarState (e.g. cooldown from
    a much earlier session) would block this cycle's dispatch at 0 A instead of the fresh
    max-current request a just-arrived escalation should get."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=True)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_SOLAR  # this cycle escalates away from Solar, not already Captar
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)
    # Leftover Captar cooldown state from long before this test's own dispatch -- if the reset
    # doesn't fire this same cycle, Captar's step() sees this and returns 0 A (still cooling
    # down) instead of max_a.
    coord._mode_state[MODE_CAPTAR] = CaptarState(Phase.COOLDOWN, hass.loop.time())
    coord._last_active_mode = MODE_SOLAR

    _seed_today_deadline(coord, hours_from_now=1)
    result = await coord._async_update_data()

    assert result.active_mode == MODE_CAPTAR
    assert result.commanded_current == 16.0  # CONF_MAX_CURRENT -- fresh idle state, not cooldown


async def test_auto_profile_falls_back_to_power_when_captar_unavailable_under_urgency(
    hass, freezer
):
    """R16/R18's carve-out: the same urgency as above, but with Captar unavailable, Auto
    selects Power instead of falling through to Off."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    config = dataclasses.replace(config, solar_available=False)
    config = dataclasses.replace(config, captar_available=False)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_AUTO
    coord.active_mode = MODE_OFF
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_mode == MODE_POWER


async def test_manual_profile_never_changes_mode_regardless_of_urgency(hass, freezer):
    """NF2 regression: active_mode stays whatever the user selected even while urgent."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_MANUAL
    coord.active_mode = MODE_SOLAR
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)  # would be urgent, if Auto
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert coord._required_current.urgent is True
    assert result.active_mode == MODE_SOLAR


async def test_manual_profile_solar_only_baseline_dry_run(hass, freezer):
    """Same shape as test_manual_profile_never_changes_mode_regardless_of_urgency, for
    MODE_SOLAR_ONLY specifically -- the one mode the ModeHandler-registry unification
    (ADR-0012 T3.3) had no existing dry-run coverage for, since every other baseline-mode
    deadline test above exercises Off/Power/Solar/Captar but never SolarOnly."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_MANUAL
    coord.active_mode = MODE_SOLAR_ONLY
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)  # would be urgent, if Auto
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert coord._required_current.urgent is True
    assert result.active_mode == MODE_SOLAR_ONLY


async def test_effective_peak_limit_raises_to_maximum_during_urgency(hass, freezer):
    """R5/C3 row 1: urgency raises the effective peak limit to max_peak_kw, above the
    monthly-tracked peak it would otherwise be capped to."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_MANUAL
    coord.active_mode = MODE_POWER
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord, kw=1.0)  # well below max_peak_kw -- row 2 alone would apply

    result = await coord._async_update_data()

    assert coord._required_current.urgent is True
    assert result.effective_peak_limit_kw == 10.0


async def test_effective_peak_limit_resolves_normally_once_urgency_reverts(hass, freezer):
    """Once the SOC reaches the active limit (nothing left to charge, no urgency), the
    effective peak limit reverts to row 2's min(monthly, max)."""
    freezer.move_to("2026-01-15 12:00:00")
    adapters = _adapters(status=STATE_CHARGING, ev_soc=70.0)
    config = _config()
    config = dataclasses.replace(config, max_peak_kw=10.0)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_MANUAL
    coord.active_mode = MODE_POWER
    coord.soc_limit_override = 80.0
    _seed_today_deadline(coord, hours_from_now=1)
    _seed_ample_peak_headroom(coord, kw=1.0)

    result = await coord._async_update_data()
    assert result.effective_peak_limit_kw == 10.0  # urgent -- raised

    adapters[ROLE_EV_SOC]._value = 80.0  # SOC now at the limit -- nothing left to charge
    result = await coord._async_update_data()
    assert coord._required_current.urgent is False
    assert result.effective_peak_limit_kw == 1.0  # reverted -- min(monthly, max)


async def test_manual_selector_unaffected_by_available_modes_gate_already_true_today(hass):
    """Regression: existing ModeSelect option-gating behavior (R18) is untouched by the
    new resolve_available_modes call this task adds for Auto's own use -- Manual dispatches
    to Captar directly even with the Captar capability unavailable (config alone doesn't
    gate Manual's own dispatch; select.py's own option list is what does, unaffected here)."""
    adapters = _adapters(status=STATE_CHARGING, ev_soc=50.0)
    config = _config()
    config = dataclasses.replace(config, captar_available=False)
    coord = SmartChargingCoordinator(
        hass, adapters=adapters, config=config, interval_s=30, store=_FakeStore({})
    )
    coord.active_profile = PROFILE_MANUAL
    coord.active_mode = MODE_CAPTAR
    coord.soc_limit_override = 80.0
    _seed_ample_peak_headroom(coord)

    result = await coord._async_update_data()

    assert result.active_mode == MODE_CAPTAR
    assert result.commanded_current == 16.0  # CONF_MAX_CURRENT -- Captar's own step ran normally


async def test_set_soc_limit_override_clamps_below_minimum(hass):
    """ADR-0014: the coordinator's own clamp, using the new named SOC_LIMIT_OVERRIDE_MIN/MAX
    constants shared with SocLimitOverrideNumber's own bounds."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_soc_limit_override(10.0)
    assert coord.soc_limit_override == SOC_LIMIT_OVERRIDE_MIN


async def test_set_soc_limit_override_clamps_above_maximum(hass):
    """ADR-0014: same clamp, upper bound."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_soc_limit_override(150.0)
    assert coord.soc_limit_override == SOC_LIMIT_OVERRIDE_MAX


async def test_set_soc_limit_override_passes_through_in_range_value(hass):
    """ADR-0014: an in-range value reaches the field unchanged -- the clamp only rejects
    out-of-range input, it doesn't substitute a fixed value for everything."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_soc_limit_override(80.0)
    assert coord.soc_limit_override == 80.0


async def test_set_target_current_clamps_below_minimum(hass):
    """ADR-0014: the coordinator's own clamp -- reachable by any caller, not just
    TargetCurrentNumber's own native_min_value/native_max_value."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_target_current(0.0)  # _config()'s CONF_MIN_CURRENT is 6.0
    assert coord.target_current == 6.0


async def test_set_target_current_clamps_above_maximum(hass):
    """ADR-0014: the same clamp, exercised on the above-maximum side."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_target_current(99.0)  # _config()'s CONF_MAX_CURRENT is 16.0
    assert coord.target_current == 16.0


async def test_set_target_current_passes_through_in_range_value(hass):
    """ADR-0014: an in-range value is left untouched -- the clamp only ever narrows toward
    the configured bound, never perturbs a value already inside it."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.set_target_current(10.0)
    assert coord.target_current == 10.0


async def test_seed_monthly_peak_sets_tracked_kw_and_month(hass):
    """ADR-0012: the coordinator's own boundary for seeding `_peak_demand` from
    MonthlyPeakSensor's restored state -- the intended write path for sensor.py, replacing
    its direct reach into `_peak_demand`'s private fields (#496)."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.seed_monthly_peak(3.4, (2026, 7))
    assert coord._peak_demand.tracked_kw == 3.4
    assert coord._peak_demand.tracked_month == (2026, 7)


async def test_seed_monthly_peak_leaves_month_unchanged_when_none(hass):
    """A restore with no `period_month` attribute (older stored state) seeds only the kW
    value, matching sensor.py's own restore-path branching."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord._peak_demand.tracked_month = (2026, 6)
    coord.seed_monthly_peak(3.4, None)
    assert coord._peak_demand.tracked_kw == 3.4
    assert coord._peak_demand.tracked_month == (2026, 6)


async def test_seed_monthly_peak_passes_a_negative_kw_through_unchanged(hass):
    """A faithful restore, not a clamp -- `PeakDemandState.update()` can itself produce a
    negative `tracked_kw` on a net-export month (peak_demand_tracker.py's own contract), so
    the seed path must not silently floor a legitimately-negative restored value to zero."""
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), config=_config(), interval_s=30, store=_FakeStore({})
    )
    coord.seed_monthly_peak(-1.0, (2026, 7))
    assert coord._peak_demand.tracked_kw == -1.0


# --- Task 4.1 (ADR-0012 coordinator decomposition): explicit ADR-0006 clamp-integrity check,
# made permanent regression tests rather than a one-time manual read (plan Step 4). ---
#
# OPEN QUESTION FOR REVIEWER (T4.1's own Step 3 dead-code sweep): `_mode_desired_current` in
# coordinator.py still carries its own pre-Task-3.3 if/elif dispatch chain (calling
# solar.step/solar_only.step/captar.step/power.desired_current directly against
# self._mode_state), rather than the unified `self._mode_handlers[mode].desired_current(ctx,
# ...)` form Task 3.3 specifies -- its own docstring even says so ("still its own if/elif
# chain here -- unified onto the ModeHandler registry in Task 3.3"). Task 4.1 assumes Tasks
# 0.1-3.3 already landed; this sweep found that precondition doesn't hold for Task 3.3
# specifically. Left unchanged here -- unifying it is Task 3.3's own scope, not T4.1's, and
# this session's scope is T4.1 only. The three old peak-tracking fields, `_last_active_soc_
# limit`, and `_run_cycle`'s own old per-mode if/elif chain (Tasks 1.2/2.2/3.2) ARE confirmed
# fully removed (grep + read, both clean).


async def test_power_opt_out_of_r3_does_not_disable_c4_ceiling(hass):
    """ADR-0006 Option B: the R17 opt-out can only ever skip step 7 (R3 peak clamp); step 8
    (C4 grid-ceiling clamp) has no opt-out of its own and must still bind. This is the
    discriminating case test_power_can_opt_out_of_peak_protection above cannot provide: that
    test's grid ceiling (23A headroom) never actually falls below the 16A target, so it can't
    tell a merged single-conditional clamp (Option A, rejected) from two distinct call sites --
    a merged implementation would also return 16.0 here, unclamped."""
    config = _config()
    config = dataclasses.replace(config, power_respect_peak=False)
    config = dataclasses.replace(config, grid_ceiling_a=10.0)
    # headroom = 8A, below the 16A target.
    config = dataclasses.replace(config, grid_safety_offset_a=2.0)
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=0.0)

    _coord, result = await _run(hass, adapters, config, target=16.0)

    assert result.commanded_current == 8.0


async def test_adr0006_clamp_and_smoothing_call_order_is_preserved(hass, monkeypatch):
    """ADR-0006: 'coordinator.py is the one place the ten-step order lives in code; a change
    to step order... is a change to this ADR'. Observes the actual call order of the
    module-level step functions coordinator.py imports, rather than grepping for call sites,
    to prove ADR-0012's decomposition didn't reorder or merge them."""
    call_order = []

    def _spy(name, real):
        def wrapper(*args, **kwargs):
            call_order.append(name)
            return real(*args, **kwargs)

        return wrapper

    spied = (
        "resolve_voltage",
        "smooth_net_power",
        "apply_peak_clamp",
        "clamp_to_ceiling",
        "apply_floor_cap",
    )
    for name in spied:
        monkeypatch.setattr(coordinator_module, name, _spy(name, getattr(coordinator_module, name)))
    adapters = _adapters(status=STATE_CHARGING, net_w=0.0, charger_w=1000.0)

    _coord, result = await _run(hass, adapters, _config(), target=10.0)

    assert result.fault is False
    # Voltage (step 3, NF4) resolves before this cycle's net-power smoothing call (step 2's
    # mode-dispatch reading) in this implementation; steps 7 (R3), 8 (C4), 9 (C1 floor/cap)
    # then run in ADR-0006's fixed order -- neither reordered nor merged.
    assert call_order == [
        "resolve_voltage",
        "smooth_net_power",
        "apply_peak_clamp",
        "clamp_to_ceiling",
        "apply_floor_cap",
    ]


async def test_read_owned_entities_updates_active_mode(hass):
    """ADR-0018: the coordinator reads active_mode through the Store, via its own setter --
    the mutation point (set_active_mode) is unchanged, only the caller is."""
    store = _FakeStore({(Platform.SELECT, OWNED_SUFFIX_MODE): MODE_SOLAR})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.active_mode == MODE_SOLAR


async def test_read_owned_entities_leaves_field_unchanged_when_store_returns_none(hass):
    """Success criterion 4: a missing/unresolvable read is not a fault -- keep the current value."""
    store = _FakeStore({})  # every read() call returns None
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    coord.set_active_mode(MODE_POWER)
    await coord._read_owned_entities()
    assert coord.active_mode == MODE_POWER


async def test_read_owned_entities_clamps_target_current_via_existing_setter(hass):
    """The Store-read value still goes through set_target_current's own clamp (ADR-0014) --
    confirms the mutation point didn't change, only its caller."""
    store = _FakeStore(
        {(Platform.NUMBER, OWNED_SUFFIX_TARGET_CURRENT): 99.0}
    )  # _config()'s max is 16.0
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.target_current == 16.0


async def test_read_owned_entities_updates_active_profile(hass):
    """ADR-0018: the coordinator reads active_profile through the Store, via its own
    setter -- the mutation point (set_active_profile) is unchanged, only the caller is."""
    store = _FakeStore({(Platform.SELECT, OWNED_SUFFIX_PROFILE): PROFILE_AUTO})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.active_profile == PROFILE_AUTO


async def test_read_owned_entities_clamps_soc_limit_override_via_existing_setter(hass):
    """The Store-read value still goes through set_soc_limit_override's own clamp
    (ADR-0014) -- confirms the mutation point didn't change, only its caller."""
    store = _FakeStore(
        {(Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): 150.0}
    )  # SOC_LIMIT_OVERRIDE_MAX is 100.0
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.soc_limit_override == SOC_LIMIT_OVERRIDE_MAX


async def test_read_owned_entities_updates_home_day_flag(hass):
    store = _FakeStore({(Platform.SWITCH, OWNED_SUFFIX_HOME_DAY): True})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.home_day_flag is True


async def test_read_owned_entities_updates_departure_dow_defaults(hass):
    store = _FakeStore({(Platform.TIME, OWNED_SUFFIX_DEPARTURE_DOW[0]): time_of_day(6, 0)})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.departure_dow_defaults[0] == time_of_day(6, 0)  # Monday=0


async def test_read_owned_entities_updates_departure_holiday_override(hass):
    store = _FakeStore({(Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOLIDAY): time_of_day(7, 30)})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.departure_holiday_override == time_of_day(7, 30)


async def test_read_owned_entities_updates_departure_home_day_override(hass):
    store = _FakeStore({(Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOME_DAY): time_of_day(8, 0)})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.departure_home_day_override == time_of_day(8, 0)


async def test_read_owned_entities_leaves_departure_dow_default_unchanged_when_store_returns_none(
    hass,
):
    store = _FakeStore({})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    coord.departure_dow_defaults[0] = time_of_day(6, 0)
    await coord._read_owned_entities()
    assert coord.departure_dow_defaults[0] == time_of_day(6, 0)


async def test_run_cycle_reads_owned_entities_before_anything_else(hass):
    """system-design.md §5.1: the Store read is the cycle's first step, ahead of the
    hardware-adapter read -- a mode change is visible to every step in the same cycle."""
    store = _FakeStore({(Platform.SELECT, OWNED_SUFFIX_MODE): MODE_SOLAR_ONLY})
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._run_cycle()
    assert coord.active_mode == MODE_SOLAR_ONLY


async def test_read_owned_entities_does_not_overwrite_active_mode_under_auto(hass):
    """Regression: under Auto, active_mode is select_mode()'s own resolution, carried
    across cycles -- the Store's raw selector read (the user's last manual choice, which
    Auto ignores) must not overwrite it. Overwriting it would falsely register as a mode
    *change* to _reset_mode_state_if_changed(), silently discarding R7/R11 timers and R3's
    breach cooldown every single cycle."""
    store = _FakeStore(
        {
            (Platform.SELECT, OWNED_SUFFIX_PROFILE): PROFILE_AUTO,
            (Platform.SELECT, OWNED_SUFFIX_MODE): MODE_OFF,
        }
    )
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    coord.set_active_profile(PROFILE_AUTO)
    coord.set_active_mode(MODE_CAPTAR)  # simulates Auto's own resolution from a prior cycle
    await coord._read_owned_entities()
    assert coord.active_mode == MODE_CAPTAR  # unchanged -- the stale selector (Off) not applied


async def test_read_owned_entities_applies_every_table_driven_read(hass):
    """#652: the five reads with no cross-read dependency (target_current, soc_limit_override,
    home_day_flag, the two departure overrides) now run through a `simple_reads` table instead
    of five hand-written blocks -- confirms the loop applies every row in one call, catching an
    early `break` or a duplicated/dropped table row that per-field tests (below) each run in
    isolation wouldn't. See _read_owned_entities' docstring for why this is a readability-only
    change (asyncio.gather was investigated and rejected)."""
    store = _FakeStore(
        {
            (Platform.NUMBER, OWNED_SUFFIX_TARGET_CURRENT): 12.0,
            (Platform.NUMBER, OWNED_SUFFIX_SOC_LIMIT_OVERRIDE): 80.0,
            (Platform.SWITCH, OWNED_SUFFIX_HOME_DAY): True,
            (Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOLIDAY): time_of_day(7, 30),
            (Platform.TIME, OWNED_SUFFIX_DEPARTURE_HOME_DAY): time_of_day(8, 0),
        }
    )
    coord = SmartChargingCoordinator(
        hass, adapters=_adapters(), store=store, config=_config(), interval_s=30
    )
    await coord._read_owned_entities()
    assert coord.target_current == 12.0
    assert coord.soc_limit_override == 80.0
    assert coord.home_day_flag is True
    assert coord.departure_holiday_override == time_of_day(7, 30)
    assert coord.departure_home_day_override == time_of_day(8, 0)
