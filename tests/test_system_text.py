"""Tests for NF8's system-language text loader (system_text.py).

Anchors: docs/analysis/requirements.md#nf8--english-and-dutch-throughout AC2 (Home
Assistant's system language, including after it changes).
"""

from custom_components.smart_charging.const import (
    KEY_DASHBOARD_SECTION_CHARGING_STATUS,
    KEY_NOTIFICATION_HOME_DAY_ACTION_NO,
    KEY_NOTIFICATION_HOME_DAY_ACTION_YES,
)
from custom_components.smart_charging.system_text import async_get_system_text


async def test_defaults_to_english_text(hass):
    text = await async_get_system_text(hass)

    assert text[KEY_DASHBOARD_SECTION_CHARGING_STATUS] == "Charging status"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_YES] == "Yes"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_NO] == "No"


async def test_reads_dutch_text_when_the_system_language_is_dutch(hass):
    hass.config.language = "nl"

    text = await async_get_system_text(hass)

    assert text[KEY_DASHBOARD_SECTION_CHARGING_STATUS] == "Laadstatus"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_YES] == "Ja"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_NO] == "Nee"


async def test_falls_back_to_english_for_any_other_language(hass):
    """NF8 AC2: any language other than Dutch shows English."""
    hass.config.language = "fr"

    text = await async_get_system_text(hass)

    assert text[KEY_DASHBOARD_SECTION_CHARGING_STATUS] == "Charging status"


async def test_keys_carry_no_component_prefix(hass):
    """`async_get_translations` returns `component.smart_charging.common.<slug>` keys
    internally -- callers here compare against the bare `KEY_*` slug instead."""
    text = await async_get_system_text(hass)

    assert all(not key.startswith("component.") for key in text)
