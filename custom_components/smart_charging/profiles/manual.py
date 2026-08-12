"""Manual profile mode-selection (E2, ADR-0017). Pure -- no HA imports, no cross-engine calls."""

from typing import Any


class ManualPolicy:
    """resolution-rules.md: "Manual needs no table" -- a pass-through of the user's own
    selection (R16). Reads only `active_mode`; every other kwarg a caller passes (Auto's
    observable-conditions inputs) is accepted and ignored, so both registry entries share
    one call shape (ModeSelectionPolicy.select(**kwargs))."""

    def select(self, *, active_mode: str, **_ignored: Any) -> str:
        return active_mode
