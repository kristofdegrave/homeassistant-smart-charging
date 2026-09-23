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


async def test_should_return_english_text_when_the_system_language_is_english(hass):
    # Arrange -- the `hass` fixture's default system language is English.

    # Act
    text = await async_get_system_text(hass)

    # Assert
    assert text[KEY_DASHBOARD_SECTION_CHARGING_STATUS] == "Charging status"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_YES] == "Yes"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_NO] == "No"


async def test_should_return_dutch_text_when_the_system_language_is_dutch(hass):
    # Arrange
    hass.config.language = "nl"

    # Act
    text = await async_get_system_text(hass)

    # Assert
    assert text[KEY_DASHBOARD_SECTION_CHARGING_STATUS] == "Laadstatus"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_YES] == "Ja"
    assert text[KEY_NOTIFICATION_HOME_DAY_ACTION_NO] == "Nee"


async def test_should_return_english_text_when_the_system_language_is_neither_english_nor_dutch(
    hass,
):
    """NF8 AC2: any language other than Dutch shows English."""
    # Arrange
    hass.config.language = "fr"

    # Act
    text = await async_get_system_text(hass)

    # Assert
    assert text[KEY_DASHBOARD_SECTION_CHARGING_STATUS] == "Charging status"


async def test_should_strip_the_component_prefix_when_returning_keys(hass):
    """`async_get_translations` returns `component.smart_charging.common.<slug>` keys
    internally -- callers here compare against the bare `KEY_*` slug instead. Asserting a
    known key is present (not just the absence of a prefix) keeps this test from passing
    against an `async_get_system_text` that always returned `{}`."""
    # Act
    text = await async_get_system_text(hass)

    # Assert
    assert KEY_DASHBOARD_SECTION_CHARGING_STATUS in text
    assert not any(key.startswith("component.") for key in text)
