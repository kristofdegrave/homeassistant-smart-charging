"""Shared phase vocabulary for the mode engines (E1).

Not an Engine of its own -- a pure utility, like `_amp_step.py`, that keeps the
phase names consistent across `modes/solar.py` and `modes/solar_only.py` (and any
later mode engine with the same Idle/Charging/[Hold]/Cooldown shape, e.g. UC03's
`Captar`) without coupling their state-machine logic together (NF2): each module
still defines its own valid subset and its own transition rules -- only the names
are shared. `SocReached` is deliberately absent -- see `modes/solar.py`'s module
docstring for why that phase is the coordinator's responsibility, not a mode's.

`DEBOUNCING` (R11, issue #757) is a `Solar`/`SolarOnly`-only sub-state of `Idle`: once
the has-charged flag is set for the connection, a start-threshold crossing while
dwelling in `Idle` must hold for the restart-debounce period before charging actually
starts. `Captar`/`Power` never use it -- their own start conditions aren't derived
from a fluctuating sensor reading, so there is nothing to debounce (R11).
"""

from enum import StrEnum


class Phase(StrEnum):
    IDLE = "idle"
    CHARGING = "charging"
    HOLD = "hold"
    COOLDOWN = "cooldown"
    DEBOUNCING = "debouncing"
