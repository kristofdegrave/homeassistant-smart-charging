# TDD plan: runtime dashboard (C5, #601)

Derived from `docs/plans/2026-08-11-runtime-dashboard-design.md`. Branch: `feature/runtime-dashboard`.
Test boundary throughout: HA harness (ADR-0009) — every task touches `entity.py`, a platform file,
`dashboard.py`, `manifest.json`, or `__init__.py`, none of it `modes/`/`engines/`.

## T0 — `lovelace` manifest dependency + `sc_runtime` label-registry entry

- Add `"dependencies": ["lovelace"]` to `manifest.json`.
- Failing test (`tests/test_init.py`): after a full `MockConfigEntry` setup,
  `lr.async_get(hass).async_get_label_by_name("sc_runtime")` (or equivalent) returns a real
  `LabelEntry`. A second setup (reload) does not raise (idempotent create-if-missing).
- In `async_setup_entry`, before platform forwarding, create the `LABEL_SC_RUNTIME` label registry
  entry if it doesn't already exist (`homeassistant.helpers.label_registry`).
- Add `LABEL_SC_RUNTIME = "sc_runtime"` to `const.py`.
- Green, commit: `feat: declare lovelace dependency and create the sc_runtime label (#601)`.

## T1 — `SmartChargingEntity` label-application mechanism

- Failing test (`tests/test_entity_labels.py`, new file, HA harness — `tests/test_entity.py` stays
  plain-pytest, per the design doc's Testing section): a minimal `SmartChargingEntity` subclass with
  `_owned_labels = frozenset({LABEL_SC_RUNTIME})`, added to hass via a `MockConfigEntry`, ends up
  with `sc_runtime` in `entity_registry.async_get(hass).async_get(entity_id).labels` after
  `async_added_to_hass` fires. A second subclass with the default `_owned_labels = frozenset()` ends
  up with no labels.
- Failing test: a subclass that also mixes in `RestoreEntity` still has its restored state
  round-trip correctly (regression guard for the `super().async_added_to_hass()` delegation — this
  is the test that would have caught issue #1 in the impl-spec-reviewer's Critical findings).
- Failing test: an entity that already carries a user-added label (seed one directly via
  `er.async_update_entity` before the entity is added) keeps that label alongside `sc_runtime` after
  `async_added_to_hass` fires — regression guard for the merge-not-replace fix.
- Add `_owned_labels: frozenset[str] = frozenset()` and
  `async def async_added_to_hass(self) -> None` to `SmartChargingEntity` (`entity.py`) — **must**
  call `await super().async_added_to_hass()` first, then merge
  (`entry.labels | self._owned_labels`), never assign the bare set. See the design doc's code block
  for the exact shape.
- Green, commit: `feat: add sc_runtime label-application mechanism to SmartChargingEntity (#601)`.

## T2 — Apply `_owned_labels` to every runtime-classified owned entity class

- Failing test (`tests/test_init.py`, extending the existing full-setup fixture): after a full
  `MockConfigEntry` setup, every entity_id in `{select.smart_charging_mode,
  select.smart_charging_profile, number.smart_charging_target_current,
  number.smart_charging_soc_limit_override, switch.smart_charging_home_day,
  time.smart_charging_departure_mon...sun, time.smart_charging_departure_holiday,
  time.smart_charging_departure_home_day}` (14 entities) carries `sc_runtime`; every other owned
  entity_id (the diagnostic/status sensors) carries no labels.
- Set `_owned_labels = frozenset({LABEL_SC_RUNTIME})` on: `select.py`'s mode/profile select
  classes, `number.py`'s target-current/soc-limit-override classes, `switch.py`'s home-day switch
  class, `time.py`'s `SmartChargingDepartureTime` (class-level default covers all nine instances).
  **Disclosed deviation:** the nine departure-time entities are labelled as `time.py` creates them
  today — unconditionally, regardless of the `deadline_available` capability (a pre-existing C2 gap,
  not introduced or fixed by this task; R19 AC4 is not fully satisfied for them until that gap is
  closed under its own issue).
- Green, commit: `feat: label every runtime-classified owned entity sc_runtime (#601)`.

## T3 — `dashboard.py`: `build_dashboard_config`

- Add `DASHBOARD_URL_PATH = "smart-charging"`, `DASHBOARD_FILENAME = "dashboard_generated.yaml"`,
  `DASHBOARD_ICON = "mdi:ev-station"` to `const.py` (single home for every dashboard constant,
  alongside `LABEL_SC_RUNTIME` from T0 — `dashboard.py` imports them).
- Failing test (`tests/test_dashboard.py`, new file): given a `MockConfigEntry` with
  `CONF_CHARGER_STATUS_ENTITY`/`CONF_CHARGER_CURRENT_ENTITY`/`CONF_NET_POWER_ENTITY` (required,
  always set) and `CONF_EV_SOC_ENTITY`/`CONF_SOLAR_FORECAST_ENTITY` (optional, set for this case),
  `build_dashboard_config(entry)` returns a dict whose *Charging status* grid has exactly the seven
  tiles the design doc's corrected table names (charger status via `CONF_CHARGER_STATUS_ENTITY`,
  **not** `sensor.smart_charging_status`; `sensor.smart_charging_active_mode`, **not**
  `select.smart_charging_mode`), *Power flow* has four tiles (`CONF_CHARGER_CURRENT_ENTITY`,
  `CONF_NET_POWER_ENTITY`, `solar_surplus_w`, `effective_peak_limit`) plus a `markdown` card, and
  *Runtime settings* is a single `custom:auto-entities` card filtered by `label: sc_runtime` only
  (assert the `exclude` clause the 2026-07-08 doc sketched is **absent** — a regression guard for
  the deliberate deviation the design doc records).
- Failing test: with `CONF_SOLAR_FORECAST_ENTITY` unset (solar capability off), the `markdown` card
  is omitted — assert `len(power_flow_cards) == 4`.
- Failing test: with `CONF_EV_SOC_ENTITY` unset (neither solar nor CapTar configured), the battery
  tile is omitted — assert `len(charging_status_cards) == 6` and no card references a `None`
  entity id (regression guard for the `KeyError`/broken-tile finding).
- Add `dashboard.py` with `build_dashboard_config(entry: ConfigEntry) -> dict`.
- Green, commit: `feat: build runtime dashboard Lovelace config (#601)`.

## T4 — `dashboard.py`: register/unregister against `hass.data[LOVELACE_DATA]`

- Failing test (`tests/test_dashboard.py`; call `await async_setup_component(hass, "lovelace", {})`
  first, per T0's manifest dependency): after `await async_register_dashboard(hass, entry)`,
  `hass.data[lovelace.LOVELACE_DATA].dashboards[DASHBOARD_URL_PATH]` is a `LovelaceYAML` instance
  whose `.path` resolves to the absolute path under the integration's own package directory (assert
  this explicitly — the regression guard for the `hass.config.path()` finding); a panel is
  registered at that url_path with `sidebar_title="Smart Charging"` and `show_in_sidebar=True`
  (assert via `hass.data[frontend.DATA_PANELS][DASHBOARD_URL_PATH]`, not a hand-typed magic string);
  and the file at that path exists (written via `hass.async_add_executor_job`, not a direct
  synchronous write — the HA harness's blocking-call guard is the regression guard for this) and
  parses as YAML matching `build_dashboard_config(entry)`.
- Failing test: calling `async_register_dashboard` a second time (simulating reload) does not raise
  and does not create a duplicate panel entry (`update=True` on the second call).
- Failing test: `await async_unregister_dashboard(hass, entry)` removes the panel and the
  `dashboards[DASHBOARD_URL_PATH]` entry, and does not raise if called when nothing was registered
  (mirrors `frontend.async_remove_panel`'s own `warn_if_unknown` tolerance).
- Add `async_register_dashboard`/`async_unregister_dashboard` per the design doc's Known internals
  dependency section — the `LovelaceYAML` `config` dict carries `CONF_MODE`/`CONF_FILENAME`
  (absolute)/`CONF_TITLE`/`CONF_ICON`/`CONF_REQUIRE_ADMIN`/`CONF_SHOW_IN_SIDEBAR`; the panel-register
  call passes `sidebar_title`/`sidebar_icon`/`show_in_sidebar`/`require_admin` as direct keyword
  arguments, using `lovelace.DOMAIN`/`frontend.DATA_PANELS` (never a bare `"lovelace"` string or a
  hand-typed `hass.data` key).
- Green, commit: `feat: register/unregister the runtime dashboard panel (#601)`.

## T5 — Wire into `__init__.py`

- Failing test (`tests/test_init.py`): a full `MockConfigEntry` setup registers the dashboard panel
  (assert via the T4 helper); unloading the entry removes it.
- Call `await async_register_dashboard(hass, entry)` at the end of `async_setup_entry` (after
  platform forwarding); call `await async_unregister_dashboard(hass, entry)` in
  `async_unload_entry`.
- Green, commit: `feat: register the runtime dashboard on setup/unload (#601)`.

## T6 — README packaging note

- No test (documentation-only). Add one paragraph to `README.md` explaining the dashboard is
  regenerated on every reload (edits to it don't persist) and how to build an ordinary dashboard
  from the same entities instead, per ADR-0022's Consequences — **and** naming `custom:auto-entities`
  (HACS) as a required prerequisite, since the *Runtime settings* section renders as a broken card
  without it.
- Commit: `docs: note the runtime dashboard is regenerated on reload (#601)`.

## T7 — Integration checkpoint

- Failing test (`tests/test_init.py`): one end-to-end test — full `MockConfigEntry` setup, then:
  every entity_id in T2's runtime set carries `sc_runtime`; no diagnostic/status entity does; the
  panel is registered at `DASHBOARD_URL_PATH` with `config["mode"] == "yaml"` and is visible in the
  sidebar; then `await hass.config_entries.async_reload(entry.entry_id)` (the actual ADR-0008
  reload — unload then setup, **not** a second bare `async_setup_entry` call, since
  `manifest.json`'s `single_config_entry: true` makes that unrepresentative) does not raise and
  leaves exactly one panel registered; unloading removes it cleanly.
- No new implementation expected — this task only exists to catch an integration seam T0–T5's
  per-task tests miss. If it fails, the fix belongs to whichever task actually owns the gap; commit
  the fix there, not here.
- Green, commit: `test: runtime dashboard integration checkpoint (#601)`.
