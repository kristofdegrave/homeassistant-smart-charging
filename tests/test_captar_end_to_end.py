"""End-to-end HA-harness regression for UC03 (Captar) -- Task 6.2.

Drives the full stack (`hass.config_entries` setup + `coordinator.async_refresh()`), not
`modes.captar.step` directly -- Phase 1's pure-logic suite (`tests/modes/test_captar.py`)
already covers the state machine in isolation; this file proves the coordinator wiring
(Task 5.1/6.1) dispatches to it correctly through a real config entry, including the R3
peak clamp (Billing-Protection Engine, E5) and the SOC gate.
"""

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CAPTAR_AVAILABLE,
    CONF_EV_SOC_ENTITY,
    CONF_MAX_PEAK_KW,
    CONF_PEAK_GRACE_MIN,
    CONF_SAFETY_MARGIN_W,
    CONF_SMOOTHING_WINDOW,
    CONF_SOLAR_AVAILABLE,
    DOMAIN,
    MODE_CAPTAR,
    STATUS_OK,
)
from custom_components.smart_charging.coordinator_cycle import ActiveCooldown
from custom_components.smart_charging.modes._phase import Phase
from tests.helpers import (
    capture_charger_current_writes,
    entry_data_base,
    entry_options_base,
    replace_coordinator_config,
    seed_ample_peak_headroom,
    seed_charger_states,
    seed_owned_entity,
)


def _entry_data():
    """DATA bucket -- entity-role mappings + translation only (ADR-0005), plus this suite's
    own Captar-specific overrides on top of the shared base shape."""
    return entry_data_base(
        **{
            CONF_SOLAR_AVAILABLE: False,
            CONF_CAPTAR_AVAILABLE: True,
            CONF_EV_SOC_ENTITY: "sensor.ev_soc",
        }
    )


def _entry_options(**overrides):
    """OPTIONS bucket -- thresholds/defaults + interval (ADR-0005).

    R3's peak-protection numbers (`safety_margin_w`, `max_peak_kw`, `peak_grace_min`) are
    left at their real defaults unless a test needs to override one to exercise a specific
    boundary -- this suite exercises the same numbers a real install would see. This
    suite's own addition on top of the shared base (isolating raw readings from R10's
    rolling average) is applied before the caller's own overrides, so a test can still
    override it too.
    """
    return entry_options_base(**{CONF_SMOOTHING_WINDOW: 1, **overrides})


_capture_charger_current_writes = capture_charger_current_writes


def _seed_states(
    hass, *, status: str, net_w: float = 0.0, charger_w: float = 0.0, ev_soc: float = 50.0
) -> None:
    seed_charger_states(hass, status=status, net_w=net_w, charger_w=charger_w, ev_soc=ev_soc)


_seed_ample_peak_headroom = seed_ample_peak_headroom


def _effective_peak_limit_state(hass):
    """Look up the diagnostic EffectivePeakLimitSensor by unique_id, not entity_id -- its
    friendly-name-derived entity_id depends on the select.mode-style translation entry T6.3
    (translations/strings) adds, not this task (see tests/test_init.py's identical note)."""
    entry_id = hass.config_entries.async_entries(DOMAIN)[0].entry_id
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry_id}_effective_peak_limit")
    return hass.states.get(entity_id)


async def _setup(hass, **option_overrides):
    calls = _capture_charger_current_writes(hass)
    _seed_states(hass, status="Connected")
    entry = MockConfigEntry(
        domain=DOMAIN, data=_entry_data(), options=_entry_options(**option_overrides)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    _seed_ample_peak_headroom(coordinator)
    seed_owned_entity(hass, "select.smart_charging_mode", MODE_CAPTAR)
    return coordinator, calls


async def _cycle(
    hass,
    coordinator,
    *,
    net_w: float = 0.0,
    charger_w: float = 0.0,
    status: str = "Connected",
    ev_soc: float = 50.0,
):
    """Seed one cycle's readings and drive it through the real coordinator refresh."""
    _seed_states(hass, status=status, net_w=net_w, charger_w=charger_w, ev_soc=ev_soc)
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_uc03_main_success_starts_at_max_current_within_headroom(hass):
    """UC03 steps 1-3: with Captar active, the car connected, SOC below the active limit,
    no cooldown running, and ample peak headroom, the System starts grid charging within
    one control cycle and requests the maximum charging current."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0})

    # baseline household load (net_w - charger_w) = 0 W -> ample headroom -> the R3 clamp
    # does not reduce the max-current request (16 A).
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING
    assert hass.states.get("sensor.smart_charging_active_mode").state == MODE_CAPTAR
    assert hass.states.get("sensor.smart_charging_status").state == STATUS_OK
    # C3: the effective-peak-limit sensor reflects the configured max_peak_kw this cycle
    # (min(monthly_peak_kw, max_peak_kw) with the ample seeded peak) -- ties this set-point
    # to the clamp bound that produced it, the whole point of this suite.
    assert _effective_peak_limit_state(hass).state == "4.0"


async def test_uc03_2a_cooldown_blocks_restart_until_it_elapses(hass):
    """UC03 alternate 2a: a running Captar cooldown -- entered via a sustained R3 breach
    stop -- blocks a restart even once headroom is restored, and the System starts again
    only on the first qualifying cycle after the cooldown has fully elapsed."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0, CONF_PEAK_GRACE_MIN: 0.0})

    # Charging starts, then a breach at the minimum current that is immediately "sustained"
    # (0-minute grace period) forces a stop into cooldown.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    # A steady cycle first, so the breach lands on a reading R3 trusts rather than on one
    # deferred by R3 case (a) after the 0 A -> 16 A step above.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # Headroom is fully restored, but the (default 10-minute) cooldown has not had time to
    # elapse in real wall-clock terms -- the System must stay stopped (2a).
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN

    # Simulate the cooldown having fully elapsed (avoiding a real 10-minute wall-clock wait)
    # and confirm the System starts again on the next qualifying cycle. Since issue #974,
    # `replace_coordinator_config` alone no longer suffices: R11's rapid-cycling cooldown is
    # now also tracked coordinator-scoped (`_active_cooldown`), with its duration fixed at
    # the moment charging stopped precisely so a later config change can't shorten it
    # (requirements.md R11's "not shortened by a change in conditions"). Simulate elapse via
    # `ActiveCooldown.elapsed()` itself -- zero its duration rather than discarding the object
    # (discarding it would exercise disconnect semantics, not elapse semantics, and would
    # never catch a broken `elapsed()` comparison).
    replace_coordinator_config(coordinator, captar_cooldown_min=0.0)
    coordinator._active_cooldown = ActiveCooldown(coordinator._active_cooldown.stop_at, 0.0)
    # Two qualifying cycles, not one, and R3's own criteria say why: the drop from the 3600 W
    # breach back to 0 W increases headroom, so case (b) defers it until a second consecutive
    # observation confirms it -- and the cycle right after the forced stop to 0 A is a case-(a)
    # deferral, which is not an observation and so does not count towards case (b)'s window.
    # R3's accepted baseline is still the breach value until then, which is what holds the
    # set-point at 0 A here rather than the cooldown, which has already been elapsed above.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_uc03_peak_clamp_reduces_set_point_within_headroom(hass):
    """UC03 exception flow: the R3 peak clamp fits the max-current request (raw) to the
    available peak headroom when household load leaves less than the maximum -- but still
    at least the minimum -- charging current of headroom, reducing (not stopping) the
    set-point this cycle.

    (UC03's exception flow also names the C4 grid-supply-ceiling clamp as a second way the
    set-point can be reduced/stopped -- that clamp is mode-agnostic and already covered at
    engine level by `tests/engines/test_grid_safety.py`, so it is deferred there rather than
    duplicated here, the same call the sibling `test_solar_end_to_end.py` makes for its own
    out-of-scope alternates.)"""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0, CONF_SAFETY_MARGIN_W: 250.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    # R3 case (a): that cycle stepped the set-point 0 A -> 16 A, so the NEXT cycle's
    # household-baseline reading is deferred. One steady cycle settles it, as a real install
    # settles between two set-point changes. The deferral has its own test below; asserting
    # the same-cycle reduction needs a reading R3 is allowed to trust.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0

    # target_w = 4000 - 250 = 3750 W; baseline_w = 2000 W (household load) -> headroom_a =
    # floor(1750 / 230) = 7 A -- between the 6 A minimum and the 16 A maximum, so the clamp
    # reduces the set-point without stopping charging.
    await _cycle(hass, coordinator, net_w=2000.0, charger_w=0.0)
    assert calls[-1]["value"] == 7.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_uc03_peak_clamp_defers_a_reading_that_follows_its_own_step_by_one_cycle(hass):
    """R3 case (a) (ADR-0039): a household-baseline reading taken after the System changed the
    charger current partly measures that change rather than the household, so it is deferred and
    the previously accepted reading stands -- for exactly one control cycle, never two. This is
    the bounded exception to the same-cycle reduction the test above asserts."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0, CONF_SAFETY_MARGIN_W: 250.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0  # steps 0 A -> 16 A, so the next reading is deferred

    # 2000 W of household load arrives on the very next cycle. R3 does not act on it -- the
    # accepted baseline is still 0 W, so R3's own headroom is unchanged at the 16 A maximum --
    # and the set-point is therefore NOT R3's 7 A this cycle.
    await _cycle(hass, coordinator, net_w=2000.0, charger_w=0.0)
    assert calls[-1]["value"] != 7.0

    # One cycle later the same load is read again with no intervening step, so R3 accepts it
    # and the reduction lands. The deferral is one cycle, never two (R3 case (a)).
    await _cycle(hass, coordinator, net_w=2000.0, charger_w=0.0)
    assert calls[-1]["value"] == 7.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING


async def test_uc03_c4_still_clamps_on_the_cycle_r3_defers(hass):
    """R3's deferral is safe rather than merely tolerable because C4 never defers (R3's own
    criterion, and C3/C4's division): on the one cycle R3 holds its previous baseline, the
    grid-supply-ceiling clamp still reads raw and still bounds the set-point."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0, CONF_SAFETY_MARGIN_W: 250.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0

    # The step above defers R3's reading on this cycle, so R3's own headroom is still the one
    # it accepted at 0 W of household load -- the 16 A maximum, no reduction at all. C4 reads
    # raw regardless: floor((25 - 2) - 3600/230) = floor(23 - 15.65) = 7 A. So the 7 A written
    # here is C4's bound alone, on a cycle R3 contributed nothing.
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 7.0, "C4 must clamp on the cycle R3 defers"


async def test_uc03_sustained_r3_breach_stops_and_starts_cooldown(hass):
    """UC03 exception flow: a momentary breach at the minimum charging current holds at
    the minimum rather than stopping (R3: "a momentary breach does not stop charging"),
    but once that breach has held continuously for the configured grace period, the System
    stops (0 A) and starts the Captar cooldown (R11)."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0
    # A steady cycle, so the breach below lands on a reading R3 is allowed to trust rather than
    # on one deferred by R3 case (a) after the 0 A -> 16 A step above.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0)
    assert calls[-1]["value"] == 16.0

    # target_w = 4000 - 250 = 3750 W; baseline_w = 3600 W -> headroom_a = floor(150 / 230) =
    # 0 A, below the 6 A minimum -- a breach, but the default grace period has not elapsed
    # yet, so the System holds at the minimum current rather than stopping.
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 6.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.CHARGING

    # Simulate the grace period having fully elapsed (avoiding a real wall-clock wait) --
    # the same continuing breach now forces a stop and starts the Captar cooldown.
    replace_coordinator_config(coordinator, peak_grace_min=0.0)
    await _cycle(hass, coordinator, net_w=3600.0, charger_w=0.0)
    assert calls[-1]["value"] == 0.0
    assert coordinator._mode_state[MODE_CAPTAR].phase == Phase.COOLDOWN


async def test_uc03_soc_limit_reached_stops_charging(hass):
    """UC03 exception flow: state of charge reaching the active SOC limit stops charging
    (0 A) and does not resume above that limit while it continues to hold."""
    coordinator, calls = await _setup(hass, **{CONF_MAX_PEAK_KW: 4.0})

    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0, ev_soc=50.0)
    assert calls[-1]["value"] == 16.0

    # SOC reaches the (default 80%) active SOC limit -> stop, and stay stopped on the next
    # cycle too even though headroom is still ample.
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0, ev_soc=80.0)
    assert calls[-1]["value"] == 0.0
    await _cycle(hass, coordinator, net_w=0.0, charger_w=0.0, ev_soc=80.0)
    assert calls[-1]["value"] == 0.0
