# ADR-0022: Runtime-dashboard delivery mechanism

Date: 2026-08-10
Status: Proposed

## Context

[`docs/plans/2026-07-08-runtime-dashboard-design.md`](../plans/2026-07-08-runtime-dashboard-design.md)
decided the runtime dashboard's (UC11, R19) card types, layout, and label-driven extensibility
mechanism (the `sc_runtime`/`sc_install` labels driving an `auto-entities` card), but explicitly
left "how the dashboard reaches the user" as an open question — deliberately out of scope for
that doc.

That question has real, hard-to-reverse structural weight, so it gets its own ADR rather than
being decided inline in the C5 implementation spec (`write-impl-spec`'s "derive, don't design"
discipline):

- Whichever mechanism is chosen becomes a dependency on a specific Home Assistant frontend/
  Lovelace capability, which the integration must keep working across HA core upgrades.
- If the dashboard is *editable* Lovelace configuration (the storage-mode dashboards a user can
  drag/drop/edit in the UI), every `async_setup_entry` (a reload — ADR-0008 — happens on every
  options/reconfigure change) needs a defined answer for what happens to a dashboard resource
  that may already exist and may already carry the user's own edits. Silently overwriting it on
  every reload is a real risk, not a hypothetical one — ADR-0008 already causes reloads far more
  often than "the user installed or upgraded the integration."
- `docs/design/system-design.md` classifies UC11 as **"Client, no service of its own"** (line
  99–103: it merely presents/edits entities through the Store, with no Manager/Engine
  orchestration). Whichever mechanism is chosen must not smuggle in orchestration or policy that
  would contradict that classification.

## Considered options

### Option A — Ship a YAML file in the repo; the user adds it manually

The dashboard's YAML lives in the integration's repo (e.g. under `dashboards/`); setup
instructions tell the user to create a new dashboard in YAML mode and paste it in.

- Pro: zero new HA-API dependency; zero reload/clobber question — nothing is ever written on the
  user's behalf, so there is nothing to overwrite.
- Con: fails UC11's implicit "the dashboard is there when the integration is set up" expectation;
  every other Client (owned entities, config/options flow) is created automatically at setup, so a
  manual step here is the odd one out and the easiest step for a user to forget or get wrong
  (pasting stale YAML after an integration upgrade adds fields).

### Option B — Programmatic registration as an editable (storage-mode) dashboard

The integration registers a normal, user-editable Lovelace dashboard at `async_setup_entry`,
using HA's storage-mode dashboard registration.

- Pro: closest to "batteries included" — the user can freely rearrange, add Mushroom cards, etc.,
  exactly like any dashboard they built themselves.
- Con: storage-mode dashboards are stored as user configuration, not code; the integration would
  need to detect "does this dashboard already exist, and did the user change it?" on every reload
  to avoid clobbering their edits, and no reliable signal exists to tell "user changed this" apart
  from "the integration's own last write." Getting this wrong either loses user customization
  silently or leaves stale cards behind after an entity-catalog change — exactly the clobber risk
  named in Context.

### Option C — Programmatic registration as a locked (YAML-mode) dashboard

The integration registers a dashboard at a fixed `url_path` (e.g. `smart-charging`) whose content
comes from a YAML file the integration owns, using HA's YAML-mode dashboard registration — the
same mechanism HA itself offers for a dashboard that is "configured via file, not the UI." The
registration re-runs (idempotently) on every `async_setup_entry`.

- Pro: the clobber question in Context doesn't need an answer — YAML-mode dashboards are not part
  of the editable Lovelace storage collection, so there is no user-owned copy to overwrite; the
  integration can freely regenerate the dashboard's content on every reload (e.g. to add a card
  for a newly-catalogued runtime entity) with no data-loss risk. The user still edits everything
  UC11 actually asks for — the individual entities the dashboard's cards point at — just not the
  dashboard's own layout.
- Con: the user cannot rearrange cards or restyle the dashboard itself without editing the
  integration-owned YAML source directly (which HA's UI won't let them do in place — they'd need
  to fork the packaged file), a real loss of flexibility compared to Option B.

### Option D — Blueprint-style optional import

Package the dashboard as an importable blueprint (the same UX pattern as automation blueprints):
the user explicitly triggers an import step; nothing is registered automatically.

- Pro: no silent registration at all — the most conservative option for "does the integration
  touch frontend configuration on my behalf."
- Con: HA's blueprint mechanism is built for automations/scripts, not dashboards — there is no
  first-party "dashboard blueprint" import flow to build on, so this option means building custom
  import UX from scratch, a materially larger implementation cost than A/B/C for a UC11
  acceptance criterion that doesn't ask for an import step.

## Decision

**Option C** — programmatic registration as a locked, YAML-mode dashboard, re-registered
idempotently on every `async_setup_entry`.

This resolves the Context's central risk (clobbering a user's dashboard edits on reload) by
construction rather than by a merge algorithm: a YAML-mode dashboard has no editable, storage-held
copy to clobber, so Option B's hardest problem simply doesn't arise. It still meets UC11's actual
requirement — the user edits the underlying entities, never the dashboard layout, and R19 never
asks for dashboard layout to be user-editable — so Option B's flexibility advantage isn't a
requirement this decision needs to satisfy. Option A is rejected because it's the one Client in
this integration a user would have to set up by hand while every other owned entity/flow appears
automatically; Option D is rejected as disproportionate build cost for a need R19/UC11 doesn't
express.

This decision does not change `docs/design/system-design.md`'s classification of UC11 as
"Client, no service of its own": registering a YAML-mode dashboard is a setup-time detail of how
that Client's UI surface is materialized, not new orchestration or policy — no Manager/Engine
call is introduced, and the dashboard still only ever reads/writes through the Store and adapter
read-backs, exactly as system-design.md already states.

## Consequences

- The C5 implementation spec can now name concrete tasks: generate the dashboard YAML from
  `entity-catalog.md`'s runtime-labelled entities (the label mechanism `2026-07-08-runtime-
  dashboard-design.md` Decision 1 already settled) and register it as a YAML-mode dashboard in
  `async_setup_entry`, idempotently re-registering on every reload (ADR-0008).
- Because the dashboard is regenerated on every reload rather than persisted as user state, a
  runtime-entity addition (e.g. a future use-case's new `sc_runtime`-labelled entity) needs no
  dashboard-specific migration step — the next reload picks it up, which is the same
  extensibility guarantee `2026-07-08-runtime-dashboard-design.md` already relies on for the
  `auto-entities` card, now extended to the dashboard's own registration.
- Users who want a different layout must build their own dashboard from the same entities rather
  than editing the packaged one in place — worth a line in the integration's README/setup docs so
  it isn't a surprise the first time someone tries to drag a card.
- No change to `docs/design/system-design.md` is required (see Decision) — no follow-up edit
  there.
