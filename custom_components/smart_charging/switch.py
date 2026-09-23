"""Home-day flag switch (C2, R9/R13). New `switch.py` platform.

Bound to the calendar date it was set for (R13's last acceptance criterion, NF14): a flag set
on date D applies to D+1 alone, until D+1 ends at local midnight, and survives a restart and a
reload still bound to that date however long the system was stopped. That is why this entity
restores via `RestoreEntity` -- every other runtime-configuration entity already does
(`select.py`, `number.py`, `time.py`); this one previously did not, silently clearing the flag
on every restart or options-change reload.

A plain on/off restore cannot carry which date the flag is bound to, so the state itself is
derived, not restored: `_applies_to` holds the set of dates the flag currently applies to (at
most two at once -- today's, set the evening before and still in force until midnight, and
tomorrow's, being set again right now by the switch or the evening prompt's "yes") and is what
actually round-trips through `RestoreEntity`'s extra restore data. `is_on` and the `applies_to`
attribute are both computed from it fresh on every read, so no separately-tracked boolean can
fall out of sync with it, and "tomorrow" simply stops being what it used to be the moment the
date rolls over, without disturbing today's own (now separately dated) entry -- no mutation is
needed for that half of it. `_applies_to` DOES still need pruning of dates that have fully
elapsed, though: nothing else ever removes one (R14 only ever resolves today's or tomorrow's
deadline, so a past date is simply never queried again, not cleaned up by being queried), and
without pruning it would grow by one entry per home day for as long as the switch runs without
a restart. `_async_refresh_at_midnight` does both jobs at the one moment both are due: it drops
any date that has ended, and it writes state so HA's state machine -- which only shows a new
value once something calls `async_write_ha_state()` -- actually shows the `is_on`/`applies_to`
value that was already true the instant the date rolled over, rather than keeping yesterday's
"on" displayed until some unrelated write happens to touch it (R13's "reads off from midnight
as before").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from . import SmartChargingConfigEntry
from .adapters.store import parse_iso_dates
from .const import ATTR_APPLIES_TO, LABEL_SC_RUNTIME, OWNED_SUFFIX_HOME_DAY
from .entity import SmartChargingEntity, sync_labels


@dataclass
class _HomeDayExtraStoredData(ExtraStoredData):
    """The extra-restore-data round trip for `_applies_to`: a list of ISO ("YYYY-MM-DD")
    date strings, `ATTR_APPLIES_TO`-keyed to match the live `extra_state_attributes` value."""

    applies_to: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {ATTR_APPLIES_TO: self.applies_to}

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> _HomeDayExtraStoredData | None:
        applies_to = restored.get(ATTR_APPLIES_TO)
        if not isinstance(applies_to, list):
            return None
        return cls(applies_to)


class HomeDaySwitch(SmartChargingEntity, RestoreEntity, SwitchEntity):
    """User-set "home day" flag (R9's solar-reserve trigger, one of R13's configured
    mechanisms). Always shows and sets TOMORROW's flag (R13): turning it on binds
    "today + 1 day", at the moment of the call, into `_applies_to` -- so a flag set through
    the evening prompt's "yes" or a write through the Store (both of which resolve to a
    `switch.turn_on` service call, ADR-0018) binds exactly the same way as the switch's own
    UI toggle. See the module docstring for why `_applies_to` and not a plain on/off bool
    is what this entity actually persists.
    """

    _attr_translation_key = "home_day"
    _object_id_suffix = OWNED_SUFFIX_HOME_DAY
    _owned_labels = frozenset({LABEL_SC_RUNTIME})

    def __init__(self, entry_id: str) -> None:
        super().__init__(entry_id)
        self._applies_to: set[date] = set()
        self._unsub_midnight_refresh: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_extra_data()
        if restored is not None:
            data = _HomeDayExtraStoredData.from_dict(restored.as_dict())
            if data is not None:
                # A date already in the past by the time HA restarts can never be resolved
                # against again (R14 only ever resolves today's or tomorrow's deadline) --
                # drop it rather than carrying it forever.
                today = dt_util.now().date()
                self._applies_to = {d for d in parse_iso_dates(data.applies_to) if d >= today}
        self._unsub_midnight_refresh = async_track_time_change(
            self.hass, self._async_refresh_at_midnight, hour=0, minute=0, second=0
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_midnight_refresh is not None:
            self._unsub_midnight_refresh()
            self._unsub_midnight_refresh = None
        await super().async_will_remove_from_hass()

    @callback
    def _async_refresh_at_midnight(self, now: datetime) -> None:
        """See the module docstring: drops any date that has fully elapsed (nothing else ever
        prunes `_applies_to`), then writes state so HA's state machine actually shows the
        `is_on`/`applies_to` value that was already true the instant the date rolled over."""
        today = dt_util.now().date()
        self._applies_to = {d for d in self._applies_to if d >= today}
        self.async_write_ha_state()

    @staticmethod
    def _tomorrow() -> date:
        return dt_util.now().date() + timedelta(days=1)

    @property
    def is_on(self) -> bool:
        return self._tomorrow() in self._applies_to

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        return {ATTR_APPLIES_TO: sorted(d.isoformat() for d in self._applies_to)}

    @property
    def extra_restore_state_data(self) -> _HomeDayExtraStoredData:
        return _HomeDayExtraStoredData(sorted(d.isoformat() for d in self._applies_to))

    async def async_turn_on(self, **kwargs) -> None:
        self._applies_to.add(self._tomorrow())
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._applies_to.discard(self._tomorrow())
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entity = HomeDaySwitch(entry_id=entry.entry_id)
    async_add_entities([entity])
    sync_labels(
        er.async_get(hass), Platform.SWITCH, entity.unique_id, owned_labels=entity._owned_labels
    )
