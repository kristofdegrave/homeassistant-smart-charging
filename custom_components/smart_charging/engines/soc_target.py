"""SOC-Target engine (E3). Pure — no HA imports.

Full R7 has three priority rows (solar-reserve cap -> solar step-up -> default).
Rows 1-2 require the Auto profile (E2) and the solar step-up mechanism (UC06/R8),
neither of which exists yet -- row 1 can structurally never match without Auto
(resolution-rules.md's own note: "under Manual, row 1 never matches"), and row 2
has no step-up mechanism to trigger it. Row 3 -- the configured override -- is
therefore the COMPLETE resolution for the system as it currently exists, not a
stub; rows 1-2 are added here (not as a new service) once E2/UC06 land.
"""


def resolve_active_soc_limit(soc_limit_override: float) -> float:
    """Return the active SOC limit (R7, row 3: the configured default/override)."""
    return soc_limit_override
