# TDD plan: config-value mirror diagnostic sensors (#888)

Derived from `docs/plans/2026-08-31-config-mirror-sensors-design.md`. Branch: `development/<issue>`
per task, filed once this plan lands. Test boundary named per task (design doc's Testing approach)
— T0–T4 and T6 are HA harness (ADR-0009); T5 is plain pytest (translation-file content, matching
`tests/test_translations.py`'s existing precedent).

## T0 — Expose `SmartChargingConfig` to platform files

- Failing test (`tests/test_init.py`): after `async_setup_entry`, `entry.runtime_data.config` is
  the same `SmartChargingConfig` instance passed to `SmartChargingCoordinator` (assert identity or
  field-for-field equality against a known-good entry).
- Add `config: SmartChargingConfig` to `SmartChargingRuntimeData` (`__init__.py`). Pass the
  already-constructed `config` local at the one `SmartChargingRuntimeData(...)` construction site
  (~`__init__.py:227`) — no new resolution, no second `SmartChargingConfig(...)` build.
- Green, commit: `refactor: expose SmartChargingConfig on runtime_data (#888)` (plumbing only, no
  user-visible behavior yet — the four pre-existing scalar fields stay, still read by `number.py`
  unchanged; de-duplicating them onto `config` is a follow-up, not this task).

## T1 — `_ConfigMirrorSensor` mechanism, proven on the four capabilities

- Failing test (`tests/test_sensor.py`): a `_ConfigMirrorSensor` built from a `_ConfigMirrorSpec`
  has `entity_category == EntityCategory.DIAGNOSTIC`, `entity_registry_enabled_default is False`,
  `unique_id == f"{entry_id}_{object_id_suffix}"`, `translation_key == object_id_suffix`, and
  `native_value == _format_mirror_value(spec.value)` for a **non-bool** spec value (e.g.
  `spec.value = 4.0` → `native_value == 4.0`) — pin this assertion to a non-bool value since
  `_format_mirror_value` changes a bool's representation (see next bullet), so `native_value ==
  spec.value` would be false for a bool spec.
- Add `_ConfigMirrorSpec` (frozen dataclass: `object_id_suffix`, `unit`, `device_class`, `value`)
  and `_ConfigMirrorSensor(SmartChargingEntity, SensorEntity)` to `sensor.py`, per the design doc's
  class shape. Add a module-level `_format_mirror_value(value: Any) -> Any` helper: `bool` →
  `STATE_ON`/`STATE_OFF` (`homeassistant.const`), else passthrough.
- Failing test (`tests/test_sensor.py`): `_format_mirror_value(True) == STATE_ON`,
  `_format_mirror_value(False) == STATE_OFF`, `_format_mirror_value(4.0) == 4.0` — the formatter in
  isolation, not just through a sensor.
- Failing test (`tests/test_sensor.py`): `async_setup_entry` registers
  `sensor.smart_charging_solar_available`/`captar_available`/`deadline_available`/
  `notifications_available` — the first two reading `entry.runtime_data.config.solar_available`/
  `.captar_available`, the last two reading `entry.data.get(CONF_DEADLINE_AVAILABLE,
  DEFAULT_DEADLINE_AVAILABLE)`/`entry.data.get(CONF_NOTIFICATIONS_AVAILABLE,
  DEFAULT_NOTIFICATIONS_AVAILABLE)` — each `native_value` is `STATE_ON`/`STATE_OFF` matching the
  entry's actual data, for both an on-config and an off-config test entry (proves both source
  buckets and the bool formatter together).
- Add the 4-entry slice of the spec list to `async_setup_entry` and register the entities.
- Green, commit: `feat: add capability config-mirror sensors (ADR-0031, #888)`.

## T2 — Core/Installation/Charger/Peak protection mirrors (12 values)

- Failing test (`tests/test_sensor.py`, parametrized over the 12 entries): for each of
  `smoothing_window`, `grid_supply_ceiling_a` (reads `config.grid_ceiling_a`), `grid_safety_offset_a`,
  `nominal_voltage_v` (reads `config.nominal_voltage`), `min_current_a` (reads `config.min_current`),
  `max_current_a` (reads `config.max_current`), `safety_margin_w`, `max_peak_kw`, `peak_floor_kw`,
  `peak_grace_min`, `captar_cooldown_min`, `power_respect_peak` — the registered sensor's
  `unique_id`/`object_id` uses the **catalog's** id (not the `SmartChargingConfig` field name where
  they differ — the four renamed above), `native_value` matches the corresponding
  `SmartChargingConfig` field on a known-config test entry, unit/device_class match the design
  doc's mapping table. (`power_cooldown_min` is **not** in this task — see T4, it is not a
  `SmartChargingConfig` field.)
- Extend the spec list in `async_setup_entry` with these 12 entries (values resolved from
  `entry.runtime_data.config`, per the mapping table — note the four field-name-vs-catalog-id
  divergences above).
- Green, commit: `feat: add installation/charger/peak config-mirror sensors (ADR-0031, #888)`.

## T3 — EV + Solar mirrors (13 values)

- Failing test (`tests/test_sensor.py`, parametrized over the 13 entries): for each of
  `ev_battery_capacity_kwh`, `solar_start_threshold_w`, `solar_hold_min`, `solar_cooldown_min`,
  `solar_restart_debounce_min`, `solar_only_start_threshold_w`, `solar_only_hold_min`,
  `solar_only_rounding_strategy` (reads `config.solar_only_strategy`),
  `solar_only_rounding_midpoint_pct` (reads `config.solar_only_midpoint`), `max_solar_soc`,
  `solar_step_pp`, `solar_step_threshold_pp`, `solar_forecast_threshold_kwh` — same assertions as
  T2 (unique_id/object_id per catalog id, `native_value`, unit/device_class).
- Extend the spec list with these 13 entries.
- Green, commit: `feat: add EV/solar config-mirror sensors (ADR-0031, #888)`.

## T4 — Power mode + Notification mirrors (6 values) — proves the third source bucket

- Failing test (`tests/test_sensor.py`): `power_cooldown_min`, `reminder_lead_h`,
  `deadline_notice_enabled`, `plug_in_reminder_enabled` each read `entry.options.get(CONF_X,
  DEFAULT_X)` directly (not `entry.runtime_data.config`, which has none of these four fields) —
  assert with a test entry whose `options` value differs from the `DEFAULT_*` constant, so the
  assertion would fail if the sensor silently fell back to the default instead of reading the
  entry. `evening_prompt_enabled`/`evening_prompt_time` read
  `entry.runtime_data.config.evening_prompt_enabled`/`.evening_prompt_time` as usual (these two
  **are** `SmartChargingConfig` fields).
- Extend the spec list with these 6 entries.
- Green, commit: `feat: add power-mode/notification config-mirror sensors (ADR-0031, #888)`.

## T5 — Translations

- Failing test (`tests/test_translations.py`, plain pytest — extends the existing
  `test_every_entity_translation_key_has_a_name`-style guard rather than adding a separate check):
  every `object_id_suffix` in the (by now complete, 35-entry) spec list has a matching
  `entity.sensor.<suffix>.name` key in `strings.json`. `test_nl_json_has_the_same_keys_as_en_json`
  (already in the suite) then covers the Dutch half without a new assertion.
- Add `entity.sensor.<object_id_suffix>.name` for all 35 values to `strings.json`,
  `translations/en.json`, `translations/nl.json` — Dutch names matching the existing nine sensors'
  translation style.
- Green (`pytest tests/test_translations.py`), `ruff check .`, `ruff format --check .`, and a
  manual read-through for the Dutch wording.
- Commit: `feat: translate config-mirror sensor names (ADR-0031, #888)`.

## T6 — Integration checkpoint

- Failing test (`tests/test_sensor.py` or a config-entry setup test): `async_setup_entry` registers
  all 35 `_ConfigMirrorSensor` entities plus the existing 9 with no duplicate `unique_id` and no
  duplicate `_object_id_suffix` (ADR-0013) across all 44 sensors; every one of the 35 has
  `entity_registry_enabled_default is False`, `entity_category == EntityCategory.DIAGNOSTIC`, and
  `_owned_labels == frozenset()` (no `LABEL_SC_RUNTIME` — ADR-0031's "never on the runtime
  dashboard" claim, checked structurally, not by omission).
- Failing test (`tests/test_init.py` or `tests/test_sensor.py`): reload behavior — set up an entry,
  change an options value one of the 35 mirrors (e.g. `CONF_MAX_CURRENT`), trigger the options
  reload (ADR-0008), and assert the enabled mirror sensor's `native_value` reflects the *new* value,
  not the one from the entry's first setup. This is the one realistic failure mode of a
  "resolved-once" sensor and needs its own explicit coverage, not just an assumption from T0–T5.
- Full HA-harness suite green (`pytest tests/`), `ruff check .`, `ruff format --check .`.
- Report status; this closes #888 and, once its own build tasks (filed against this plan) land,
  epic #883.
