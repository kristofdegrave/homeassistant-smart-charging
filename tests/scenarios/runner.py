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

from homeassistant.util import dt as dt_util

from tests.helpers import capture_charger_current_writes, seed_charger_states, seed_owned_entity
from tests.scenarios.plant import Plant, StepReading


@dataclass(frozen=True)
class CycleTrace:
    """One cycle's full trace -- what a scenario prints on failure and asserts against."""

    index: int
    commanded_current_a: float  # what THIS cycle's control cycle actually wrote
    reading: StepReading
    faulted: bool  # this cycle's coordinator.data.fault -- a faulted cycle writes 0 A


class ScenarioRunner:
    """Runs one scenario's timeline: a `Plant` plus the HA harness state it drives through."""

    def __init__(
        self,
        hass,
        coordinator,
        plant: Plant,
        *,
        freezer,
        mode: str,
        status: str = "Charging",
        ev_soc: float = 50.0,
        grid_voltage: float = 230.0,
        charger_current_entity_id: str = "number.charger_current",
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._plant = plant
        self._freezer = freezer
        self._mode = mode
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
            # The mode select is a real, polled (`should_poll=True`) entity: left seeded only
            # once, its own periodic poll re-asserts its internal default option (`Off`) over
            # the direct `hass.states.async_set` this scenario relies on, silently reverting the
            # scenario's chosen mode partway through a long-running timeline. Re-seeding every
            # cycle keeps the external selection in force throughout, the same way the charger
            # states above are re-seeded rather than set once.
            seed_owned_entity(self._hass, "select.smart_charging_mode", self._mode)
            self._freezer.move_to(dt_util.now() + self._interval)
            await self._coordinator.async_refresh()
            await self._hass.async_block_till_done()

            # Only the charger-current entity's writes are this scenario's commanded current --
            # a future owned-number write (e.g. a peak/soc helper) must not be fed into the
            # plant as though it were one.
            commanded = next(
                (
                    c["value"]
                    for c in reversed(self._calls)
                    if c.get("entity_id") == self._charger_current_entity_id
                ),
                0.0,
            )
            self._plant.record_write(commanded)
            self.trace.append(
                CycleTrace(
                    index=len(self.trace),
                    commanded_current_a=commanded,
                    reading=reading,
                    faulted=bool(self._coordinator.data.fault),
                )
            )
        return self.trace


def format_trace(trace: list[CycleTrace]) -> str:
    """A per-step trace table for a failure message -- commanded current, true draw, reported
    reading, true import and fault status at each step, so a violation is legible without
    re-running."""
    header = (
        f"{'step':>4} {'commanded_a':>12} {'true_draw_a':>12} "
        f"{'reported_w':>11} {'true_import_w':>14} {'fault':>6}"
    )
    lines = [header]
    for t in trace:
        r = t.reading
        lines.append(
            f"{t.index:>4} {t.commanded_current_a:>12.1f} {r.true_draw_a:>12.1f} "
            f"{r.reported_charger_w:>11.1f} {r.true_import_w:>14.1f} {t.faulted!s:>6}"
        )
    return "\n".join(lines)
