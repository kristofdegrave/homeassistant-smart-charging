"""Structural purity guard for engines/modes/profiles (issue #503).

ADR-0010 (engines package) and the engine/mode-purity boundary (ADR-0006/0009) rest on
"no ``homeassistant.*`` import under ``engines/``, ``modes/``, or ``profiles/``" holding
true -- ADR-0009 relies on exactly that boundary to unit-test this logic with plain
pytest, no HA harness. Until now that guarantee was enforced only by convention and
manual review. This test walks the three package directories, parses each module with
``ast`` (never imports it -- importing would require mocking all of HA, which is exactly
what ADR-0009's plain-pytest tier avoids), and asserts no import statement names the
``homeassistant`` package, making the ADR self-enforcing.

Scope is deliberately the three directories issue #503 names. ``coordinator_cycle.py``,
``notification_state.py``, and ``const.py`` are also HA-free today (ADR-0012/0013) but
are root-level modules, not one of the three packages -- extending this guard to
individual root files is a natural follow-up, tracked separately rather than folded in
here silently.

Known limits, deliberately out of scope for this guard:

- It only catches *direct* ``homeassistant.*`` imports, not transitive coupling (e.g. a
  mode importing ``..coordinator`` or ``..adapters.factory``, which would drag HA in
  without naming it). No such import exists in these packages today.
- Dynamic imports (``importlib.import_module("homeassistant.core")``, ``__import__``)
  are invisible to a static AST walk. Nobody does this in pure logic today.
- A ``TYPE_CHECKING``-guarded HA import (``if TYPE_CHECKING: from homeassistant.core
  import HomeAssistant``) *is* flagged -- ``ast.walk`` descends into every branch. That
  strictness is intentional: a pure module has no business naming an HA type at all,
  guarded or not.

Plain pytest, no HA harness needed (ADR-0009) -- this test module itself must stay
HA-free, the same rule it enforces on its subjects.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "smart_charging"

# The three package directories ADR-0006/0009/0010 require to stay HA-free.
_PURE_PACKAGE_DIRS = ("engines", "modes", "profiles")

_FORBIDDEN_ROOT = "homeassistant"


def _iter_python_files(package_dir: Path) -> Iterator[Path]:
    """Yield every ``.py`` file under ``package_dir``, skipping ``__pycache__``."""
    for path in sorted(package_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _offenders_in_source(source: str) -> list[str]:
    """Return the offending import names/module paths in ``source``, if any.

    Catches ``import homeassistant``, ``import homeassistant.foo as x``, and
    ``from homeassistant.foo import bar`` -- anything whose root package is
    ``homeassistant`` -- including one nested inside a function, class, or
    ``if TYPE_CHECKING:`` block (``ast.walk`` covers the whole tree, not just top-level
    statements). Relative imports (``from . import x``, ``from .. import y``,
    ``level > 0``) are never flagged: their ``module`` is either ``None`` or a
    same-package name, never ``homeassistant``. A bare ``from . import *`` is likewise
    safe since it isn't rooted at ``homeassistant`` either. A lookalike name (e.g.
    ``import homeassistant_extras``) is not flagged: matching is on the exact first
    dotted component, not a substring/prefix check.
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == _FORBIDDEN_ROOT:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 means a relative import (from . import x / from .. import y);
            # node.module is None for a bare "from . import x", so guard before splitting.
            if node.level == 0 and node.module and node.module.split(".")[0] == _FORBIDDEN_ROOT:
                offenders.append(node.module)
    return offenders


def _homeassistant_imports(path: Path) -> list[str]:
    """Return the offending import names/module paths found in the file at ``path``."""
    # utf-8-sig tolerates a UTF-8 BOM (some files in this repo have one) without
    # ast.parse choking on a stray leading U+FEFF.
    return _offenders_in_source(path.read_text(encoding="utf-8-sig"))


def test_engines_modes_profiles_never_import_homeassistant():
    """No module under engines/, modes/, or profiles/ imports ``homeassistant.*``.

    This is the structural guarantee ADR-0006 ("no engine performs Home Assistant /
    adapter I/O"), ADR-0009 (plain-pytest tier for this logic), and ADR-0010 (the
    engines/ package's purity boundary) all depend on. A regression here means one of
    those ADRs' load-bearing assumption silently stopped holding.
    """
    violations: dict[str, list[str]] = {}
    scanned = 0

    for package_name in _PURE_PACKAGE_DIRS:
        package_dir = COMPONENT_DIR / package_name
        assert package_dir.is_dir(), f"expected package directory {package_dir} to exist"

        for path in _iter_python_files(package_dir):
            scanned += 1
            offenders = _homeassistant_imports(path)
            if offenders:
                violations[str(path.relative_to(COMPONENT_DIR))] = offenders

    # Guard against a vacuous pass: if the glob/skip logic (or a future package move)
    # ever silently yielded zero files, the assertion below would pass having checked
    # nothing. `__init__.py` alone in each of the three directories means this floor
    # can never legitimately drop below 3.
    assert scanned >= 3, f"expected to scan at least 3 files, only found {scanned}"

    assert not violations, (
        "found homeassistant.* imports under engines/modes/profiles, violating the "
        f"ADR-0006/0009/0010 purity boundary: {violations}"
    )


def test_purity_detector_flags_direct_homeassistant_imports():
    """Positive self-test: the detector actually catches every import form it claims to.

    Proves the detection logic works by construction, rather than only by inspection --
    if a future refactor of ``_offenders_in_source`` regresses, this fails independently
    of whether any real file happens to violate the rule yet.
    """
    bad_sources = [
        "import homeassistant\n",
        "import homeassistant.core\n",
        "import homeassistant.helpers.entity as ha_entity\n",
        "from homeassistant.core import HomeAssistant\n",
        "from homeassistant import config_entries\n",
        # Nested inside a function body and a TYPE_CHECKING guard -- ast.walk must
        # still find these, not just top-level statements.
        "def f():\n    import homeassistant.core\n",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from homeassistant.core import HomeAssistant\n",
    ]
    for source in bad_sources:
        assert _offenders_in_source(source), f"expected a violation to be flagged in: {source!r}"


def test_purity_detector_ignores_benign_imports():
    """Positive self-test: the detector never flags relative imports or lookalike names."""
    benign_sources = [
        "from . import cycle_invariant\n",
        "from .. import const\n",
        "from .foo import *\n",
        "import homeassistant_extras\n",
        "from homeassistant_extras import helper\n",
        "from __future__ import annotations\nimport math\nfrom dataclasses import dataclass\n",
    ]
    for source in benign_sources:
        assert not _offenders_in_source(source), f"expected no violation flagged in: {source!r}"
