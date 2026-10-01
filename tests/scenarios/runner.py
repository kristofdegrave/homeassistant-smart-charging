"""Drives a `Plant` through real coordinator cycles (ADR-0037, epic #996). Test-only --
product code takes no dependency on this module (ADR-0037's Consequences).

One plant step per control cycle (#996's *Decisions this slice makes*): seed this cycle's
derived readings, advance the frozen clock by the entry's configured control interval so R3's
grace period and R11's holds/cooldowns see real elapsed time, then call
`coordinator.async_refresh()` -- through the same `tests/helpers.py` seeding path
(`seed_charger_states`/`capture_charger_current_writes`) every other HA-harness suite uses, not
a replacement for it.

T2 wires the shared invariant set (`invariants.py`) in here, as `run`'s own `judge` callback,
rather than leaving a scenario to loop back over the whole trace afterwards: every cycle of
every scenario is judged the moment it is recorded, and a breach is reported -- as
`InvariantViolation`, naming the first violating cycle with its context -- from the cycle it
first appears in rather than from some later, unrelated assertion.
"""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.util import dt as dt_util

from tests.helpers import capture_charger_current_writes, seed_charger_states
from tests.scenarios.plant import Plant, StepReading


@dataclass(frozen=True)
class CycleTrace:
    """One cycle's full trace -- what a scenario prints on failure and asserts against."""

    index: int
    commanded_current_a: float  # what THIS cycle's control cycle actually wrote
    reading: StepReading
    faulted: bool  # this cycle's coordinator.data.fault -- a faulted cycle writes 0 A
    active_mode: str  # coordinator.active_mode as of this cycle -- proves the mode never reverted


class ScenarioRunner:
    """Runs one scenario's timeline: a `Plant` plus the HA harness state it drives through."""

    def __init__(
        self,
        hass,
        coordinator,
        plant: Plant,
        *,
        freezer,
        status: str = "Charging",
        ev_soc: float = 50.0,
        grid_voltage: float = 230.0,
        charger_current_entity_id: str = "number.charger_current",
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._plant = plant
        self._freezer = freezer
        # The control interval is the entry's own (`coordinator.update_interval`, set from
        # CONF_CONTROL_INTERVAL_S/DEFAULT_CONTROL_INTERVAL_S in __init__.py) -- never a free
        # parameter here, so a scenario overriding the entry option can't silently desync this
        # runner's clock advance from R3's grace period and R11's holds.
        self._interval = coordinator.update_interval
        self._status = status
        self._ev_soc = ev_soc
        self._grid_voltage = grid_voltage
        self._charger_current_entity_id = charger_current_entity_id
        self._calls = capture_charger_current_writes(hass)
        self._last_commanded = 0.0  # a cycle with no write of its own keeps the plant's
        # previous command in force, explicitly, rather than reaching into the whole history.
        self.trace: list[CycleTrace] = []

    async def run(
        self, cycles: int, *, judge: Callable[[list[CycleTrace]], None] | None = None
    ) -> list[CycleTrace]:
        """Run `cycles` further control cycles, appending each one's trace to `self.trace`
        (so a scenario driving `run` more than once keeps the whole timeline). `judge`, when
        given, is called with `self.trace` right after each cycle is appended -- so a violation
        raises (`InvariantViolation`, `invariants.py`) from the cycle it first appears in,
        naming the first violating cycle rather than some later one a full-trace scan would
        also find. A scenario composes which invariants apply to it (R3 only where it applies
        at all -- CapTar present, and in `Power` its own option enabled) via
        `invariants.judge_all` and passes the result here; `run` itself knows nothing about
        which invariants exist."""
        for _ in range(cycles):
            reading = self._plant.step()
            seed_charger_states(
                self._hass,
                status=self._status,
                net_w=reading.net_w,
                charger_w=reading.reported_charger_w,
                ev_soc=self._ev_soc,
                grid_voltage=self._grid_voltage,
            )
            self._freezer.move_to(dt_util.now() + self._interval)
            # The mode is selected once, through the real `select.select_option` service, before
            # `run` is ever called (never re-asserted here) -- see `_setup` in the scenario
            # module. Recording `active_mode` below is this runner's own proof that the polled
            # mode select entity's periodic poll never reverts that selection mid-timeline.
            calls_before = len(self._calls)
            await self._coordinator.async_refresh()
            await self._hass.async_block_till_done()

            # Only the charger-current entity's writes are this scenario's commanded current --
            # a future owned-number write (e.g. a peak/soc helper) must not be fed into the
            # plant as though it were one. And only a write from THIS cycle counts: a cycle that
            # writes nothing leaves the plant's previous command in force explicitly, rather than
            # silently picking up an older write from earlier in the whole history.
            commanded = next(
                (
                    c["value"]
                    for c in reversed(self._calls[calls_before:])
                    if c.get("entity_id") == self._charger_current_entity_id
                ),
                self._last_commanded,
            )
            self._last_commanded = commanded
            self._plant.record_write(commanded)
            self.trace.append(
                CycleTrace(
                    index=len(self.trace),
                    commanded_current_a=commanded,
                    reading=reading,
                    faulted=bool(self._coordinator.data.fault),
                    active_mode=self._coordinator.active_mode,
                )
            )
            if judge is not None:
                judge(self.trace)
        return self.trace


def format_trace(trace: list[CycleTrace], *, target_w: float | None = None) -> str:
    """A per-step trace table for a failure message -- commanded current, true draw, reported
    reading, true import, fault status and active mode at each step, so a violation is legible
    without re-running. `target_w`, when given, adds a headroom column (`target_w` minus that
    step's true import) against the limit a caller is judging -- the surrounding cycles' own
    headroom, not only the violating one's, as an invariant's failure message needs."""
    header = (
        f"{'step':>4} {'commanded_a':>12} {'true_draw_a':>12} "
        f"{'reported_w':>11} {'true_import_w':>14} {'fault':>6} {'active_mode':>12}"
    )
    if target_w is not None:
        header += f" {'headroom_w':>11}"
    lines = [header]
    for t in trace:
        r = t.reading
        line = (
            f"{t.index:>4} {t.commanded_current_a:>12.1f} {r.true_draw_a:>12.1f} "
            f"{r.reported_charger_w:>11.1f} {r.true_import_w:>14.1f} {t.faulted!s:>6} "
            f"{t.active_mode:>12}"
        )
        if target_w is not None:
            line += f" {target_w - r.true_import_w:>11.1f}"
        lines.append(line)
    return "\n".join(lines)
