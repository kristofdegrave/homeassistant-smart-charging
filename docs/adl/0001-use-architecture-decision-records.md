# ADR-0001: Use Architecture Decision Records, with a Nygard+options template

Date: 2026-07-04
Status: Accepted

## Context

We need to record the architectural decisions made on this project. This is a
recommendation from the project's human partner (Kristof Degrave), based on prior
experience using ADRs on another project (see e.g. that project's own ADR-001, "Record
architecture decisions").

Architectural decisions made for this project — e.g. the entity-mapping/adapter-layer
choice — have so far been folded into design docs with no durable, indexed record of *why*
an alternative was rejected. As the integration grows (multi-charger support, three-phase,
additional config-entry shapes), later contributors — including a future instance of this
assistant — need a fast way to answer "why is it built this way, and what else did we
consider?" without re-reading an entire design doc or PR thread.

[adr.github.io](https://adr.github.io/) documents this problem and its established
solution: a lightweight, numbered, immutable-once-accepted record per decision, kept in
the repo next to the code/docs it governs.

Two template families are common:

- **Michael Nygard's original template** — Title, Status, Context, Decision,
  Consequences. Minimal; fast to write; says nothing about alternatives that were
  rejected.
- **MADR (Markdown Any Decision Records)** — adds Decision Drivers, a full Considered
  Options list with per-option pros/cons, and a Decision Outcome section. Thorough, but
  heavier than this project's terse documentation style (see `requirements.md`,
  `docs/analysis/use-cases/*`).

## Considered options

### Option A — Michael Nygard's template as-is

- Pro: Matches this project's terse documentation style; fastest to write and keep
  current.
- Con: Doesn't record *which alternatives were rejected and why* — exactly the
  information most useful when a later decision revisits the same trade-off.

### Option B — Full MADR

- Pro: Most explicit about alternatives; separates decision drivers from the options
  themselves.
- Con: More sections than most decisions in this project need (Decision Drivers,
  separate Decision Outcome vs. Consequences); overhead per record that this project's
  other docs deliberately avoid (see the requirements/use-case skills' "what, not how,
  one home per fact" discipline).

### Option C — Nygard base with an inserted "Considered options" section (pros/cons per option), dropping MADR's separate Decision Drivers section

- Pro: Keeps Nygard's four-section skeleton (Status, Context, Decision, Consequences)
  that fits this project's style, while still forcing every rejected alternative onto
  the record with its trade-off — the specific gap in Option A.
- Con: Not a single named template from either source; it's a hybrid, so contributors
  familiar with "pure" Nygard or "pure" MADR need the project's own template file
  (`docs/adl/template.md`) rather than an external reference alone.

## Decision

Option C. `docs/adl/template.md` is the authoritative template: Status / Context /
Considered options (with pros/cons) / Decision / Consequences. This keeps ADRs as
lightweight as the rest of the project's documentation while satisfying the actual
reason ADRs exist here — a searchable record of rejected alternatives.

ADRs live in `docs/adl/`, numbered sequentially (`NNNN-kebab-case-title.md`, zero-padded
to 4 digits), and are never edited to reverse a decision — a reversal gets a new ADR
that supersedes the old one (old ADR's Status becomes `Superseded by ADR-NNNN`).

## Consequences

- Every architectural decision going forward gets its own ADR (see the new constraint
  in `CLAUDE.md` and the `write-adr` skill) instead of being buried in a design doc's
  prose.
- Adds one more artifact type to review before commit (per the project's existing
  issue-first, human-approved review discipline), which is a small but real tax on
  every future architectural decision.

