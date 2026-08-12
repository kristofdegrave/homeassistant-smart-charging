# Runtime dashboard — implementation design (C5, UC11)

*Date: 2026-08-11 · Issue: #601 · Epic: #549*

## Scope

This is the last remaining item of Phase 4 (`docs/design/project-plan.md`'s C5 — "Runtime
dashboard (UC11)"). It builds the concrete Client that ships the dashboard
[`2026-07-08-runtime-dashboard-design.md`](2026-07-08-runtime-dashboard-design.md) (card types,
layout, the `sc_runtime`-label extensibility mechanism) decided, delivered exactly as
[ADR-0022](../adl/0022-runtime-dashboard-delivery-mechanism.md) decided (Option C — a locked,
YAML-mode dashboard, regenerated and re-registered on every `async_setup_entry`). ADR-0022's own
Status line was still `Proposed` despite PR #598 having already been merged with human approval —
a bookkeeping gap, not a live decision; it is corrected to `Accepted` in this same PR (a Status-only
edit, not a revision of its Context/Decision/Consequences) so this spec's ADR gate is genuinely
closed, not merely assumed closed.

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
- An ADR-0008 reload (`hass.config_entries.async_reload`, unload-then-setup — not a second bare
  `async_setup_entry` call, which `manifest.json`'s `single_config_entry: true` makes
  unrepresentative) neither raises nor leaves a stale panel/file — regeneration is idempotent.
- No install-time, config-data, or config-options value is ever labelled or shown (R19's exclusion
  criterion) — structurally true because none of those are entities to begin with (Decision 1's own
  reasoning), not because of a runtime filter this spec has to get right.

## Known internals dependency (verified against the project's pinned HA version)

ADR-0022 already accepted the risk of depending on undocumented `lovelace`/`frontend` internals.
Concretely, as read directly from `homeassistant==2026.7.2` (the version this project pins in
`requirements-test.txt`, vendored in `.venv`):

- `homeassistant.components.lovelace.dashboard.LovelaceYAML` is the class backing a `mode: yaml`
  dashboard; `homeassistant.components.lovelace.__init__.async_setup` builds these **exclusively**
  from `configuration.yaml`'s `lovelace: dashboards:` block at boot — there is no public API to add
  one afterward. `LOVELACE_DATA`'s value is a `LovelaceData` dataclass (attribute access,
  `lovelace_data.dashboards[url_path]` — **not** the deprecated dict-subscript form some
  third-party integrations still use) as of this pinned version already.
- The only way to register one at runtime is the same pattern several HACS dashboard-generator
  integrations already use (e.g. `ui_lovelace_minimalist`, `dwains-lovelace-dashboard`): insert a
  `LovelaceYAML` instance into `hass.data[lovelace.LOVELACE_DATA].dashboards[url_path]` directly,
  then call `homeassistant.components.frontend.async_register_built_in_panel(hass, lovelace.DOMAIN,
  frontend_url_path=url_path, sidebar_title="Smart Charging", sidebar_icon=DASHBOARD_ICON,
  show_in_sidebar=True, require_admin=False, config={"mode": "yaml"}, update=<True if already
  registered>)` — `sidebar_title`/`sidebar_icon`/`show_in_sidebar` are direct keyword arguments to
  this call (mirroring core's own `_register_panel` helper), **not** nested inside `config`; a call
  that omits them registers a panel with no sidebar entry, defeating the "it's just there" property
  ADR-0022 rejected Option A over. Teardown is `frontend.async_remove_panel(hass, url_path)` plus
  deleting the `dashboards[url_path]` entry.
- `LovelaceYAML.__init__` resolves `config[CONF_FILENAME]` via `hass.config.path(...)`, which joins
  it against the user's HA config directory *unless* the value is already absolute — `os.path.join`
  discards every earlier segment once it hits an absolute one, so passing the integration's own
  absolute package-directory path here keeps ADR-0022's "never the user's config directory"
  guarantee despite the helper's name. The `config` dict passed to `LovelaceYAML(...)` must also
  carry `CONF_MODE="yaml"`, `CONF_TITLE`, `CONF_ICON`, `CONF_REQUIRE_ADMIN=False`,
  `CONF_SHOW_IN_SIDEBAR=True` — core's schema normally fills these from `configuration.yaml`
  parsing; constructing the object directly means this module must supply them itself.
- Writing the generated YAML file must go through `hass.async_add_executor_job` — direct
  synchronous file I/O in `async_register_dashboard` would block the event loop (and fails outright
  under the HA test harness's blocking-call guard).
- `hass.data[LOVELACE_DATA]` only exists once the `lovelace` integration's own `async_setup` has
  run. This integration's `manifest.json` declares no dependency on it today — `dashboard.py`
  cannot assume it is present without one. See T0 below.
- This exact surface has already broken across HA core releases for *other* integrations that used
  the older dict-subscript form — logged as deprecated and removed entirely in HA 2026.2 (see
  [UI-Lovelace-Minimalist/UI#1610](https://github.com/UI-Lovelace-Minimalist/UI/issues/1610),
  [dwainscheeren/dwains-lovelace-dashboard#861](https://github.com/dwainscheeren/dwains-lovelace-dashboard/issues/861)).
  This project's pinned version already requires the attribute-access form, so this spec is not
  exposed to that specific past break, but the underlying internals-dependency risk (any future core
  refactor of `lovelace`/`frontend`) remains exactly as ADR-0022's Con describes.

This spec isolates all of this behind one module (`dashboard.py`, below) so a future HA-core break
is a one-file fix.

## Control flow

### Manifest dependency

`manifest.json` gains `"dependencies": ["lovelace"]`, so `hass.data[LOVELACE_DATA]` is guaranteed
populated before `async_setup_entry` runs. HA-harness tests that exercise `dashboard.py` directly
(rather than through a full config-entry setup) must call
`await async_setup_component(hass, "lovelace", {})` first, since a declared manifest dependency is
only enforced by HA's own component loader, not by the test harness.

### New module: `custom_components/smart_charging/dashboard.py`

| Function | Responsibility |
| --- | --- |
| `build_dashboard_config(entry: ConfigEntry) -> dict` | Pure(-ish) builder: returns the `sections` Lovelace config dict (Python dict, not YAML text) for the fixed *Charging status* / *Power flow* tiles plus the label-driven `auto-entities` *Runtime settings* card. Reads only `entry.data` (for `CONF_EV_SOC_ENTITY` / `CONF_SOLAR_FORECAST_ENTITY` — the two Decision-4 tiles that point at a user-mapped upstream entity, not a `smart_charging_` id) and fixed native ids (everything else) — no coordinator/Store access, no HA state reads. |
| `async_register_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None` | Serializes `build_dashboard_config(entry)` to YAML, writes it to `Path(__file__).parent / DASHBOARD_FILENAME` (the integration's own package directory, ADR-0022), and registers/updates the `LovelaceYAML`/panel pair at `DASHBOARD_URL_PATH`, per the Known internals dependency section. `update=True` whenever the url_path is already present (idempotent on reload). |
| `async_unregister_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None` | Removes the panel and the `dashboards[url_path]` entry. Does **not** delete the generated YAML file (deleting a file HA's frontend may still be reading mid-teardown is an unforced risk; the next `async_register_dashboard` overwrites it unconditionally anyway). |

`DASHBOARD_URL_PATH = "smart-charging"`, `DASHBOARD_FILENAME = "dashboard_generated.yaml"`,
`DASHBOARD_ICON = "mdi:ev-station"` — new constants in `const.py` (the single home for every
dashboard-related constant, alongside `LABEL_SC_RUNTIME` below — `dashboard.py` imports them, it
does not define its own copies).

### Wiring into `__init__.py`

- `async_setup_entry`: after platform forwarding (entities must exist in the registry before the
  dashboard references them — order doesn't affect correctness since Lovelace resolves entity ids
  lazily at render time, but matches the natural "entities first, then the thing that displays them"
  reading order), call `await async_register_dashboard(hass, entry)`.
- `async_unload_entry`: call `async_unregister_dashboard(hass, entry)` before/alongside the existing
  platform-unload call.

### Label application: `entity.py`

- `LABEL_SC_RUNTIME = "sc_runtime"` — new constant in `const.py`.
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
  **Known, disclosed deviation:** `time.py` creates all nine departure-time entities
  unconditionally regardless of the `deadline_available` capability — this is a pre-existing C2 gap
  (confirmed by reading `time.py`'s `async_setup_entry`: no capability check exists there today),
  not something this spec introduces or is scoped to fix. R19 AC4 (capability-gated entities hidden
  from the dashboard when their capability is off) is therefore **not fully satisfied** for the
  departure-time entities until that C2 gap is closed under its own issue; labelling them
  `sc_runtime` as they exist today is the truthful, task-scoped choice available to this spec.
- `SmartChargingEntity.async_added_to_hass(self) -> None` (new override) — **must delegate to
  `super()` first**, since `SmartChargingEntity` is the first base in every subclass's MRO
  (`RestoreEntity`/`CoordinatorEntity` come after it in `number.py`/`select.py`/`time.py`/
  `sensor.py`) and a non-delegating override would silently break every existing entity's
  restore-on-restart and coordinator-push behavior:

  ```python
  async def async_added_to_hass(self) -> None:
      await super().async_added_to_hass()
      if not self._owned_labels:
          return
      registry = er.async_get(self.hass)
      entry = registry.async_get(self.entity_id)
      registry.async_update_entity(
          self.entity_id, labels=(entry.labels | self._owned_labels) if entry else self._owned_labels
      )
  ```

  Note the merge (`entry.labels | self._owned_labels`), not a bare assignment —
  `async_update_entity`'s `labels` parameter **replaces** the stored set, so a bare assignment would
  silently erase any label the user attached themselves on the very next reload (the same clobber
  risk ADR-0022 rejected Option B1 over, just at the label layer instead of the dashboard-content
  layer). This runs once per entity, every setup (including reload) — idempotent, since the merged
  result is unchanged if the label is already present.
- **Label-registry prerequisite:** `sc_runtime` must exist as a `label_registry` entry before any
  entity references it — an entity-registry label id with no matching `label_registry` entry has no
  display name and nothing for the dashboard's `auto-entities` `label:` filter to resolve against.
  Add an idempotent `lr.async_get(hass).async_create(LABEL_SC_RUNTIME)` call (checking
  `lr.async_get(hass).async_get_label_by_name` first, or catching the "already exists" case per
  `label_registry`'s own API) in `async_setup_entry`, before platform forwarding.

This keeps the label mechanism a property of the entity class (declared once, next to the id
suffix), not a separate list `dashboard.py` has to keep in sync — the same "one place owns the
fact" discipline `entity.py`'s existing `_object_id_suffix`/`unique_id` derivation already follows.

## Entities mapped to sections (real current ids, replacing the 2026-07-08 doc's placeholders)

| Section | Card | Entities (native ids) |
| --- | --- | --- |
| Charging status | `tile` × 6–7 | `entry.data[CONF_CHARGER_STATUS_ENTITY]` (charger status — a **required** role, always mapped; **not** `sensor.smart_charging_status`, which is integration health/Fault-or-OK per ADR-0007, a different value), `entry.data[CONF_EV_SOC_ENTITY]` (battery level — **optional**, included only when set), `select.smart_charging_profile`, `sensor.smart_charging_active_mode` (the resolved active mode — **not** `select.smart_charging_mode`, which is the raw `Manual`-profile override selection and is stale/irrelevant display-wise under the `Auto` profile), `sensor.smart_charging_active_soc_limit`, `sensor.smart_charging_time_to_full`, `sensor.smart_charging_peak_headroom_a` |
| Power flow | `tile` × 4, `markdown` × 1 (conditional) | `entry.data[CONF_CHARGER_CURRENT_ENTITY]`, `entry.data[CONF_NET_POWER_ENTITY]` (both required roles, always mapped — these satisfy R19 AC1's "current charger current" and AC2's "net import"), `sensor.smart_charging_solar_surplus_w`, `sensor.smart_charging_effective_peak_limit`; the solar-forecast `markdown` card is included only when `entry.data[CONF_SOLAR_FORECAST_ENTITY]` is set (mirrors the solar-capability gating `entity-catalog.md` already documents for `solar_reserve_soc`) |
| Runtime settings | `custom:auto-entities` | filtered by `label: sc_runtime` only — the 2026-07-08 doc's `exclude: label: sc_install` clause is dropped: per that doc's own Decision 1 reasoning, no entity is ever labelled `sc_install` (install-time values are config-data/options, not entities), so the exclude clause can never match anything; keeping it would be dead config with no test able to exercise it |

**Correcting an earlier draft of this table:** an earlier version of this spec dropped
`charger_current`/`net_power` and reasoned that `sensor.smart_charging_adapter_readings` covered
them — this was wrong. ADR-0021's own Context states that sensor exists *specifically* to give this
dashboard something to bind to for hardware-I/O values with no dedicated entity, and R19 AC1/AC2
require both values on the dashboard itself, not merely somewhere reachable in the entities UI. The
table above binds directly to the required-role config-entry entity ids instead — a single value
per tile is also the better UX fit for the *tile* card type Decision 2 chose; `adapter_readings`
remains excluded from the tile set (it is a timestamp-plus-attributes diagnostic blob, not a
tileable single value) but is no longer cited as a reason to omit these two values — it never
covered them.

`input_number.sc_power_target_current_a` / `sc_solar_reserve_soc` (entity-catalog.md's two
still-open legacy `sc_` runtime helpers) are excluded — they are not native owned entities today (the
Power target current is already native as `number.smart_charging_target_current`, included above;
the solar-reserve cap remains a config-option with no entity to label, an existing ADR-0004 open
question this spec does not resolve).

## Addendum (2026-08-13) — two UX refinements from reviewing against the Slim Laden reference

The 2026-07-08 design doc's own Open questions named this exact moment: "revisit only if the
built-in cards prove visually insufficient once a real dashboard is built and reviewed against the
[Slim Laden] reference for UX parity." Reviewing the built dashboard against that reference surfaced
two refinements — neither is new behavior invented for this addendum; both are derived from
decisions this spec (or the glossary) already made.

### Mode selector only editable under the `Manual` profile

`system-overview.md`'s glossary already scopes `select.smart_charging_mode` to "the `Manual`
profile's mode-override selection" — it has no effect under `Auto` (E2 drives dispatch instead, per
`ModeSelect`'s own docstring in `select.py`). The dashboard was showing/allowing edits to it
unconditionally; this is a dashboard-side correction to match behavior the domain model already
states, not a new rule.

**Mechanism:** `select.smart_charging_mode` is pulled out of the label-driven `auto-entities` list
(via that card's own `exclude` filter, keyed on `entity_id` — not the `label: sc_install` clause
Decision 1 already rejected, a different, legitimate exclude) and rendered as its own `entities`
card, gated via that card's own `visibility` key (the native idiom for a single gated card inside a
`sections` view — a wrapping `type: conditional` card also works but adds a needless nesting level)
on `select.smart_charging_profile == "Manual"`:

```yaml
type: entities
entities:
  - select.smart_charging_mode
visibility:
  - condition: state
    entity: select.smart_charging_profile
    state: Manual
```

Note the condition key is `entity`, not `entity_id` — the Lovelace `visibility`/`conditional` schema
differs from the automation/script condition schema here; a missing `entity` key resolves the
checked state as `unavailable` and the card silently never renders (caught in this addendum's own
fresh-agent review, not in the first draft).

The entity keeps its `sc_runtime` label (entity-registry classification is orthogonal to which card
renders it) — only the dashboard's own filter/placement changes.

### Departure-time settings move to a second dashboard tab

HA renders `>1` entries in a YAML dashboard's `views` list as tabs automatically — no new
registration mechanism needed, ADR-0022's Option C is unaffected. `build_dashboard_config` now
returns two views: `overview` (unchanged three sections, minus the departure-time rows) and
`deadline` (one section, the nine departure-time entities). Both filter by `label: sc_runtime`
plus `domain: time` (`auto-entities` ANDs the keys of one `include` filter object) — this stays
label-driven, not a hardcoded list, matching Decision 1's own extensibility property. The overview
tab's own `auto-entities` card gains a matching `exclude: [{domain: time}]` so the nine departure
entities don't render twice.

## Testing approach (ADR-0009)

`dashboard.py` imports `homeassistant.components.frontend`/`lovelace` directly → **HA harness**
(`tests/test_dashboard.py`), not plain pytest. Label application (`entity.py`'s
`async_added_to_hass` override) is entity/registry-level → HA harness, in a **new**
`tests/test_entity_labels.py` — `tests/test_entity.py` is deliberately left alone: it is a
plain-pytest file today (constructs `SmartChargingEntity` directly, no `hass` fixture, testing only
the pure `_object_id_suffix`/`unique_id` derivation), and mixing an HA-harness test into it would
blur that boundary rather than extend it. No `modes/`/`engines/` code changes.

Integration checkpoint (T7): a full `MockConfigEntry` setup registers the panel at
`DASHBOARD_URL_PATH` with `mode: yaml`, every runtime entity's registry entry carries
`sc_runtime`, no diagnostic/state entity does, and unloading removes the panel without error; a
second setup (simulating reload) does not raise and does not duplicate the panel.

## Packaging

- README gets one paragraph (per ADR-0022's Consequences) explaining the dashboard is regenerated
  on every reload, so in-place edits to it don't persist, and how to build a separate ordinary
  dashboard from the same entities instead — **and** names `custom:auto-entities` (HACS) as a
  required prerequisite, since the entire *Runtime settings* section (R19 AC3/AC6) renders as a
  broken card without it. This is new information the dashboard build surfaces, not something the
  2026-07-08 design doc already flagged for packaging.
- No `strings.json`/translation changes — the dashboard's own card titles are static English text
  inside the generated YAML (Lovelace card titles are not part of HA's translation system), matching
  how every other dashboard-building HACS integration ships them.

## Deferrals

- **`entity-catalog.md`'s `input_number.sc_power_target_current_a` row.** `entity-catalog.md` itself
  (its own Notes) deliberately retains this as an **open ADR-0004 question**, not an oversight — C2
  shipped the native `number.smart_charging_target_current` ahead of that question being resolved.
  This spec uses the real, current native id and leaves ADR-0004's own resolution to that ADR's
  follow-up, rather than treating it as a catalog wording fix.
- **The `sc_solar_reserve_soc` open ADR-0004 question** (still a config-option, not an entity) is
  unchanged by this spec; the dashboard simply cannot show it as a runtime entity until that
  question resolves.
- **R19 AC4 for the nine departure-time entities** — not fully satisfied; see the disclosed
  deviation in the Label application section (a pre-existing C2 gap, not introduced or fixed here).
- **R19 AC3 for `select.smart_charging_mode` under the `Auto` profile** — this addendum's mode gate
  (above) makes the entity invisible on the dashboard while `Auto` is active, whereas R19 AC3 reads
  "every runtime entity is both visible and settable from the dashboard" with no profile carve-out.
  The behavioral rationale (the glossary already scopes the entity to `Manual`; it has no effect
  under `Auto`) is sound, but the requirement text itself is not amended by this spec — a follow-up
  issue against R19 AC3's wording, or a switch to an always-visible-but-disabled rendering, is left
  open rather than silently treating the AC as met.
- **Mushroom cards, tablet-specific sizing** — already deferred by the 2026-07-08 design doc; nothing
  here reopens either.
- **Deleting the generated YAML file on unload** — deliberately not done (see `dashboard.py` table);
  revisit only if a concrete problem (stale file confusing a manual inspection) is reported.

## Requirements / use-cases realized

- [R19](../analysis/requirements.md#r19--runtime-dashboard), [UC11](../analysis/use-cases/UC11-monitor-and-manage-charging-configuration.md) — via the concrete build above.
- [ADR-0022](../adl/0022-runtime-dashboard-delivery-mechanism.md) — the delivery mechanism this spec implements.
