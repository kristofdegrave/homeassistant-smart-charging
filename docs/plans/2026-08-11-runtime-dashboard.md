# TDD plan: runtime dashboard (C5, #601)

Derived from `docs/plans/2026-08-11-runtime-dashboard-design.md`. Branch: `feature/runtime-dashboard`.
Test boundary throughout: HA harness (ADR-0009) — every task touches `entity.py`, a platform file,
`dashboard.py`, or `__init__.py`, none of it `modes/`/`engines/`.

## T1 — `sc_runtime` label constant + `SmartChargingEntity` label-application mechanism

- Add `LABEL_SC_RUNTIME = "sc_runtime"` to `const.py`.
- Failing test (`tests/test_entity.py`, new file if none exists — check first): a minimal
  `SmartChargingEntity` subclass with `_owned_labels = frozenset({LABEL_SC_RUNTIME})`, added to
  hass via a `MockConfigEntry`, ends up with `sc_runtime` in
  `entity_registry.async_get(hass).async_get(entity_id).labels` after `async_added_to_hass` fires.
  A second subclass with the default `_owned_labels = frozenset()` ends up with no labels.
- Add `_owned_labels: frozenset[str] = frozenset()` and `async_added_to_hass(self) -> None` to
  `SmartChargingEntity` (`entity.py`): if `self._owned_labels`, call
  `er.async_get(self.hass).async_update_entity(self.entity_id, labels=self._owned_labels)`.
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
- Green, commit: `feat: label every runtime-classified owned entity sc_runtime (#601)`.

## T3 — `dashboard.py`: `build_dashboard_config`

- Failing test (`tests/test_dashboard.py`, new file): given a `MockConfigEntry` with
  `CONF_EV_SOC_ENTITY`/`CONF_SOLAR_FORECAST_ENTITY` set, `build_dashboard_config(entry)` returns a
  dict whose *Charging status* grid cards list exactly the seven tile entities the design doc
  names (in the entry's mapped `ev_soc` id, not a placeholder), *Power flow* has two tiles plus a
  `markdown` card, and *Runtime settings* is a single `custom:auto-entities` card filtered by
  `label: sc_runtime` only (assert the `exclude` clause the 2026-07-08 doc sketched is **absent** —
  a regression guard for the deliberate deviation the design doc records).
- Failing test: with `CONF_SOLAR_FORECAST_ENTITY` unset (solar capability off), the `markdown`
  card is omitted — assert `len(power_flow_cards) == 2`.
- Add `dashboard.py` with `build_dashboard_config(entry: ConfigEntry) -> dict`, `DASHBOARD_URL_PATH
  = "smart-charging"`, `DASHBOARD_FILENAME = "dashboard_generated.yaml"` (constants can live in
  `dashboard.py` itself — nothing outside this module and its tests references them).
- Green, commit: `feat: build runtime dashboard Lovelace config (#601)`.

## T4 — `dashboard.py`: register/unregister against `hass.data[LOVELACE_DATA]`

- Failing test (`tests/test_dashboard.py`): after `await async_register_dashboard(hass, entry)`,
  `hass.data[lovelace.LOVELACE_DATA].dashboards[DASHBOARD_URL_PATH]` is a `LovelaceYAML` instance,
  a panel is registered at that url_path (assert via `hass.data["frontend_panels"]` or the
  equivalent HA-harness-visible registry — check current core test helpers for the idiomatic
  assertion), and the file at `Path(dashboard.__file__).parent / DASHBOARD_FILENAME` exists and
  parses as YAML matching `build_dashboard_config(entry)`.
- Failing test: calling `async_register_dashboard` a second time (simulating reload) does not
  raise and does not create a duplicate panel entry.
- Failing test: `await async_unregister_dashboard(hass, entry)` removes the panel and the
  `dashboards[DASHBOARD_URL_PATH]` entry, and does not raise if called when nothing was registered
  (mirrors `frontend.async_remove_panel`'s own `warn_if_unknown` tolerance).
- Add `async_register_dashboard`/`async_unregister_dashboard` per the design doc's table, using
  `frontend.async_register_built_in_panel(..., update=<url_path already present>)` and
  `frontend.async_remove_panel(hass, url_path)` — attribute access on `LOVELACE_DATA`
  (`.dashboards[...]`), never the deprecated subscript form (see design doc's Known internals
  dependency section).
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
  from the same entities instead, per ADR-0022's Consequences.
- Commit: `docs: note the runtime dashboard is regenerated on reload (#601)`.

## T7 — Integration checkpoint

- Failing test (`tests/test_init.py`): one end-to-end test — full `MockConfigEntry` setup, then:
  every entity_id in T2's runtime set carries `sc_runtime`; no diagnostic/status entity does; the
  panel is registered at `DASHBOARD_URL_PATH` with `config["mode"] == "yaml"`; a second
  `async_setup_entry` call (simulating an ADR-0008 reload) does not raise and leaves exactly one
  panel registered; unloading removes it cleanly.
- No new implementation expected — this task only exists to catch an integration seam T1–T5's
  per-task tests miss. If it fails, the fix belongs to whichever task actually owns the gap; commit
  the fix there, not here.
- Green, commit: `test: runtime dashboard integration checkpoint (#601)`.
