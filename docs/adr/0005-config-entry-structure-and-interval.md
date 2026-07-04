# ADR-0005: Config entry structure and control interval

Date: 2026-07-04
Status: Accepted

## Context

This is backfilled from Decision 4 of `docs/plans/2026-07-04-integration-architecture-design.md`
(PR #30, still open — see ADR-0001's plan to give each of that doc's decisions its own
ADR before #30 merges, and ADR-0002's Consequences, which reserves ADR-0005 for this
decision).

Home Assistant config entries split persisted integration state into two buckets:
**data** (set at initial setup, changed only via a reconfigure flow, not live-editable
by the user without going through that flow) and **options** (changeable at any time via
Settings -> Integrations -> Configure, without a reconfigure flow, and without
necessarily reloading the entry unless the integration's options-update listener
requests a reload). The integration has several kinds of persisted state that need to be
placed into one bucket or the other:

- Entity-role mappings (which HA entity plays which role, e.g. "EV charger current
  setpoint", "solar production sensor") and state-translation tables (e.g. mapping a
  charger's raw state strings to the integration's own state model) — read by the
  adapter layer, expected to be defined by ADR-0003 (not yet accepted at the time of
  writing; if its final shape differs, that ADR's own Consequences call for revisiting
  cross-references such as this one).
- Declared capabilities (R18), e.g. whether solar production is present at all, which
  determines whether solar-dependent modes are even offered.
- Thresholds and defaults with numeric or enumerated values: start thresholds, safety
  margin, grace periods, the smoothing window size N.
- The control interval — how often the coordinator polls and re-evaluates.

ADR-0004 already decided, for a different but related question, which pieces of
integration state are exposed as HA-owned entities (`number`, `select`, etc., which the
user can change from the dashboard without opening Configure) versus which are not
exposed as entities at all and instead live only in the config entry. That decision
governs *whether something is an entity*; this decision governs, for the state that
ADR-0004 leaves *out* of the owned-entity list, where in the config entry it lives
(data vs. options), plus the specific question of whether the control interval
should have been an owned entity in the first place. The two decisions are adjacent but
distinct: a setting could in principle be both a config-entry value and mirrored as an
entity (ADR-0004 rejected that duplication for the settings in scope here), and a
config-entry value still needs a data/options placement regardless.

The forces at play:

- Remapping which physical entity plays which role, or changing a state-translation
  table, while the coordinator is mid-cycle is exactly the kind of change that is unsafe
  to apply silently — the adapter layer (ADR-0003) resolves roles to entities once and
  assumes that mapping is stable for the life of a control cycle, and getting it wrong
  (e.g. two roles briefly pointing at the same entity) risks writing to the wrong
  hardware entity, which is a safety-relevant guarantee this integration cannot regress.
- Thresholds and the control interval, in contrast, are “turn the dial” tuning
  values a user reasonably expects to adjust repeatedly without re-running setup, similar
  to how most HA polling integrations expose their update interval.
- HA's own config entry model already distinguishes data from options for exactly this
  kind of setup-time-vs-anytime split, so the question is which of this integration's
  values map to which bucket, not whether to invent a new mechanism.

## Considered options

### Option A — Entity-role mappings, state-translation tables, and declared capabilities in config entry data (reconfigure-flow only); thresholds, defaults, and the control interval in config entry options (Configure, anytime)

- Pro: Matches the risk profile of each value — mapping/capability changes go through a
  reconfigure flow that can re-validate the whole entity graph before committing, while
  tuning values change instantly with no re-validation needed because no adapter
  resolution is affected.
- Pro: Keeps ADR-0003's assumption intact — adapters resolve role mappings once per
  reload, and only a reconfigure flow (which itself triggers a reload) can change them.
- Con: Two buckets to reason about instead of one; a contributor adding a new persisted
  setting has to decide, each time, which bucket it belongs in, and the wrong choice
  (e.g. putting a mapping in options) would silently reintroduce the live-remapping risk
  this decision exists to avoid.

### Option B — Everything in config entry options; no reconfigure flow, only a single Configure flow

- Pro: One bucket, one flow to build and maintain; simpler config-flow code, fewer
  concepts for a new contributor to learn.
- Con: Entity-role mappings and state-translation tables would then be changeable at any
  time without the safeguards a reconfigure flow provides (e.g. re-validating that every
  role still resolves to a real entity before accepting the change), while the
  coordinator could be mid-cycle — exactly the "unsafe, surprising live remap" this
  decision needs to rule out, and it would contradict ADR-0003's assumption that role
  resolution is stable for a reload's lifetime.

## Decision

Option A. Config entry **data** holds entity-role mappings, state-translation tables, and
declared capabilities (R18) — set at initial setup, changed only via a reconfigure flow.
Config entry **options** holds thresholds and defaults (start thresholds, safety margin,
grace periods, smoothing window N) and the control interval — changeable at any
time via Settings -> Integrations -> Configure.

The control interval specifically is a fixed options-flow setting, not an owned entity.
ADR-0004's owned-entity list is scoped to entities that describe charging state or a
user-facing charging preference (active profile/mode, SoC override, departure time, WFH
status, diagnostic readouts) — the control interval is neither; it configures the
coordinator's own polling behavior, so it has no natural place among the `number`/`select`
entities ADR-0004 lists, and this ADR is the one making that placement decision, not
ADR-0004. It is also conventional: most HA polling coordinators expose their update
interval as an options-flow setting rather than an entity, so following that precedent
keeps the integration unsurprising to HA users and developers already familiar with the
pattern.
Changing the interval in options triggers an options-update listener that reloads the
config entry, restarting the coordinator with the new interval — there is no live
"change interval without reload" path, since the coordinator's polling loop is
established at reload time.

## Consequences

- The config flow implementation needs two distinct flows: an initial `async_step_user`
  plus `async_step_reconfigure` (data) and a separate options flow (options) — not a
  single flow, and not options-only as Option B would have allowed.
- Any future setting must be classified at the time it is added: does changing it need to
  re-validate entity/role resolution (data, reconfigure-only) or not (options, anytime)?
  This ADR's Option A trade-off (Con) means that classification step doesn't disappear —
  it needs to be called out explicitly in the write-adr/development workflow so a new
  setting isn't dropped into options by default without checking against ADR-0003's
  stability assumption.
- The options-update listener must call `async_reload` when the control interval
  (or any other option) changes, per HA's standard options-flow pattern — this is a
  concrete implementation task for whichever ADR/issue covers the config-flow build-out.
- This ADR does not decide the config flow's step layout, schema validation details, or
  how the reconfigure flow re-validates entity/role resolution — those remain
  implementation detail for the development work that follows, informed by ADR-0003 and
  ADR-0004.
