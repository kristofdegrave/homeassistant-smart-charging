# Work type: `development` — the `home-assistant` overlay

Stack material for the `development` work type, read with the core files beside it as one
work file, one bar and one checklist — each core file's **Overlays** section says which section
below it takes. Nothing here restates a rule of those files: every entry names the rule or the
bar item it extends, and the severity is the item's unless the entry states one. The shape of
an overlay is this tree's `README.md`'s.

## Implement

**Where the code lives.** The product code is `custom_components/smart_charging/`; tests mirror
it 1:1 under `tests/`. Wherever a core file of this work type says *the product code* or *the
product-code tree*, this is the tree it means.

**The platform reference** — the work file's read-first list, before the TDD loop: the
**`ha-integration-knowledge` skill** — the Home Assistant platform reference (entity
platforms, config-flow conventions, quality scale, thin-wrapper rule) — before writing
anything that touches HA APIs.

**Honour the structural ADRs as you code** — the work file's *Building the task*. The bar's
item 2, *Structural ADR compliance*, judges them, and the enumeration is under **Done** below,
two of them at Critical. What that means while writing: the engine/adapter boundary, the two
clamp call sites and the fault path are decided *before* the first line, not repaired after a
review — a design that puts HA state inside an engine or folds the two clamps into one
conditional is rewritten rather than adjusted.

**A common mistake** — the work file's list: deciding the layer after writing the code — a
piece that turns out to need `homeassistant.*` inside `modes/`/`engines/` is a design signal,
and moving the import is not the fix.

## Done

**Item 2, *Structural ADR compliance*** — the boundaries this project cannot regress. Each miss
names the file and the boundary crossed.

- **Engine purity (ADR-0006/0009/0010):** nothing under `modes/` or `engines/` imports
  `homeassistant.*` or calls another engine; a stateful engine takes its state as a parameter
  and never holds HA state. An `import homeassistant` under `modes/`/`engines/` is **Critical** —
  it defeats the package boundary the plain-pytest half of the suite rests on.
- **Adapter isolation (ADR-0003):** all HA-entity I/O goes through an adapter, and no logic
  layer reads a raw `entity_id` directly — **Major**. A role returning `None` is the fault
  signal, never a guessed default.
- **Two distinct clamps (ADR-0006):** the grid-safety clamp is a separate call site from the
  peak clamp, with no shared opt-out. Merging the two into one conditional is **Critical**.
- **Fault path (ADR-0007):** every adapter `None` or exception funnels to force-0 A + `Fault` —
  **Major** where one does not. Grid voltage `None` is the single exception (the NF4 nominal
  fallback) and is **Major** if routed to the fault path instead.
- **Config data/options split (ADR-0005):** mappings, translations and thresholds in data;
  tunables (the control interval) in options; an options change reloads the entry — **Major**.
- **Native naming and package layout (ADR-0004/0002/0010):** owned entities use the
  `smart_charging_` native names, and files sit in the ADR-mandated package (`adapters/`,
  `modes/`, `engines/`, platform files and `coordinator.py`/`entity.py` at root) — **Major**,
  because both are contracts other code and the entity registry already depend on.

**Item 3, *Code health* — the no-magic-strings exception.** A value that must round-trip
through HA config-entry storage or `vol.In(...)` as a bare `str` may use module-level string
constants instead of an enum (see `const.py`'s `ROUND_UP`/`ROUND_DOWN`/`ROUND_NEAREST`) —
repeated bare literals are still the finding there, the choice of constant over enum is not.

**Item 6, *Runtime check recorded* — what is observable at runtime.** The Definition of Done
defines observable runtime behaviour and routes here for what it is in this stack: a diff
changes it when it changes any of

- an **owned entity's state value**, or the computation that produces it;
- an owned entity's **unit of measurement**, **display precision**, **device class** or
  **state class**;
- the **dashboard** — which tiles or cards appear, their order, titles, or how a value is
  formatted;
- a **notification** the integration raises — its text, its trigger condition, or when it
  clears;
- the **current commanded to the charger**;
- whether an owned entity **appears at all** — registry enablement and capability gating —
  whether it goes **unavailable**, and the **name it displays** (`strings.json`,
  `translations/`).

**Tests green** — the Definition of Done's item, for the harness matched to what changed: the
`testing` work type's overlay for this stack states the split under its bar's item 1, *Harness
split*, and it is the same split for a test written inside a `development` task.

## Review

**What to read first — always:** the changed files under `custom_components/smart_charging/`
and their mirrored tests under `tests/` — from the diff the caller gives you, or the files
whole.

**Read conditionally:** the `ha-integration-knowledge` skill — where the diff touches HA
platform surface (entity classes, config flow, `manifest.json`, services).
