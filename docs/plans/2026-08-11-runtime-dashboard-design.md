# Runtime dashboard — implementation design (C5, UC11)

*Date: 2026-08-11 · Issue: #601 · Epic: #549*

## Scope

This is the last remaining item of Phase 4 (`docs/design/project-plan.md`'s C5 — "Runtime
dashboard (UC11)"). It builds the concrete Client that ships the dashboard
[`2026-07-08-runtime-dashboard-design.md`](2026-07-08-runtime-dashboard-design.md) (card types,
layout, the `sc_runtime`-label extensibility mechanism) decided, delivered exactly as
[ADR-0022](../adl/0022-runtime-dashboard-delivery-mechanism.md) decided (Option C — a locked,
YAML-mode dashboard, regenerated and re-registered on every `async_setup_entry`).

C5 depends on C2 (owned control entities), C3 (diagnostic entities), and RA1 (adapter role → real
entity mapping) — all already merged. This spec adds no new config-flow surface, no new Manager/
Engine call, and no change to `docs/design/system-design.md`'s classification of UC11 as "Client,
no service of its own": it only builds the dashboard-generation Client itself.

### Two prerequisite gaps this spec must close before the dashboard can be built

Both were deferred by the 2026-07-08 design doc as "out of scope for this doc" / "implementation-
time" work, and neither has landed yet — confirmed by grep against `custom_components/`:

1. **No entity is labelled `sc_runtime` today.** Decision 1 of the 2026-07-08 doc requires every
   runtime-classified owned entity to carry that label "applied when the integration creates it" —
   this is the mechanism the dashboard's `auto-entities` card depends on, and it does not exist in
   code yet. T1–T2 below build it.
2. **`entity-catalog.md`'s runtime-entity ids are partly stale.** The catalog still lists
   `input_number.sc_power_target_current_a` (a pre-native-naming placeholder); the entity actually
   shipped in C2 is `number.smart_charging_target_current` (`OWNED_SUFFIX_TARGET_CURRENT`,
   `const.py:87`). This spec uses the real, current native id and files the catalog drift as a
   follow-up (see Deferrals) rather than fixing analysis-layer wording inline (out of this spec's
   authority per `write-impl-spec`'s "derive, don't design").

## Success criteria

- Every entity `entity-catalog.md` classifies `runtime` **and that currently exists as a native
  owned entity** carries the `sc_runtime` label from the moment it is added to the entity registry,
  with no dashboard-specific code touching that entity by id.
- A YAML-mode dashboard is registered at a fixed `url_path` on every `async_setup_entry`, and
  removed on `async_unload_entry`, matching every card/section
  [`2026-07-08-runtime-dashboard-design.md`](2026-07-08-runtime-dashboard-design.md)'s Layout
  section shows, using **real** current entity ids (not that doc's illustrative placeholders).
- A second `async_setup_entry` (reload, ADR-0008) neither raises nor leaves a stale panel/file —
  regeneration is idempotent.
- No install-time, config-data, or config-options value is ever labelled or shown (R19's exclusion
  criterion) — structurally true because none of those are entities to begin with (Decision 1's own
  reasoning), not because of a runtime filter this spec has to get right.

## Known internals dependency (confirmed, not inferred)

ADR-0022 already accepted the risk of depending on undocumented `lovelace`/`frontend` internals.
Concretely, as of the current HA core `dev` branch:

- `homeassistant.components.lovelace.dashboard.LovelaceYAML` is the class backing a `mode: yaml`
  dashboard; `homeassistant.components.lovelace.__init__.async_setup` builds these **exclusively**
  from `configuration.yaml`'s `lovelace: dashboards:` block at boot — there is no public API to add
  one afterward.
- The only way to register one at runtime is the same pattern several HACS dashboard-generator
  integrations already use (e.g. `ui_lovelace_minimalist`, `dwains-lovelace-dashboard`): insert a
  `LovelaceYAML` instance into `hass.data[lovelace.LOVELACE_DATA].dashboards[url_path]` directly,
  then call `homeassistant.components.frontend.async_register_built_in_panel(hass, "lovelace",
  frontend_url_path=url_path, config={"mode": "yaml"}, update=<True if already registered>)`.
  Teardown is `frontend.async_remove_panel(hass, url_path)` plus deleting the `dashboards[url_path]`
  entry.
- This exact surface has already broken across HA core releases for other integrations —
  `hass.data[LOVELACE_DATA]` changed from dict-subscript to attribute access, logged as deprecated
  today and removed entirely in HA 2026.2 (see
  [UI-Lovelace-Minimalist/UI#1610](https://github.com/UI-Lovelace-Minimalist/UI/issues/1610),
  [dwainscheeren/dwains-lovelace-dashboard#861](https://github.com/dwainscheeren/dwains-lovelace-dashboard/issues/861)).

This confirms ADR-0022's Con was not hypothetical. This spec isolates all of this behind one module
(`dashboard.py`, below) so a future HA-core break is a one-file fix, and pins the attribute-access
form (not the deprecated subscript form) since that is what current/near-future core requires.

## Control flow

### New module: `custom_components/smart_charging/dashboard.py`

| Function | Responsibility |
| --- | --- |
| `build_dashboard_config(entry: ConfigEntry) -> dict` | Pure(-ish) builder: returns the `sections` Lovelace config dict (Python dict, not YAML text) for the fixed *Charging status* / *Power flow* tiles plus the label-driven `auto-entities` *Runtime settings* card. Reads only `entry.data` (for `CONF_EV_SOC_ENTITY` / `CONF_SOLAR_FORECAST_ENTITY` — the two Decision-4 tiles that point at a user-mapped upstream entity, not a `smart_charging_` id) and fixed native ids (everything else) — no coordinator/Store access, no HA state reads. |
| `async_register_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None` | Serializes `build_dashboard_config(entry)` to YAML, writes it to `Path(__file__).parent / DASHBOARD_FILENAME` (the integration's own package directory, ADR-0022), and registers/updates the `LovelaceYAML`/panel pair at `DASHBOARD_URL_PATH`, per the Known internals dependency section. `update=True` whenever the url_path is already present (idempotent on reload). |
| `async_unregister_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None` | Removes the panel and the `dashboards[url_path]` entry. Does **not** delete the generated YAML file (deleting a file HA's frontend may still be reading mid-teardown is an unforced risk; the next `async_register_dashboard` overwrites it unconditionally anyway). |

`DASHBOARD_URL_PATH = "smart-charging"`, `DASHBOARD_FILENAME = "dashboard_generated.yaml"` — new
constants in `const.py`.

### Wiring into `__init__.py`

- `async_setup_entry`: after platform forwarding (entities must exist in the registry before the
  dashboard references them — order doesn't affect correctness since Lovelace resolves entity ids
  lazily at render time, but matches the natural "entities first, then the thing that displays them"
  reading order), call `await async_register_dashboard(hass, entry)`.
- `async_unload_entry`: call `async_unregister_dashboard(hass, entry)` before/alongside the existing
  platform-unload call.

### Label application: `entity.py`

- New class attribute on `SmartChargingEntity`: `_owned_labels: frozenset[str] = frozenset()`
  (default: no labels — every diagnostic/state-only owned entity, e.g. `ChargingStatusSensor`,
  `MonthlyPeakSensor`, keeps this default and is therefore structurally never `sc_runtime`-labelled,
  matching Decision 1's "install-time/diagnostic entities are never labelled" reasoning extended to
  the diagnostic set too).
- Runtime-classified owned entity classes set `_owned_labels = frozenset({LABEL_SC_RUNTIME})`:
  `select.py`'s `ModeSelect`/`ProfileSelect`, `number.py`'s `TargetCurrentNumber`/
  `SocLimitOverrideNumber`, `switch.py`'s `HomeDaySwitch`, `time.py`'s
  `SmartChargingDepartureTime` (all nine departure-time instances — a class-level default covers
  every instance regardless of which `id_suffix` it was constructed with).
- `SmartChargingEntity.async_added_to_hass(self) -> None` (new override): once `self.entity_id` is
  assigned by the platform, if `self._owned_labels`, call
  `er.async_get(self.hass).async_update_entity(self.entity_id, labels=self._owned_labels)`. This
  runs once per entity, every setup (including reload) — idempotent, since re-applying the same
  label set is a no-op in the entity registry.
- `LABEL_SC_RUNTIME = "sc_runtime"` — new constant in `const.py`.

This keeps the label mechanism a property of the entity class (declared once, next to the id
suffix), not a separate list `dashboard.py` has to keep in sync — the same "one place owns the
fact" discipline `entity.py`'s existing `_object_id_suffix`/`unique_id` derivation already follows.

## Entities mapped to sections (real current ids, replacing the 2026-07-08 doc's placeholders)

| Section | Card | Entities (native ids) |
| --- | --- | --- |
| Charging status | `tile` × 7 | `sensor.smart_charging_status`, `entry.data[CONF_EV_SOC_ENTITY]` (battery level — user-mapped, may be absent if never configured), `select.smart_charging_profile`, `select.smart_charging_mode`, `sensor.smart_charging_active_soc_limit`, `sensor.smart_charging_time_to_full`, `sensor.smart_charging_peak_headroom_a` |
| Power flow | `tile` × 2, `markdown` × 1 (conditional) | `sensor.smart_charging_solar_surplus_w`, `sensor.smart_charging_effective_peak_limit`; the solar-forecast `markdown` card is included only when `entry.data[CONF_SOLAR_FORECAST_ENTITY]` is set (mirrors the solar-capability gating `entity-catalog.md` already documents for `solar_reserve_soc`) |
| Runtime settings | `custom:auto-entities` | filtered by `label: sc_runtime` only — the 2026-07-08 doc's `exclude: label: sc_install` clause is dropped: per that doc's own Decision 1 reasoning, no entity is ever labelled `sc_install` (install-time values are config-data/options, not entities), so the exclude clause can never match anything; keeping it would be dead config with no test able to exercise it |

`charger_current` (Decision 2's status tile) has no dedicated native entity per `entity-catalog.md`
(it is an adapter role, write-only from the coordinator's side, per the #602 `ROLES_ADAPTER_READINGS_EXCLUDED`
finding) and `net_power` likewise has none — both are dropped from the fixed tile set rather than
invented; `solar_surplus_w`/`effective_peak_limit` already cover the "how's the power flow doing"
glance the 2026-07-08 doc wanted from them. `sensor.smart_charging_adapter_readings` is diagnostic
(ADR-0021, `entity_category: diagnostic`) and intentionally excluded from the dashboard — R19/UC11
ask for *charging status*, not an adapter-health readout; it remains visible in HA's own entities UI
like any other diagnostic entity.

`input_number.sc_power_target_current_a` / `sc_solar_reserve_soc` (entity-catalog.md's two
still-open legacy `sc_` runtime helpers) are excluded — they are not native owned entities today (the
Power target current is already native as `number.smart_charging_target_current`, included above;
the solar-reserve cap remains a config-option with no entity to label, an existing ADR-0004 open
question this spec does not resolve).

## Testing approach (ADR-0009)

`dashboard.py` imports `homeassistant.components.frontend`/`lovelace` directly → **HA harness**
(`tests/test_dashboard.py`), not plain pytest. Label application (`entity.py`'s
`async_added_to_hass` override) is entity/registry-level → HA harness (`tests/test_entity.py`,
extended). No `modes/`/`engines/` code changes.

Integration checkpoint (T7): a full `MockConfigEntry` setup registers the panel at
`DASHBOARD_URL_PATH` with `mode: yaml`, every runtime entity's registry entry carries
`sc_runtime`, no diagnostic/state entity does, and unloading removes the panel without error; a
second setup (simulating reload) does not raise and does not duplicate the panel.

## Packaging

- README gets one paragraph (per ADR-0022's Consequences) explaining the dashboard is regenerated
  on every reload, so in-place edits to it don't persist, and how to build a separate ordinary
  dashboard from the same entities instead.
- No `strings.json`/translation changes — the dashboard's own card titles are static English text
  inside the generated YAML (Lovelace card titles are not part of HA's translation system), matching
  how every other dashboard-building HACS integration ships them.

## Deferrals

- **`entity-catalog.md`'s stale `input_number.sc_power_target_current_a` row** — the real native id
  is `number.smart_charging_target_current`; filed as a follow-up analysis-layer correction, not
  fixed inline here (this spec derives from current code, not the stale row, per `write-impl-spec`'s
  scope).
- **The `sc_solar_reserve_soc` open ADR-0004 question** (still a config-option, not an entity) is
  unchanged by this spec; the dashboard simply cannot show it as a runtime entity until that
  question resolves.
- **Mushroom cards, tablet-specific sizing** — already deferred by the 2026-07-08 design doc; nothing
  here reopens either.
- **Deleting the generated YAML file on unload** — deliberately not done (see `dashboard.py` table);
  revisit only if a concrete problem (stale file confusing a manual inspection) is reported.

## Requirements / use-cases realized

- [R19](../analysis/requirements.md#r19--runtime-dashboard), [UC11](../analysis/use-cases/UC11-monitor-and-manage-charging-configuration.md) — via the concrete build above.
- [ADR-0022](../adl/0022-runtime-dashboard-delivery-mechanism.md) — the delivery mechanism this spec implements.
