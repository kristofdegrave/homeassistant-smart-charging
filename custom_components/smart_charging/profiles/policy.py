"""ModeSelectionPolicy Protocol and the Manual/Auto registry (ADR-0017). Pure -- no HA imports,
no cross-engine calls (mirrors profiles/auto.py's existing purity, ADR-0009/0010)."""

from typing import Any, Protocol, runtime_checkable

from ..const import PROFILE_AUTO, PROFILE_MANUAL
from .auto import AutoPolicy
from .manual import ManualPolicy


@runtime_checkable  # matches adapters/base.py's Adapter Protocol -- makes isinstance() against
# this Protocol a real conformance check (tests/profiles/test_policy.py), not a typing-only claim
class ModeSelectionPolicy(Protocol):
    """One role: given this cycle's observable conditions, which mode is active -- the one
    decision ADR-0017 identified as genuinely profiles/'s own. SOC-limit coordination and
    escalation levers are realized elsewhere (SOC-Target Engine; this Protocol's own Auto
    implementation's table rows), not as separate Profile roles."""

    def select(self, **kwargs: Any) -> str:
        """Return the active mode. Each implementation reads only the kwargs it needs; a
        caller must pass exactly the selected policy's own kwargs, not a union of both
        registered policies' parameter sets (Auto's select_mode() rejects unknown kwargs --
        design doc §3's Protocol docstring)."""
        ...


PROFILE_POLICIES: dict[str, ModeSelectionPolicy] = {
    PROFILE_MANUAL: ManualPolicy(),
    PROFILE_AUTO: AutoPolicy(),
}
