"""The Adapter protocol shared by every hardware role (ADR-0003)."""

from datetime import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Adapter(Protocol):
    """One mapped hardware role. Numeric roles return floats; status returns a canonical state.

    Widened for Task 2.1 (RA2) to also cover the `bool`-typed `home_day_external` role
    (`BooleanReadAdapter`) and the `time`-typed `departure_external` role
    (`TimeReadAdapter`) -- neither fits `NumericReadAdapter`/`StatusReadAdapter` cleanly
    (design doc §4 note), so this Protocol's value union grows rather than either of
    those two classes being reshaped to fit a value they don't natively hold.
    """

    async def read(self) -> float | str | bool | time | None:
        """Return the current canonical value, or None if missing/unavailable/unmapped."""
        ...

    async def write(self, value: float | str | bool | time) -> None:
        """Write a value to the role. Read-only roles raise NotImplementedError."""
        ...
