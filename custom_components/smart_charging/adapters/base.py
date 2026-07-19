"""The Adapter protocol shared by every hardware role (ADR-0003)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class Adapter(Protocol):
    """One mapped hardware role. Numeric roles return floats; status returns a canonical state."""

    async def read(self) -> float | str | None:
        """Return the current canonical value, or None if missing/unavailable/unmapped."""
        ...

    async def write(self, value: float | str) -> None:
        """Write a value to the role. Read-only roles raise NotImplementedError."""
        ...
