"""Charging status sensor (Fault/OK, ADR-0007), active-mode diagnostic sensor, and the
peak-protection diagnostic sensors (C3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorEntity, SensorExtraStoredData
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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


@dataclass
class _MonthlyPeakExtraStoredData(SensorExtraStoredData):
    """SensorExtraStoredData + `period_month` ("YYYY-MM", design doc Sec 6.4)."""

    period_month: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {**super().as_dict(), "period_month": self.period_month}

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> _MonthlyPeakExtraStoredData | None:
        base = SensorExtraStoredData.from_dict(restored)
        if base is None:
            return None
        return cls(base.native_value, base.native_unit_of_measurement, restored.get("period_month"))


class MonthlyPeakSensor(SmartChargingEntity, CoordinatorEntity, RestoreSensor):
    """Diagnostic: the coordinator's tracked monthly peak, kW (C3). Restoring this
    sensor's prior value + `period_month` attribute seeds the coordinator's
    Peak-Demand Tracker's `(tracked_kw, tracked_month)` across a restart instead of
    it starting cold at 0 kW (design doc Sec 6.4's persistence note) -- the 15-minute
    smoothing window itself is deliberately NOT seeded here; Sec 6.4 is explicit that
    it rebuilds from scratch post-restart, same as R10's own window."""

    _attr_translation_key = "monthly_peak_kw"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, entry_id: str, coordinator) -> None:
        SmartChargingEntity.__init__(self, entry_id)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{entry_id}_monthly_peak_kw"
        self._attr_native_value = 0.0

    @property
    def extra_restore_state_data(self) -> _MonthlyPeakExtraStoredData:
        month = getattr(self.coordinator, "_peak_tracked_month", None)
        period_month = f"{month[0]:04d}-{month[1]:02d}" if month else None
        return _MonthlyPeakExtraStoredData(
            self.native_value, self.native_unit_of_measurement, period_month
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = await self.async_get_last_extra_data()
        if restored is None:
            return
        data = _MonthlyPeakExtraStoredData.from_dict(restored.as_dict())
        if data is None or data.native_value is None:
            return
        self._attr_native_value = float(data.native_value)
        self.coordinator._peak_tracked_kw = self._attr_native_value
        if data.period_month:
            year, month = (int(part) for part in data.period_month.split("-"))
            self.coordinator._peak_tracked_month = (year, month)

    @property
    def native_value(self) -> float:
        data = self.coordinator.data
        if data is not None:
            return getattr(data, "monthly_peak_kw", self._attr_native_value)
        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        month = getattr(self.coordinator, "_peak_tracked_month", None)
        return {"period_month": f"{month[0]:04d}-{month[1]:02d}" if month else None}


class EffectivePeakLimitSensor(SmartChargingEntity, CoordinatorEntity, SensorEntity):
    """Diagnostic: resolve_effective_peak_limit(monthly_peak_kw, max_peak_kw, urgent), kW (C3).
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
