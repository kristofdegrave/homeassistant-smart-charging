"""Drives a `Plant` through real coordinator cycles (ADR-0037, epic #996). Test-only --
product code takes no dependency on this module (ADR-0037's Consequences).

One plant step per control cycle (#996's *Decisions this slice makes*): seed this cycle's
derived readings, advance the frozen clock by the entry's configured control interval so R3's
grace period and R11's holds/cooldowns see real elapsed time, then call
`coordinator.async_refresh()` -- through the same `tests/helpers.py` seeding path
(`seed_charger_states`/`capture_charger_current_writes`) every other HA-harness suite uses, not
a replacement for it.
"""

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.util import dt as dt_util

from tests.helpers import capture_charger_current_writes, seed_charger_states
from tests.scenarios.plant import Plant, StepReading


@dataclass(frozen=True)
class CycleTrace:
    """One cycle's full trace -- what a scenario prints on failure and asserts against."""

    index: int
    commanded_current_a: float  # what THIS cycle's control cycle actually wrote
    reading: StepReading


class ScenarioRunner:
    """Runs one scenario's timeline: a `Plant` plus the HA harness state it drives through."""

    def __init__(
        self,
        hass,
        coordinator,
        plant: Plant,
        *,
        freezer,
        control_interval_s: int,
        status: str = "Charging",
        ev_soc: float = 50.0,
        grid_voltage: float = 230.0,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._plant = plant
        self._freezer = freezer
        self._interval = timedelta(seconds=control_interval_s)
        self._status = status
        self._ev_soc = ev_soc
        self._grid_voltage = grid_voltage
        self._calls = capture_charger_current_writes(hass)
        self.trace: list[CycleTrace] = []

    async def run(self, cycles: int) -> list[CycleTrace]:
        """Run `cycles` further control cycles, appending each one's trace to `self.trace`
        (so a scenario driving `run` more than once keeps the whole timeline)."""
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
            await self._coordinator.async_refresh()
            await self._hass.async_block_till_done()

            commanded = self._calls[-1]["value"] if self._calls else 0.0
            self._plant.record_write(commanded)
            self.trace.append(
                CycleTrace(index=len(self.trace), commanded_current_a=commanded, reading=reading)
            )
        return self.trace


def format_trace(trace: list[CycleTrace]) -> str:
    """A per-step trace table for a failure message -- commanded current, true draw, reported
    reading and true import at each step, so a violation is legible without re-running."""
    header = (
        f"{'step':>4} {'commanded_a':>12} {'true_draw_a':>12} "
        f"{'reported_w':>11} {'true_import_w':>14}"
    )
    lines = [header]
    for t in trace:
        r = t.reading
        lines.append(
            f"{t.index:>4} {t.commanded_current_a:>12.1f} {r.true_draw_a:>12.1f} "
            f"{r.reported_charger_w:>11.1f} {r.true_import_w:>14.1f}"
        )
    return "\n".join(lines)
