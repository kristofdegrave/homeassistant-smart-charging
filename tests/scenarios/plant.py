"""The physical world a scenario timeline drives (ADR-0037, epic #996). Test-only -- product
code takes no dependency on this module (ADR-0037's Consequences).

Models exactly what #996's *Decisions this slice makes* settle, and nothing else (the plant
"carries only what its scenarios read", ADR-0037's deferrals): the charger's true draw follows
the current written at the end of the previous cycle, so even a lag-0 scenario has the one-cycle
actuation delay a real charger has; the charger's *power reading* -- what a real EVSE power
meter reports -- additionally lags that true draw by a configurable further number of cycles;
and the whole-home meter derives net import from the true draw against the household load, never
from the charger's own (possibly lagged) self-report, matching a real meter that reads actual
instantaneous import.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StepReading:
    """One cycle's derived readings, plus the ground truth a scenario's invariants/assertions
    need and that production code structurally cannot see (ADR-0037's invariant-oracle rule):
    ``net_w``/``reported_charger_w`` are what the runner seeds into HA; ``true_draw_a``/
    ``true_import_w`` are the plant's own ground truth, read by a scenario's assertions, never
    by the coordinator under test."""

    true_draw_a: float
    true_charger_w: float
    reported_charger_w: float
    household_w: float
    true_import_w: float
    net_w: float  # always ground truth -- the meter, unlike the charger, does not lag


class Plant:
    """One scenario's physical world. ``step()`` advances it by exactly one control cycle;
    ``record_write(current_a)`` feeds back the current the coordinator actually wrote that
    cycle, which becomes the *next* cycle's true draw."""

    def __init__(self, *, household_w: float, voltage: float = 230.0, lag_cycles: int = 0) -> None:
        self.voltage = voltage
        self.lag_cycles = lag_cycles
        self._household_w = household_w
        self._true_draw_history: list[float] = []
        self._last_written_a = 0.0

    def set_household_w(self, household_w: float) -> None:
        """Script a household-load step. Steady (the constructor's value) until a scenario
        calls this -- no scenario under this task needs it, but a later one will."""
        self._household_w = household_w

    def step(self) -> StepReading:
        """Advance one cycle. The current written at the end of the *previous* cycle
        (``record_write``) becomes this cycle's true draw -- 0 A for the very first cycle,
        since nothing has been commanded yet."""
        true_draw_a = self._last_written_a
        self._true_draw_history.append(true_draw_a)

        lag_index = len(self._true_draw_history) - 1 - self.lag_cycles
        reported_draw_a = self._true_draw_history[lag_index] if lag_index >= 0 else 0.0

        true_charger_w = true_draw_a * self.voltage
        reported_charger_w = reported_draw_a * self.voltage
        true_import_w = true_charger_w + self._household_w

        return StepReading(
            true_draw_a=true_draw_a,
            true_charger_w=true_charger_w,
            reported_charger_w=reported_charger_w,
            household_w=self._household_w,
            true_import_w=true_import_w,
            net_w=true_import_w,
        )

    def record_write(self, current_a: float) -> None:
        """The current the coordinator actually wrote this cycle -- becomes the next cycle's
        true draw (``step``'s own docstring)."""
        self._last_written_a = current_a
