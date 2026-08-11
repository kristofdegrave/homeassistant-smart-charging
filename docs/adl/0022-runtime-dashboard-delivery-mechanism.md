# ADR-0022: Runtime-dashboard delivery mechanism

Date: 2026-08-10
Status: Accepted

## Context

[`docs/plans/2026-07-08-runtime-dashboard-design.md`](../plans/2026-07-08-runtime-dashboard-design.md)
decided the runtime dashboard's (UC11, R19) card types, layout, and label-driven extensibility
mechanism (the `sc_runtime`/`sc_install` labels driving an `auto-entities` card), but explicitly
left "how the dashboard reaches the user" as an open question — deliberately out of scope for
that doc. [`docs/plans/2026-08-10-runtime-dashboard-sequencing.md`](../plans/2026-08-10-runtime-dashboard-sequencing.md)
is where that gap was identified as needing its own ADR before the C5 implementation spec can be
written; it initially framed the dependency as "HA's frontend/Lovelace **storage** API," a framing
this ADR refines once the option set below is laid out in full — the chosen mechanism turns out
not to use the storage API at all.

That question has real, hard-to-reverse structural weight, so it gets its own ADR rather than
being decided inline in the C5 implementation spec (`write-impl-spec`'s "derive, don't design"
discipline):

- Every mechanism considered below reaches into Home Assistant's `lovelace`/`frontend` components
  through internals that are not a documented, stable integration API (there is no first-party
  "register a dashboard" call for custom integrations) — whichever one is chosen is a dependency
  the integration must keep working across HA core upgrades, and that maintenance burden needs to
  be weighed honestly rather than assumed away for whichever option looks more "official."
- If the dashboard is *editable* Lovelace configuration (the storage-mode dashboards a user can
  drag/drop/edit in the UI) and the integration ever rewrites that stored configuration after
  first creating it, every `async_setup_entry` (a reload — ADR-0008 — happens on every options/
  reconfigure change, not only on install/upgrade) needs a defined answer for what happens to a
  dashboard resource that may already carry the user's own edits. Silently overwriting it is a
  real risk, not a hypothetical one.
- `docs/design/system-design.md` classifies UC11 as **"Client, no service of its own"** (line
  99–103: it merely presents/edits entities through the Store, with no Manager/Engine
  orchestration). Whichever mechanism is chosen must not smuggle in orchestration or policy that
  would contradict that classification.

## Considered options

### Option A — Ship a YAML file in the repo; the user adds it manually

The dashboard's YAML lives in the integration's repo (e.g. under `dashboards/`); setup
instructions tell the user to create a new dashboard in YAML mode and paste it in.

- Pro: zero new HA-internals dependency; zero clobber question — nothing is ever written on the
  user's behalf, so there is nothing to overwrite.
- Con: fails UC11's implicit "the dashboard is there when the integration is set up" expectation;
  every other Client (owned entities, config/options flow) is created automatically at setup, so a
  manual step here is the odd one out and the easiest step for a user to forget or get wrong
  (pasting stale YAML after an integration upgrade adds fields).

### Option B1 — Programmatic registration as an editable (storage-mode) dashboard, kept in sync every reload

The integration registers a normal, user-editable Lovelace dashboard via the `lovelace` component's
internal `DashboardsCollection`, and **rewrites** its stored content on every `async_setup_entry`
so newly-added cards/entities always appear.

- Pro: closest to "batteries included" — the user can freely rearrange, add Mushroom cards, etc.,
  exactly like any dashboard they built themselves, right up until the next reload.
- Con: this is the option Context's clobber risk is actually about — rewriting storage-held,
  user-editable configuration on every reload has no reliable way to tell "the user changed this"
  apart from "the integration's own last write," so a rearrange the user made yesterday is
  silently gone after today's options-flow save. Rejected for exactly this reason; it is the
  option the other two "storage-mode" variants below exist to avoid.

### Option B2 — Programmatic registration as an editable (storage-mode) dashboard, created once and never rewritten

Same `DashboardsCollection` registration as B1, but only when the dashboard doesn't already exist;
once created, the integration never touches its stored content again, on any later reload.

- Pro: keeps B1's full editability with no ongoing clobber risk — the integration writes exactly
  once, at first creation, so there is nothing left to silently overwrite. The
  `auto-entities`/label mechanism already means the *runtime settings* section needs no rewrite to
  stay current (`2026-07-08-runtime-dashboard-design.md` Decision 1), so this isn't a compromise on
  that axis.
- Con: the integration itself still adds new **status/power-flow** readouts over time on fixed,
  non-label-driven tile cards — this ADR's own prerequisite catalog update just added three
  (`sensor.smart_charging_solar_surplus_w`, `sensor.smart_charging_time_to_full`,
  `sensor.smart_charging_peak_headroom_a`). "Created once" means an existing installation's
  dashboard never gains those new tiles on upgrade unless a **separate versioning/migration
  mechanism** is built to detect "the packaged template changed since I created this" and either
  reconcile or prompt the user — real, ongoing engineering this integration would then own for as
  long as the dashboard's status section keeps growing, for a Client `system-design.md` classifies
  as having no service, and no orchestration, of its own.

### Option C — Programmatic registration as a locked (YAML-mode) dashboard

The integration writes a YAML file into its own package directory and registers it at a fixed
`url_path` (e.g. `smart-charging`) via HA's YAML-mode dashboard mechanism (the `lovelace:
dashboards:` config shape, `mode: yaml`) — a dashboard whose content is "configured via file, not
the UI," so it is never a member of the storage-backed `DashboardsCollection` at all. The
integration regenerates that file and re-registers the panel on every `async_setup_entry`.

- Pro: the clobber question doesn't need an answer — there is no user-owned stored copy for a
  YAML-mode dashboard to begin with (HA's own UI refuses to save edits to one in place), so
  regenerating the file on every reload carries no data-loss risk, and unlike B2 it needs no
  separate versioning/migration mechanism: the file is always exactly what the current integration
  version's template says it should be, mirrored on every reload. The user still edits everything
  UC11 actually asks for — the individual entities the dashboard's cards point at — just not the
  dashboard's own layout.
- Con: relies on the same category of undocumented `lovelace`/`frontend` internals as B1/B2 (the
  YAML-mode registration path rather than `DashboardsCollection`), so it carries its own
  upgrade-fragility risk, not a lesser one — the trade this option makes is spending that
  maintenance cost on staying automatically in sync (Pro) rather than on user-editability. The
  user cannot rearrange cards or restyle the dashboard itself; wanting a different layout means
  building a separate, ordinary dashboard from the same entities, since any edit made to the
  packaged file is replaced on the next reload regardless.

### Option D — Blueprint-style optional import

Package the dashboard as an importable blueprint (the same UX pattern as automation blueprints):
the user explicitly triggers an import step; nothing is registered automatically.

- Pro: no silent registration at all — the most conservative option for "does the integration
  touch frontend configuration on my behalf."
- Con: HA's blueprint mechanism is built for automations/scripts, not dashboards — there is no
  first-party "dashboard blueprint" import flow to build on, so this option means building custom
  import UX from scratch, a materially larger implementation cost than A/B/C for a UC11
  acceptance criterion that doesn't ask for an import step. (The 2026-07-08 design doc rejected an
  adjacent option — a Python dashboard strategy reading `entity-catalog.md` directly — for the same
  disproportionate-build-cost reason; this option fails the same test.)

## Decision

**Option C** — programmatic registration as a locked, YAML-mode dashboard, regenerated and
re-registered idempotently on every `async_setup_entry`.

The real competitor here is B2, not B1: B1 is rejected outright (it's the clobber risk Context
describes). B2 avoids that risk and keeps editability, so the actual trade is B2 vs. C — ongoing
version-migration engineering (B2, to ever deliver a new status tile to an existing install) versus
ongoing internals-tracking risk that both options carry anyway (C's Con), in exchange for the
dashboard staying automatically current with zero migration logic. Given this integration's status/
power-flow readouts have already grown once in this same work item (three new sensors, none
label-driven), and `system-design.md` classifies UC11 as a Client with **no service of its own** —
i.e., not a component this project wants to grow a standalone versioning subsystem for — Option C's
zero-migration property outweighs B2's editability. Option A is rejected because it's the one
Client in this integration a user would have to set up by hand while every other owned entity/flow
appears automatically; Option D is rejected as disproportionate build cost for a need R19/UC11
doesn't express.

This decision does not change `docs/design/system-design.md`'s classification of UC11 as
"Client, no service of its own": registering a YAML-mode dashboard is a setup-time detail of how
that Client's UI surface is materialized, not new orchestration or policy — no Manager/Engine
call is introduced, and the dashboard still only ever reads/writes through the Store and adapter
read-backs, exactly as system-design.md already states.

## Consequences

- The C5 implementation spec can now name concrete tasks: generate the dashboard YAML (written to
  a file inside the integration's own package directory, never the user's config directory) from
  `entity-catalog.md`'s runtime-labelled entities plus the fixed status/power-flow tiles, and
  register/re-register it as a YAML-mode dashboard panel on every `async_setup_entry` — handling
  both the duplicate-`url_path` case (updating the existing registration rather than erroring) and
  removal on `async_unload_entry` (an ADR-0008 reload is unload-then-setup, so the panel must be
  torn down and re-added cleanly each time).
- Because the runtime-settings section is label-driven (`2026-07-08-runtime-dashboard-design.md`
  Decision 1) and the whole file is regenerated from the current template on every reload, neither
  a new `sc_runtime`-labelled entity nor a new fixed status tile needs a dashboard-specific
  migration step — unlike Option B2, there is no "existing install's dashboard is now stale" state
  to detect or reconcile.
- Users who want a different layout must build their own ordinary dashboard from the same
  entities rather than editing the packaged file in place, since any such edit is replaced on the
  next reload — worth a line in the integration's README/setup docs so it isn't a surprise the
  first time someone tries to drag a card in the packaged one.
- `docs/design/project-plan.md`'s C5 entry (`**ADR gate:** none (inherits C2/C3's settled native
  names)`) predates this ADR and needs updating to name it as C5's ADR gate — a small, mechanical
  follow-up edit, tracked alongside this ADR rather than deferred.
- No change to `docs/design/system-design.md` is required (see Decision).
