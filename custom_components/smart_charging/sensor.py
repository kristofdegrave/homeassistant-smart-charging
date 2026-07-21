"""Charging status sensor (Fault/OK, ADR-0007), active-mode diagnostic sensor, and the
peak-protection diagnostic sensors (C3)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODE_OFF
from .entity import SmartChargingEntity


class ChargingStatusSensor(SmartChargingEntity, CoordinatorEntity, SensorEntity):
    """Reports Fault when the last cycle faulted (ADR-0007), else OK."""

    _attr_translation_key = "status"

    def __init__(self, entry_id: str, coordinator) -> None:
        SmartChargingEntity.__init__(self, entry_id)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{entry_id}_status"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if data is not None and getattr(data, "fault", False):
            return "Fault"
        return "OK"


class ActiveModeSensor(SmartChargingEntity, CoordinatorEntity, SensorEntity):
    """Reports the resolved active mode from the last cycle (Task 4.3, plan §5.1)."""

    _attr_translation_key = "active_mode"

    def __init__(self, entry_id: str, coordinator) -> None:
        SmartChargingEntity.__init__(self, entry_id)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{entry_id}_active_mode"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if data is not None:
            return getattr(data, "active_mode", MODE_OFF)
        return MODE_OFF


class MonthlyPeakSensor(SmartChargingEntity, RestoreEntity, SensorEntity):
    """Diagnostic: the coordinator's tracked monthly peak, kW (C3). Restoring this
    sensor's prior value + `period_month` attribute seeds the coordinator's
    Peak-Demand Tracker across a restart instead of it starting cold at 0 kW
    (design doc Sec 6.4's persistence note)."""

    _attr_translation_key = "monthly_peak_kw"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, entry_id: str, coordinator) -> None:
        super().__init__(entry_id)
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_monthly_peak_kw"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = float(last.state)
            month = last.attributes.get("period_month")
            if month is not None:
                self._coordinator._peak_tracked_month = tuple(month)
            self._coordinator._peak_tracked_kw = self._attr_native_value
            self._coordinator._peak_window = (self._attr_native_value,)
        self._attr_extra_state_attributes = {
            "period_month": getattr(self._coordinator, "_peak_tracked_month", None)
        }

    @property
    def native_value(self) -> float:
        data = self._coordinator.data
        if data is not None:
            return getattr(data, "monthly_peak_kw", self._attr_native_value)
        return self._attr_native_value


class EffectivePeakLimitSensor(SmartChargingEntity, CoordinatorEntity, SensorEntity):
    """Diagnostic: resolve_effective_peak_limit(monthly_peak_kw, max_peak_kw), kW (C3).
    No restore needed -- recomputed from MonthlyPeakSensor's own restored value on the
    first post-restart cycle."""

    _attr_translation_key = "effective_peak_limit"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, entry_id: str, coordinator) -> None:
        SmartChargingEntity.__init__(self, entry_id)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{entry_id}_effective_peak_limit"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is not None:
            return getattr(data, "effective_peak_limit_kw", None)
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            ChargingStatusSensor(entry.entry_id, coordinator),
            ActiveModeSensor(entry.entry_id, coordinator),
            MonthlyPeakSensor(entry.entry_id, coordinator),
            EffectivePeakLimitSensor(entry.entry_id, coordinator),
        ]
    )
