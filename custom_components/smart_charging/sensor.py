"""Charging status sensor (Fault/OK, ADR-0007), active-mode diagnostic sensor, and the
peak-protection diagnostic sensors (C3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorEntity, SensorExtraStoredData
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    MODE_OFF,
    OWNED_SUFFIX_ACTIVE_SOC_LIMIT,
    OWNED_SUFFIX_PEAK_HEADROOM_A,
    OWNED_SUFFIX_SOLAR_SURPLUS_W,
    OWNED_SUFFIX_TIME_TO_FULL,
    STATUS_FAULT,
    STATUS_OK,
)
from .entity import SmartChargingEntity


class _CoordinatorPushMixin(SmartChargingEntity, CoordinatorEntity):
    """Base for every owned entity whose value the coordinator pushes each cycle
    (Task 4.3, C3), rather than the user setting/restoring it -- folds `SmartChargingEntity`
    and `CoordinatorEntity` into one shared `__init__` so subclasses only need their own
    when they have extra construction to do (`MonthlyPeakSensor`'s seed value)."""

    def __init__(self, entry_id: str, coordinator) -> None:
        SmartChargingEntity.__init__(self, entry_id)
        CoordinatorEntity.__init__(self, coordinator)


class _CoordinatorFieldSensor(_CoordinatorPushMixin, SensorEntity):
    """Declarative diagnostic sensor (issue #507): reads `_coordinator_field` off
    `coordinator.data` each cycle, falling back to `_field_default` when data is None or
    the field is absent. Covers the three diagnostic sensors with no bespoke restore or
    value-mapping logic of their own; `ChargingStatusSensor` (maps a bool to Fault/OK)
    and `MonthlyPeakSensor` (restore-seeded, falls back to its own last value) keep
    their own `native_value` and use `_CoordinatorPushMixin` directly instead."""

    _coordinator_field: str
    _field_default: Any = None

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data
        if data is not None:
            return getattr(data, self._coordinator_field, self._field_default)
        return self._field_default


class ChargingStatusSensor(_CoordinatorPushMixin, SensorEntity):
    """Reports Fault when the last cycle faulted (ADR-0007), else OK."""

    _attr_translation_key = "status"
    _object_id_suffix = "status"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        if data is not None and getattr(data, "fault", False):
            return STATUS_FAULT
        return STATUS_OK


class ActiveModeSensor(_CoordinatorFieldSensor):
    """Reports the resolved active mode from the last cycle (Task 4.3, plan §5.1)."""

    _attr_translation_key = "active_mode"
    _object_id_suffix = "active_mode"
    _coordinator_field = "active_mode"
    _field_default = MODE_OFF


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


class MonthlyPeakSensor(_CoordinatorPushMixin, RestoreSensor):
    """Diagnostic: the coordinator's tracked monthly peak, kW (C3). Restoring this
    sensor's prior value + `period_month` attribute seeds the coordinator's
    Peak-Demand Tracker's `(tracked_kw, tracked_month)` across a restart instead of
    it starting cold at 0 kW (design doc Sec 6.4's persistence note) -- the 15-minute
    smoothing window itself is deliberately NOT seeded here; Sec 6.4 is explicit that
    it rebuilds from scratch post-restart, same as R10's own window."""

    _attr_translation_key = "monthly_peak_kw"
    _object_id_suffix = "monthly_peak_kw"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, entry_id: str, coordinator) -> None:
        super().__init__(entry_id, coordinator)
        self._attr_native_value = 0.0

    @property
    def extra_restore_state_data(self) -> _MonthlyPeakExtraStoredData:
        return _MonthlyPeakExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self.coordinator.monthly_peak_period_month,
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
        month = None
        if data.period_month:
            try:
                year, month_num = (int(part) for part in data.period_month.split("-"))
                month = (year, month_num)
            except ValueError:
                pass  # malformed stored value -- restore the kW, leave tracked_month as-is
        self.coordinator.seed_monthly_peak(self._attr_native_value, month)

    @property
    def native_value(self) -> float:
        data = self.coordinator.data
        if data is not None:
            return getattr(data, "monthly_peak_kw", self._attr_native_value)
        return self._attr_native_value

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"period_month": self.coordinator.monthly_peak_period_month}


class EffectivePeakLimitSensor(_CoordinatorFieldSensor):
    """Diagnostic: resolve_effective_peak_limit(monthly_peak_kw, max_peak_kw, urgent), kW (C3).
    No restore needed -- recomputed from MonthlyPeakSensor's own restored value on the
    first post-restart cycle."""

    _attr_translation_key = "effective_peak_limit"
    _object_id_suffix = "effective_peak_limit"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _coordinator_field = "effective_peak_limit_kw"


class ActiveSocLimitSensor(_CoordinatorFieldSensor):
    """Diagnostic: the coordinator's resolved active SOC limit from the last cycle (R7).
    No restore needed -- recomputed each cycle from the SOC-limit-override/solar-reserve/
    solar-step-up three-row table (Task 5.1 wires the full resolution)."""

    _attr_translation_key = "active_soc_limit"
    _object_id_suffix = OWNED_SUFFIX_ACTIVE_SOC_LIMIT
    _coordinator_field = "active_soc_limit"


class SolarSurplusSensor(_CoordinatorFieldSensor):
    """Diagnostic: charger_power - net_power, raw (entity-catalog.md:151, #602)."""

    _attr_translation_key = "solar_surplus_w"
    _object_id_suffix = OWNED_SUFFIX_SOLAR_SURPLUS_W
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _coordinator_field = "solar_surplus_w"


class PeakHeadroomSensor(_CoordinatorFieldSensor):
    """Diagnostic: the R3 clamp's own headroom target, amps (entity-catalog.md:153, #602)."""

    _attr_translation_key = "peak_headroom_a"
    _object_id_suffix = OWNED_SUFFIX_PEAK_HEADROOM_A
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _coordinator_field = "peak_headroom_a"


class TimeToFullSensor(_CoordinatorFieldSensor):
    """Diagnostic: minutes to the active SOC limit at the current set-point
    (entity-catalog.md:152, #602)."""

    _attr_translation_key = "time_to_full"
    _object_id_suffix = OWNED_SUFFIX_TIME_TO_FULL
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _coordinator_field = "time_to_full_min"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        [
            ChargingStatusSensor(entry.entry_id, coordinator),
            ActiveModeSensor(entry.entry_id, coordinator),
            MonthlyPeakSensor(entry.entry_id, coordinator),
            EffectivePeakLimitSensor(entry.entry_id, coordinator),
            ActiveSocLimitSensor(entry.entry_id, coordinator),
            SolarSurplusSensor(entry.entry_id, coordinator),
            PeakHeadroomSensor(entry.entry_id, coordinator),
            TimeToFullSensor(entry.entry_id, coordinator),
        ]
    )
