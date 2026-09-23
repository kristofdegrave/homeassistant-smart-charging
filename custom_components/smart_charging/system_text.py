"""NF8's system-language text: dashboard headings and notification texts.

Both surfaces are composed by this integration itself, not by an entity's own name or the
config flow (which the viewing user's language governs instead, R20) -- NF8 AC2 puts them
under Home Assistant's *system* language, `hass.config.language`, including after that
language changes. This is the mechanism HA already exposes for backend-composed text
(`homeassistant.helpers.translation.async_get_translations`, the same loader entity names and
the config flow use) -- no new mechanism, per the ha-integration-knowledge skill.

The values themselves live in strings.json's `common` category (mirrored in
translations/en.json and translations/nl.json) rather than under `entity`/`config`/`options`:
those three are the only categories hassfest's strings.json schema recognises for entity names
and config-flow steps (script/hassfest/translations.py's `gen_strings_schema`), and neither
shape fits a dashboard heading or a notification message. `common` is that schema's flat
slug-keyed bucket for exactly this kind of string.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import DOMAIN, TRANSLATION_CATEGORY_COMMON

_PREFIX = f"component.{DOMAIN}.{TRANSLATION_CATEGORY_COMMON}."


async def async_get_system_text(hass: HomeAssistant) -> dict[str, str]:
    """Return this integration's `common`-category strings for HA's *system* language.

    Keyed by the bare slug strings.json's `common` block uses (the `KEY_*` constants in
    const.py) -- callers never see the `component.smart_charging.common.` prefix
    `async_get_translations` returns internally. English is HA's own built-in fallback for
    any key missing from the target language (`_TranslationCache._async_load`), so a caller
    always gets every key the English copy defines.
    """
    raw = await async_get_translations(
        hass, hass.config.language, TRANSLATION_CATEGORY_COMMON, integrations=[DOMAIN]
    )
    return {key.removeprefix(_PREFIX): value for key, value in raw.items()}
