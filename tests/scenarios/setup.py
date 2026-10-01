"""Shared scenario-setup plumbing every tier builds its own `_setup` from (epic #996), so a
later tier reuses this rather than reaching into an earlier tier's private names."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_charging.const import DOMAIN


async def setup_coordinator(hass, *, entry_data: dict, entry_options: dict, mode: str):
    """Set up a config entry from `entry_data`/`entry_options` and select `mode` through the
    real `select.select_option` service -- never a raw state write (`seed_owned_entity`): a raw
    write is not what a real user action produces, and the mode select is a real, polled
    (`should_poll=True`) entity whose own poll would otherwise contend with a re-seed. Returns
    the entry's coordinator."""
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data, options=entry_options)
    entry.add_to_hass(hass)
    if not await hass.config_entries.async_setup(entry.entry_id):
        # A bare `assert` here would raise AssertionError, which a caller's own
        # `xfail(strict=True, raises=InvariantViolation)` -- `InvariantViolation` subclasses
        # `AssertionError` -- would then swallow as though it were an expected invariant breach:
        # a setup failure must surface as something else entirely.
        raise RuntimeError(f"config entry {entry.entry_id} failed to set up")
    await hass.async_block_till_done()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.smart_charging_mode", "option": mode},
        blocking=True,
    )
    return entry.runtime_data.coordinator
