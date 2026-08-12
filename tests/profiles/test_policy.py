"""Plain-pytest tests for the ModeSelectionPolicy Protocol and PROFILE_POLICIES registry
(E2, ADR-0017)."""

from unittest.mock import patch

import pytest

from custom_components.smart_charging.const import (
    MODE_CAPTAR,
    MODE_OFF,
    PROFILE_AUTO,
    PROFILE_MANUAL,
)
from custom_components.smart_charging.profiles.auto import AutoPolicy, select_mode
from custom_components.smart_charging.profiles.manual import ManualPolicy
from custom_components.smart_charging.profiles.policy import PROFILE_POLICIES, ModeSelectionPolicy


def test_registry_has_exactly_the_two_built_in_profiles():
    """ADR-0017 Decision: no new key namespace -- the existing PROFILE_MANUAL/PROFILE_AUTO
    constants are the only registry keys."""
    assert set(PROFILE_POLICIES) == {PROFILE_MANUAL, PROFILE_AUTO}


def test_registry_manual_entry_is_a_manual_policy():
    assert isinstance(PROFILE_POLICIES[PROFILE_MANUAL], ManualPolicy)


def test_registry_auto_entry_is_an_auto_policy():
    assert isinstance(PROFILE_POLICIES[PROFILE_AUTO], AutoPolicy)


def test_both_registry_entries_satisfy_the_mode_selection_policy_protocol():
    """Protocol conformance, proven against the Protocol itself (not just against each
    other's concrete class) -- only possible because ModeSelectionPolicy is
    @runtime_checkable, matching adapters/base.py's Adapter Protocol precedent. Note:
    @runtime_checkable isinstance() only checks that a `select` attribute exists, not its
    signature or behavior -- the registry's Manual entry is behaviorally exercised
    separately below (test_registry_manual_entry_actually_selects)."""
    assert isinstance(PROFILE_POLICIES[PROFILE_MANUAL], ModeSelectionPolicy)
    assert isinstance(PROFILE_POLICIES[PROFILE_AUTO], ModeSelectionPolicy)


def test_registry_manual_entry_actually_selects():
    """Closes the gap the note above flags: isinstance() alone can't tell a real
    pass-through from an empty stub, so this calls the registered instance and checks the
    resulting behavior (resolution-rules.md: "Manual needs no table", R16)."""
    assert PROFILE_POLICIES[PROFILE_MANUAL].select(active_mode=MODE_OFF) == MODE_OFF


_AUTO_ROWS = [
    # Same five representative rows as tests/profiles/test_auto.py's own table coverage.
    dict(
        soc=80.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF, MODE_CAPTAR}),
        urgent=False,
        solar_capability_present=True,
        sun_is_up=False,
        solar_surplus_sufficient=False,
        sun_is_down=True,
        low_tariff_active=True,
        solar_reserve_active=False,
    ),  # row 1: Off
    dict(
        soc=50.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF, MODE_CAPTAR}),
        urgent=True,
        solar_capability_present=True,
        sun_is_up=False,
        solar_surplus_sufficient=False,
        sun_is_down=True,
        low_tariff_active=True,
        solar_reserve_active=False,
    ),  # row 2: Captar (urgent)
    dict(
        soc=50.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF, MODE_CAPTAR}),
        urgent=False,
        solar_capability_present=True,
        sun_is_up=True,
        solar_surplus_sufficient=True,
        sun_is_down=False,
        low_tariff_active=True,
        solar_reserve_active=False,
    ),  # row 3: Solar
    dict(
        soc=50.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF, MODE_CAPTAR}),
        urgent=False,
        solar_capability_present=True,
        sun_is_up=False,
        solar_surplus_sufficient=False,
        sun_is_down=True,
        low_tariff_active=True,
        solar_reserve_active=False,
    ),  # row 4: Captar (overnight top-up)
    dict(
        soc=50.0,
        active_soc_limit=80.0,
        available_modes=frozenset({MODE_OFF}),
        urgent=False,
        solar_capability_present=True,
        sun_is_up=False,
        solar_surplus_sufficient=False,
        sun_is_down=False,
        low_tariff_active=False,
        solar_reserve_active=False,
    ),  # row 5: Off (otherwise)
]


@pytest.mark.parametrize("kwargs", _AUTO_ROWS)
def test_auto_policy_matches_select_mode_across_every_table_row(kwargs):
    """AutoPolicy must not re-implement resolution-rules.md's table -- checked across all
    five representative rows, not just one, so a re-implementation that happens to agree on
    a single input can't slip through."""
    assert AutoPolicy().select(**kwargs) == select_mode(**kwargs)


def test_auto_policy_actually_calls_select_mode():
    """Proves genuine delegation (a call, not just an equal result) -- a re-implementation
    that duplicated the table would pass every _AUTO_ROWS case above without ever calling
    the real select_mode."""
    with patch(
        "custom_components.smart_charging.profiles.auto.select_mode",
        wraps=select_mode,
    ) as spy:
        AutoPolicy().select(**_AUTO_ROWS[0])
        spy.assert_called_once_with(**_AUTO_ROWS[0])
