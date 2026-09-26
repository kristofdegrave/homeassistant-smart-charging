"""HA-harness tests for the home-day flag switch (R9, R13, NF14)."""

from datetime import date, timedelta

from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockEntityPlatform,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.smart_charging.const import (
    ATTR_APPLIES_TO,
    DOMAIN,
    LABEL_SC_RUNTIME,
    OWNED_SUFFIX_HOME_DAY,
)
from custom_components.smart_charging.switch import HomeDaySwitch
from tests.helpers import entry_data_base, entry_options_base, seed_charger_states

_ENTITY_ID = "switch.smart_charging_home_day"


def _applies_to_attr(hass):
    return hass.states.get(_ENTITY_ID).attributes[ATTR_APPLIES_TO]


async def test_should_default_to_off_when_never_set(hass):
    # Arrange
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")

    # Act
    await platform.async_add_entities([entity])

    # Assert
    assert entity.is_on is False
    await entity.async_remove()


async def test_should_turn_on_when_the_user_turns_it_on(hass):
    # Arrange
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])

    # Act
    await entity.async_turn_on()

    # Assert
    assert entity.is_on is True
    await entity.async_remove()


async def test_should_turn_off_when_the_user_turns_it_off(hass):
    # Arrange
    entity = HomeDaySwitch(entry_id="abc")
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()

    # Act
    await entity.async_turn_off()

    # Assert
    assert entity.is_on is False
    await entity.async_remove()


async def test_should_show_off_on_the_real_state_machine_when_local_midnight_passes(hass, freezer):
    """R13: the switch always shows TOMORROW's flag -- once tomorrow's date rolls over to
    become today, the real HA state (not just the live `is_on` property, which is recomputed
    from `dt_util.now()` on every read regardless of whether the midnight refresh ran) must
    show "off" again for the NEW tomorrow. Asserting the state machine, not the property, is
    what actually exercises `_async_refresh_at_midnight` -- deleting that callback would still
    leave a property-only assertion green."""
    # Arrange
    freezer.move_to(dt_util.now())  # anchor the freezer at "now" before moving it forward
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()
    assert hass.states.get(_ENTITY_ID).state == STATE_ON

    # Act
    midnight = dt_util.start_of_local_day() + timedelta(days=1)
    freezer.move_to(midnight)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    # Assert
    assert hass.states.get(_ENTITY_ID).state == STATE_OFF
    await entity.async_remove()


async def test_should_prune_an_elapsed_date_when_midnight_refresh_runs(hass, freezer):
    """The other half of `_async_refresh_at_midnight`, distinct from the display reset above:
    a date that has fully elapsed is dropped from `_applies_to`/`applies_to`, not just from
    the switch's own on/off display -- otherwise the set grows by one entry per home day for
    as long as the switch runs without a restart (the module docstring's own reasoning)."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 2026-01-18
    freezer.move_to("2026-01-18 08:30:00")  # 00:30 local on 01-18 -- 01-18 has begun, not ended
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _applies_to_attr(hass) == ["2026-01-18"]

    # Act
    freezer.move_to("2026-01-19 08:30:00")  # 00:30 local on 01-19 -- 01-18 has now fully ended
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    # Assert
    assert _applies_to_attr(hass) == []
    await entity.async_remove()


async def test_should_keep_a_flag_bound_to_today_when_midnight_rolls_the_new_tomorrow_over(
    hass, freezer
):
    """NF14/R13's last acceptance criterion: a flag set on date D (bound to D+1) still applies
    to D+1 once D+1 itself becomes "today" -- the midnight rollover that resets the switch's
    own display for the new tomorrow must not disturb the date already bound and in force."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 2026-01-18

    # Act
    # freezer.move_to takes a UTC instant; this harness's local zone is US/Pacific (UTC-8 in
    # January), so 08:30 UTC is 00:30 local -- 01-18 has now begun.
    freezer.move_to("2026-01-18 08:30:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    # Assert
    assert _applies_to_attr(hass) == ["2026-01-18"]  # 01-18's own binding is untouched
    await entity.async_remove()


async def test_should_reset_the_new_tomorrows_slot_to_unset_when_midnight_rolls_over(hass, freezer):
    """The other half of the same rollover: once the bound date has begun, the switch's own
    display goes back to unset for the (different) NEW tomorrow."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 2026-01-18
    assert hass.states.get(_ENTITY_ID).state == STATE_ON

    # Act
    freezer.move_to("2026-01-18 08:30:00")  # 00:30 local, per the note above
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    # Assert
    assert hass.states.get(_ENTITY_ID).state == STATE_OFF  # the NEW tomorrow (01-19) is unset
    await entity.async_remove()


async def test_should_add_a_new_binding_without_clearing_todays_when_turned_on_again(hass, freezer):
    """The two-dates-at-once case NF14 requires: today's flag (set the evening before) and
    tomorrow's flag (being set again right now, e.g. by the evening prompt) are independent
    entries in `_applies_to`."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 01-18
    freezer.move_to("2026-01-18 20:00:00")  # 01-18 is now today
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    # Act
    await entity.async_turn_on()  # binds 01-19, must not disturb 01-18

    # Assert
    assert _applies_to_attr(hass) == ["2026-01-18", "2026-01-19"]
    await entity.async_remove()


async def test_should_cancel_only_tomorrows_not_yet_begun_binding_when_turned_off(hass, freezer):
    """Turning the switch off always targets "tomorrow" (today+1) -- it must never remove an
    already-begun (today's) entry, since the switch has no way to address that date at all."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")
    await platform.async_add_entities([entity])
    await entity.async_turn_on()  # binds 01-18
    freezer.move_to("2026-01-18 20:00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    await entity.async_turn_on()  # binds 01-19 too

    # Act
    await entity.async_turn_off()  # cancels 01-19 only

    # Assert
    assert _applies_to_attr(hass) == ["2026-01-18"]
    await entity.async_remove()


async def test_should_restore_bound_dates_when_ha_restarts(hass):
    """NF14: `HomeDaySwitch` restores via `RestoreEntity`'s extra restore data, unlike the
    prior "daily flag, not a persisted preference" design -- a restart must not clear the
    date(s) the flag is bound to. Goes through HA's real entity_id-keyed restore cache
    (`mock_restore_cache_with_extra_data`), not a patched method, so it actually proves the
    restore wiring rather than only the parsing."""
    # Arrange
    far_future = (dt_util.now().date() + timedelta(days=30)).isoformat()
    mock_restore_cache_with_extra_data(
        hass, ((State(_ENTITY_ID, STATE_ON), {ATTR_APPLIES_TO: [far_future]}),)
    )
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")

    # Act
    await platform.async_add_entities([entity])

    # Assert
    assert _applies_to_attr(hass) == [far_future]
    await entity.async_remove()


async def test_should_drop_a_date_already_in_the_past_when_restoring(hass, freezer):
    """A date carried in extra restore data that has already ended by the time HA restarts
    (e.g. HA was stopped for several days) is dropped rather than kept forever -- R14 only
    ever resolves today's or tomorrow's deadline, so nothing would ever query it again."""
    # Arrange
    freezer.move_to("2026-01-20 12:00:00")
    mock_restore_cache_with_extra_data(
        hass,
        ((State(_ENTITY_ID, STATE_OFF), {ATTR_APPLIES_TO: ["2026-01-10", "2026-01-21"]}),),
    )
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")

    # Act
    await platform.async_add_entities([entity])

    # Assert
    assert _applies_to_attr(hass) == ["2026-01-21"]  # only the still-future date survives
    await entity.async_remove()


async def test_should_restore_no_dates_when_the_restored_applies_to_is_not_a_list(hass):
    """NF14: `_HomeDayExtraStoredData.from_dict`'s own malformed-input branch. A restored
    `ATTR_APPLIES_TO` that isn't a list at all (e.g. a corrupted store) is rejected outright,
    not merely handed to `parse_iso_dates` and hoped to come back empty -- a plain string
    would happen to parse to nothing either way (each character fails `date.fromisoformat`),
    which is why this uses a dict whose own keys are well-formed ISO dates: `parse_iso_dates`
    only iterates its argument, so without the `isinstance(applies_to, list)` guard those keys
    would sail through and populate `applies_to`, even though a dict is not a list. This test
    isolates the guard alone -- that restore itself actually runs (rather than never firing at
    all, which would leave the same empty result) is what
    `test_should_restore_bound_dates_when_ha_restarts` above proves, through a well-formed
    list."""
    # Arrange
    future_date = (dt_util.now().date() + timedelta(days=365)).isoformat()
    mock_restore_cache_with_extra_data(
        hass, ((State(_ENTITY_ID, STATE_OFF), {ATTR_APPLIES_TO: {future_date: True}}),)
    )
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")

    # Act
    await platform.async_add_entities([entity])

    # Assert
    assert _applies_to_attr(hass) == []
    await entity.async_remove()


async def test_should_still_apply_a_flag_when_a_restart_happens_after_its_date_has_begun(
    hass, freezer
):
    """NF14's named scenario: HA is stopped the evening the flag was set (bound to tomorrow)
    and restarted the NEXT day, after the bound date has already begun -- the flag must still
    apply to that day once restored, exactly as it would have without the restart."""
    # Arrange
    bound_date = date(2026, 1, 18)
    mock_restore_cache_with_extra_data(
        hass, ((State(_ENTITY_ID, STATE_OFF), {ATTR_APPLIES_TO: [bound_date.isoformat()]}),)
    )
    freezer.move_to("2026-01-18 09:00:00")  # local 01:00 on 01-18 -- the bound date has begun
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")

    # Act
    await platform.async_add_entities([entity])

    # Assert
    assert _applies_to_attr(hass) == [bound_date.isoformat()]
    await entity.async_remove()


async def test_should_no_longer_apply_a_flag_when_a_restart_spans_the_home_days_end(hass, freezer):
    """The other restart scenario NF14 names, distinct from the one above: a flag bound to
    date D survives being stopped WHILE D is still in force, but a restart that happens only
    AFTER D has fully ended (D+1 has begun) must not resurrect it -- "keeps it from carrying
    into a day it was not set for" (requirements.md NF14). A second, still-future date is
    restored alongside the ended one so the test can tell "restore ran and pruned D" apart
    from "restore never ran at all" (both would otherwise leave D absent)."""
    # Arrange
    ended_date = date(2026, 1, 18)
    still_future_date = date(2026, 1, 25)
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(_ENTITY_ID, STATE_OFF),
                {ATTR_APPLIES_TO: [ended_date.isoformat(), still_future_date.isoformat()]},
            ),
        ),
    )
    freezer.move_to("2026-01-19 09:00:00")  # local 01:00 on 01-19 -- 01-18 has fully ended
    entity = HomeDaySwitch(entry_id="abc")
    entity.entity_id = _ENTITY_ID
    platform = MockEntityPlatform(hass, domain="switch")

    # Act
    await platform.async_add_entities([entity])

    # Assert -- the ended date is gone, but the still-future one proves restore actually ran.
    assert _applies_to_attr(hass) == [still_future_date.isoformat()]
    await entity.async_remove()


async def test_should_keep_the_flag_on_when_the_config_entry_reloads(hass, freezer):
    """NF14's other named survival case, alongside a restart: an options-change reload must
    not clear the flag either. Goes through a real config-entry setup + `async_reload`, the
    same wiring `select.py`/`number.py`/`time.py`'s own ADR-0028 restore-across-reload tests
    use, rather than constructing the entity directly."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_HOME_DAY}"
    )
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_ON
    bound_date = (dt_util.now().date() + timedelta(days=1)).isoformat()
    assert hass.states.get(entity_id).attributes[ATTR_APPLIES_TO] == [bound_date]

    # Act
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # Assert
    assert hass.states.get(entity_id).state == STATE_ON
    assert hass.states.get(entity_id).attributes[ATTR_APPLIES_TO] == [bound_date]


async def test_should_apply_the_restored_flag_from_the_first_cycle_after_a_reload(hass, freezer):
    """NF14: "holds the value last set ... from the first control cycle that follows" -- the
    coordinator itself, not only the switch's own displayed state, must have picked up the
    restored/reloaded flag by the time its first post-reload cycle runs. Asserts on the state
    that reload's own first cycle produced, with no extra `async_refresh()` call of this
    test's own -- an extra refresh would still turn this green even if the reload wired the
    first cycle before the switch platform (and so before its restored flag) was in place."""
    # Arrange
    freezer.move_to("2026-01-17 20:00:00")
    seed_charger_states(hass, status="Charging")
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data_base(), options=entry_options_base())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{entry.entry_id}_{OWNED_SUFFIX_HOME_DAY}"
    )
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()
    bound_date = dt_util.now().date() + timedelta(days=1)

    # Act
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # Assert
    coordinator = entry.runtime_data.coordinator
    assert bound_date in coordinator.home_day_dates


def test_should_seed_the_unique_id_when_constructed():
    # Arrange / Act
    entity = HomeDaySwitch(entry_id="abc")

    # Assert
    assert entity.unique_id == "abc_home_day"


async def test_home_day_switch_carries_runtime_label_after_setup(hass):
    """ADR-0028 (T3.1): HomeDaySwitch's label sync moves to a setup-time sync_labels call in
    async_setup_entry, replacing the async_added_to_hass hook -- a pure mechanism move, no
    capability gating (this entity is never conditional). This currently passes via the
    still-active hook alone (T3.1 doesn't delete it -- that's T3.4's job), so it isn't a
    red-then-green test in the usual TDD sense; it is a regression guard, proving the label
    still ends up correct once the setup-time call site exists, so T3.4 can safely delete the
    hook later without this test needing to change at all."""
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
