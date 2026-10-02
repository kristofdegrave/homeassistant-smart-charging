"""Shared scenario-setup plumbing every tier builds its own `_setup` from (epic #996), so a
later tier reuses this rather than reaching into an earlier tier's private names."""

from collections.abc import Callable

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import (
    CONF_CONTROL_INTERVAL_S,
    CONF_GRID_CEILING_A,
    CONF_MAX_PEAK_KW,
    CONF_MIN_CURRENT,
    CONF_NOMINAL_VOLTAGE,
    CONF_PEAK_GRACE_MIN,
    CONF_SAFETY_MARGIN_W,
    DOMAIN,
)
from tests.scenarios.invariants import check_c4, check_r3, judge_all
from tests.scenarios.runner import CycleTrace, format_trace


async def setup_coordinator(hass, *, entry_data: dict, entry_options: dict, mode: str):
    """Set up a config entry from `entry_data`/`entry_options` and select `mode` through the
    real `select.select_option` service -- never a raw state write (`seed_owned_entity`): a raw
    write is not what a real user action produces, and the mode select is a real, polled
    (`should_poll=True`) entity whose own poll would otherwise contend with a re-seed. Returns
    the entry's coordinator."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data, options=entry_options)
    entry.add_to_hass(hass)
    if not await hass.config_entries.async_setup(entry.entry_id):
        # A bare `assert` here would raise AssertionError, which a caller's own
        # `pytest.raises(InvariantViolation)` -- `InvariantViolation` subclasses
        # `AssertionError` -- would then accept as though it were the expected invariant breach:
        # a setup failure must surface as something else entirely.
        raise RuntimeError(f"config entry {entry.entry_id} failed to set up")
    await hass.async_block_till_done()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.smart_charging_mode", "option": mode},
        blocking=True,
    )
    return entry.runtime_data.coordinator


def assert_charged_without_fault(trace: list[CycleTrace]) -> None:
    """The non-vacuity guard for a "no limit was breached" scenario: no cycle faulted (a faulted
    cycle's safe write is 0 A, which holds every limit vacuously) and some cycle commanded more
    than 0 A (a charger starved to 0 A holds them too)."""
    assert not any(t.faulted for t in trace), (
        f"a faulted cycle writes 0 A, which would pass the limit checks vacuously\n"
        f"{format_trace(trace)}"
    )
    assert any(t.commanded_current_a > 0 for t in trace), (
        f"no cycle commanded more than 0 A, so the limit checks held vacuously\n"
        f"{format_trace(trace)}"
    )


def effective_peak_limit_w(options: dict) -> float:
    """R3's own target: `resolve_effective_peak_limit`'s formula, pinned wherever a scenario
    sets `max_peak_kw == peak_floor_kw` to exactly `max_peak_kw` regardless of the
    internally-tracked monthly peak -- not restated as a bare number."""
    return options[CONF_MAX_PEAK_KW] * 1000.0 - options[CONF_SAFETY_MARGIN_W]


def judge_c4_then_r3(options: dict) -> Callable[[list[CycleTrace]], None]:
    """Every cycle of an R3 scenario judged by the whole invariant set, not R3 alone: `check_c4`
    is wired in ahead of `check_r3` via `judge_all` (`judge_all`'s own ordering rule -- C4 first,
    since R3 only ever applies where C4 does too). A scenario whose loads never reach C4's
    ceiling stays quiet on that check throughout, so every breach it sees is still, correctly,
    R3's -- a caller relying on that should still wire C4 in here rather than calling `check_r3`
    alone, so a future change that does push a load past the ceiling is still caught by whichever
    check is first to see it."""
    target_w = effective_peak_limit_w(options)
    min_current_a = options[CONF_MIN_CURRENT]
    grace_period_s = options[CONF_PEAK_GRACE_MIN] * 60.0
    control_interval_s = options[CONF_CONTROL_INTERVAL_S]
    ceiling_w = options[CONF_GRID_CEILING_A] * options[CONF_NOMINAL_VOLTAGE]

    def _check_c4(trace: list[CycleTrace]) -> None:
        check_c4(trace, ceiling_w=ceiling_w)

    def _check_r3(trace: list[CycleTrace]) -> None:
        check_r3(
            trace,
            effective_peak_limit_w=target_w,
            min_current_a=min_current_a,
            grace_period_s=grace_period_s,
            control_interval_s=control_interval_s,
        )

    def _judge(trace: list[CycleTrace]) -> None:
        judge_all(trace, [_check_c4, _check_r3])

    return _judge
