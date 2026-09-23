"""HA-harness tests for the home-day flag switch (R9, R13, NF14)."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_fire_time_changed,
)

from custom_components.smart_charging.const import (
    ATTR_APPLIES_TO,
    DOMAIN,
    LABEL_SC_RUNTIME,
    OWNED_SUFFIX_HOME_DAY,
)
from custom_components.smart_charging.switch import HomeDaySwitch
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states


async def test_defaults_off(hass):
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    assert entity.is_on is False
    await entity.async_remove()


async def test_user_can_turn_on_and_off(hass):
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert entity.is_on is True

    await entity.async_turn_off()
    assert entity.is_on is False
    await entity.async_remove()


async def test_resets_to_off_at_local_midnight(hass, freezer):
    """R13: the switch always shows TOMORROW's flag -- once tomorrow's date rolls over to
    become today, `is_on` (freshly derived from `_applies_to`, NF14) is naturally False again
    for the NEW tomorrow, with no explicit reset needed."""
    freezer.move_to(dt_util.now())  # anchor the freezer at "now" before moving it forward
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()
    assert entity.is_on is True

    midnight = dt_util.start_of_local_day() + timedelta(days=1)
    freezer.move_to(midnight)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert entity.is_on is False
    await entity.async_remove()


async def test_flag_set_for_today_survives_into_the_new_tomorrow(hass, freezer):
    """NF14/R13's last acceptance criterion: a flag set on date D (bound to D+1) still
    applies to D+1 once D+1 itself becomes "today" -- the midnight rollover that resets the
    switch's own `is_on` display for the new tomorrow must not disturb the date already
    bound and in force."""
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    await entity.async_turn_on()  # binds 2026-01-18
    bound_date = dt_util.now().date() + timedelta(days=1)

    # freezer.move_to takes a UTC instant; this harness's local zone is US/Pacific (UTC-8 in
    # January), so 08:30 UTC is 00:30 local -- bound_date has now begun.
    freezer.move_to("2026-01-18 08:30:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert entity.is_on is False  # the NEW tomorrow (01-19) is unset
    assert bound_date in entity._applies_to  # but 01-18's own binding is untouched
    await entity.async_remove()


async def test_turning_on_again_for_the_new_tomorrow_does_not_clear_todays_binding(hass, freezer):
    """The two-dates-at-once case NF14 requires: today's flag (set the evening before) and
    tomorrow's flag (being set again right now, e.g. by the evening prompt) are independent
    entries in `_applies_to`."""
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 01-18

    freezer.move_to("2026-01-18 20:00:00")  # 01-18 is now today
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    await entity.async_turn_on()  # binds 01-19, must not disturb 01-18

    assert entity._applies_to == {date(2026, 1, 18), date(2026, 1, 19)}
    await entity.async_remove()


async def test_turning_off_only_cancels_tomorrows_not_yet_begun_binding(hass, freezer):
    """Turning the switch off always targets "tomorrow" (today+1) -- it must never remove an
    already-begun (today's) entry, since the switch has no way to address that date at all."""
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 01-18

    freezer.move_to("2026-01-18 20:00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    await entity.async_turn_on()  # binds 01-19 too

    await entity.async_turn_off()  # cancels 01-19 only

    assert entity._applies_to == {date(2026, 1, 18)}
    await entity.async_remove()


async def test_restores_bound_dates_across_a_restart(hass, freezer):
    """NF14: `HomeDaySwitch` restores via `RestoreEntity`'s extra restore data, unlike the
    prior "daily flag, not a persisted preference" design -- a restart must not clear the
    date(s) the flag is bound to."""
    assert issubclass(HomeDaySwitch, RestoreEntity)
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 01-18
    stored = entity.extra_restore_state_data
    assert stored.applies_to == ["2026-01-18"]
    await entity.async_remove()


async def test_restore_drops_a_date_already_in_the_past(hass, freezer):
    """A date carried in extra restore data that has already ended by the time HA restarts
    (e.g. HA was stopped for several days) is dropped rather than kept forever -- R14 only
    ever resolves today's or tomorrow's deadline, so nothing would ever query it again."""
    freezer.move_to("2026-01-20 12:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")

    class _Restored(ExtraStoredData):
        def as_dict(self):
            return {ATTR_APPLIES_TO: ["2026-01-10", "2026-01-21"]}  # one past, one future

    with patch.object(entity, "async_get_last_extra_data", AsyncMock(return_value=_Restored())):
        await platform.async_add_entities([entity])

    assert entity._applies_to == {date(2026, 1, 21)}
    await entity.async_remove()


async def test_restart_spanning_the_home_days_end_still_applies_on_restart_day(hass, freezer):
    """NF14's named scenario: HA is stopped the evening the flag was set (bound to
    tomorrow) and restarted the NEXT day, after the bound date has already begun -- the
    flag must still apply to that day once restored, exactly as it would have without the
    restart, and the switch's own `is_on` (tomorrow's slot) must be freshly unset again."""
    freezer.move_to("2026-01-17 20:00:00")
    bound_date = date(2026, 1, 18)

    class _Restored(ExtraStoredData):
        def as_dict(self):
            return {ATTR_APPLIES_TO: [bound_date.isoformat()]}

    # HA restarts the NEXT day, well after the bound date has begun.
    freezer.move_to("2026-01-18 09:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    with patch.object(entity, "async_get_last_extra_data", AsyncMock(return_value=_Restored())):
        await platform.async_add_entities([entity])

    assert bound_date in entity._applies_to  # still bound, applies exactly as it would have
    assert entity.is_on is False  # tomorrow (01-19) is a fresh, unset slot
    await entity.async_remove()


def test_init_seeds_unique_id():
    entity = HomeDaySwitch(entry_id="abc")
    assert entity.unique_id == "abc_home_day"


async def test_home_day_switch_carries_runtime_label_after_setup(hass):
    """ADR-0028 (T3.1): HomeDaySwitch's label sync moves to a setup-time sync_labels call in
    async_setup_entry, replacing the async_added_to_hass hook -- a pure mechanism move, no
    capability gating (this entity is never conditional). This currently passes via the
    still-active hook alone (T3.1 doesn't delete it -- that's T3.4's job), so it isn't a
    red-then-green test in the usual TDD sense; it's the regression guard the plan's own
    build-order note calls for, proving the label still ends up correct once the setup-time
    call site exists, so T3.4 can safely delete the hook later without this test needing to
    change at all."""
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_HOME_DAY}"
    )
    assert entity_id is not None
    entry_reg = registry.async_get(entity_id)
    assert entry_reg.labels == {LABEL_SC_RUNTIME}
    # T3.1's scope is mechanism-only -- this entity is never capability-gated, unlike
    # SolarSurplusSensor/SmartChargingDepartureTime. Pin that explicitly, not just by omission.
    assert entry_reg.disabled_by is None
