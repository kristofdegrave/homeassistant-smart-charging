# Runtime dashboard (C5) — sequencing note

*Date: 2026-08-10*

## Context

Issue #549 ("Epic: Clients & Dashboard") originally tracked C1/C3/C5/C6 from
`docs/design/project-plan.md` Phase 4. A scoping pass (2026-08-10, see #549's comment thread)
found C1, C3, and C6 already fully implemented and tested. Only **C5 — runtime dashboard
(UC11)** remains unbuilt: no Lovelace/dashboard code exists yet, only
[`docs/plans/2026-07-08-runtime-dashboard-design.md`](2026-07-08-runtime-dashboard-design.md)
(the design deliverable) and its mockup.

This note is not a technical design — the 2026-07-08 doc already made the dashboard's technical
decisions (label-driven `auto-entities` extensibility, card types, layout). It exists only to
record the **sequencing** decision reached while scoping the implementation spec: two
prerequisite artifacts must land before the C5 implementation spec (design + TDD plan) can be
written, because the 2026-07-08 doc's own "Open questions" section left them undecided and both
are decisions this implementation-spec cycle has no authority to make unilaterally (per
`write-impl-spec`'s "derive, don't design" discipline).

## Why two prerequisites, not one spec

**1. `entity-catalog.md` update (`docs/analysis/`).** The 2026-07-08 design doc calls for three
new derived sensors it does not have entity ids for yet — `sensor.sc_solar_surplus_w`,
`sensor.sc_time_to_full`, `sensor.sc_peak_headroom_a` — plus `Read by: UC11` traceability
additions to the existing `ev_soc` and `solar_forecast` adapter roles, plus a resolved id for the
charger-current read-back the status tiles need. No requirement wording changes, but it is still
an edit to a `docs/analysis/` document, which CLAUDE.md's review protocol requires to go through
its own issue-first + fresh-agent (analysis-reviewer) review cycle before an implementation spec
cites those ids as settled.

**2. ADR: dashboard delivery/registration mechanism (`docs/adl/`).** How the integration ships
the dashboard was decided during this scoping pass: **programmatic registration at setup**, not
a manually-added YAML file. That decision carries real, hard-to-reverse structural weight — a new
dependency on HA's frontend/Lovelace storage API, a reload/update behavior that must not clobber
a user's own edits to the same dashboard resource, and a question of whether it still fits C5's
`system-design.md` classification ("Client, no service of its own", R19) or needs a note added
there. CLAUDE.md's ADR criteria ("a choice about structure that would be expensive to reverse...
which library or protocol to depend on") match this squarely, so it gets its own ADR before the
implementation spec builds on it.

## Sequence

1. `docs/analysis/entity-catalog.md` update — own issue, own branch, `write-requirement`'s
   propagation discipline (lighter catalog-only path, no requirement wording change),
   analysis-reviewer review, PR, human-approved merge.
2. ADR — dashboard delivery/registration mechanism — own issue, own branch, `write-adr` skill,
   adr-reviewer review, PR, human-approved merge.
3. C5 implementation spec (design + TDD plan) — this session's original goal, `write-impl-spec`
   skill, blocked on #1 and #2 above landing on `main`. Builds the `sc_runtime`/`sc_install`
   labels at entity creation, the three new sensors, the dashboard assembly per the 2026-07-08
   doc's card/layout decisions, and the registration mechanism per the ADR.

## Deferrals carried forward (unchanged from 2026-07-08)

- Mushroom cards (styling) — stays deferred; built-in `tile`/`auto-entities` ship first.
- Tablet-specific column counts / touch-target sizing — stays deferred to a later pass once a
  real dashboard is in front of users.

## Requirements / use-cases realized

None directly — this is a process/sequencing note, not a technical or behavioral artifact. R19
and UC11 remain realized by the 2026-07-08 design doc; this note only orders the work that
implements it.
