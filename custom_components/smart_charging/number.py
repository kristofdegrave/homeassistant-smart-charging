"""Target-current number entity (C2). ADR-0004 native naming."""

from __future__ import annotations

from homeassistant.components.number import RestoreNumber
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SmartChargingConfigEntry
from .const import (
    OWNED_SUFFIX_SOC_LIMIT_OVERRIDE,
    OWNED_SUFFIX_TARGET_CURRENT,
    SOC_LIMIT_OVERRIDE_MAX,
    SOC_LIMIT_OVERRIDE_MIN,
)
from .entity import SmartChargingEntity


class _RestoreClampedNumberMixin:
    """Shared restore + set body for number entities that restore their last value on
    `async_added_to_hass`, clamped to `[_attr_native_min_value, _attr_native_max_value]`.
    Must appear before `RestoreNumber` in a subclass's bases so its
    `async_added_to_hass` override's `super()` call resolves onward to
    `RestoreEntity.async_added_to_hass` (the actual restore-state read)."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = min(
                max(last.native_value, self._attr_native_min_value),
                self._attr_native_max_value,
            )

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()


class TargetCurrentNumber(SmartChargingEntity, _RestoreClampedNumberMixin, RestoreNumber):
    """User-set target charging current for Power mode."""

    _attr_translation_key = "target_current"
    _object_id_suffix = OWNED_SUFFIX_TARGET_CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_step = 1.0

    def __init__(self, entry_id: str, min_a: float, max_a: float, default: float) -> None:
        super().__init__(entry_id)
        self._attr_native_min_value = min_a
        self._attr_native_max_value = max_a
        # config_flow validates default_target_current with vol.Coerce(float) only, no
        # [min_a, max_a] range -- clamp here so an out-of-range configured default can't diverge
        # the entity's display from the coordinator's own (now also clamped) field (symmetric
        # with SocLimitOverrideNumber's SOC clamp fix).
        self._attr_native_value = min(max(default, min_a), max_a)


class SocLimitOverrideNumber(SmartChargingEntity, _RestoreClampedNumberMixin, RestoreNumber):
    """Runtime "Default charge limit" (R6/R7): the car charges up to this SOC% unless
    a solar step-up or the overnight solar-reserve cap is temporarily raising/lowering it."""

    _attr_translation_key = "soc_limit_override"
    _object_id_suffix = OWNED_SUFFIX_SOC_LIMIT_OVERRIDE
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 1.0
    _attr_native_min_value = SOC_LIMIT_OVERRIDE_MIN
    _attr_native_max_value = SOC_LIMIT_OVERRIDE_MAX

    def __init__(self, entry_id: str, default: float) -> None:
        super().__init__(entry_id)
        # config_flow validates default_soc_limit with vol.Coerce(float) only, no 50-100 range --
        # clamp here the same way async_added_to_hass already clamps a restored value, so an
        # out-of-range configured default can't diverge the entity's display from the coordinator's
        # own (now also clamped) field.
        self._attr_native_value = min(max(default, SOC_LIMIT_OVERRIDE_MIN), SOC_LIMIT_OVERRIDE_MAX)


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartChargingConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime_data = entry.runtime_data
    async_add_entities(
        [
            TargetCurrentNumber(
                entry_id=entry.entry_id,
                min_a=runtime_data.min_current,
                max_a=runtime_data.max_current,
                default=runtime_data.default_target_current,
            ),
            SocLimitOverrideNumber(
                entry_id=entry.entry_id,
                default=runtime_data.default_soc_limit,
            ),
        ]
    )
