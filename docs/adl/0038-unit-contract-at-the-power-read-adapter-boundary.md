# ADR-0038: Unit contract at the power-read adapter boundary — convert known units, assume-and-warn when absent, reject a present non-power unit; except `monthly_peak_external`, where an absent unit is rejected too

Date: 2026-09-11
Status: Accepted

## Context

Every power-valued adapter role is documented in `entity-catalog.md` with a unit — `net_power`
W, `charger_power` W, `solar_power` W, `monthly_peak_external` kW — and every consumer computes
on that assumption. Nothing enforces it.

Three of those four roles are wired to `NumericReadAdapter`, which returns `float(state.state)`:
the mapped entity's raw native value, with no unit inspection. The config flow accepts any
`sensor` entity for each of them, with no unit or `device_class` filter. A user mapping a
kW-reporting grid meter therefore hands the control cycle a number a thousand times too small,
silently and permanently.

This is not hypothetical. On a live installation the two required roles arrive in *different*
units:

```
net_power:     3.353     (kW)
charger_power: 3705.7    (W)
solar_power:   3598      (W)
monthly_peak_external: 3.439   (kW — correct; the one role that normalises)
```

`baseline_w = net_w - charger_w` then collapses to approximately `-charger_w`, so
`solar_surplus_w` reports the charger's own consumption as solar surplus.

More seriously, that same collapsed `baseline_w` is what R3's clamp measures headroom against:
`headroom_a = floor((effective_peak_limit_kw * 1000 - margin - baseline_w) / voltage)`. With
`baseline_w` about −3700 instead of about −350, the headroom is inflated by roughly 14 A, so
`min(desired, headroom)` never binds and the clamp — the reason CapTar mode exists — stops
limiting anything. Grid-safety headroom (C4) and R10 smoothing take the same mis-scaled value.

The mis-scaled `net_w` *also* reaches the Peak-Demand Tracker, which then tracks a ~3 W monthly
peak instead of ~3 kW — but that error pulls the other way: `resolve_effective_peak_limit` returns
`min(max(~0, peak_floor_kw), max_peak_kw)`, i.e. the peak floor, a *tighter* limit than a correct
tracker would produce. It is worth being precise about this, because the two effects partly cancel
and only one of them dominates: the inflated headroom (~14 A) outweighs what the floored limit
removes (~6.5 A), so the net direction is permissive. The clamp is inert because of `baseline_w`,
not because the tracked peak is small.

The forces in tension:

- **Silence is the worst outcome.** The defect produced no fault, no log line and no visibly
  broken entity — only a plausible wrong number on a dashboard. Whatever is decided must fail
  louder than this did.
- **`net_power` and `charger_power` are required roles.** Under ADR-0007 a required role reading
  `None` is a fault: the coordinator writes 0 A and charging stops. Rejecting a reading is
  therefore not a quiet no-op for these two, the way it is for an optional role.
- **A sensor with no unit attribute is common and usually correct.** Template sensors and many
  integrations expose a bare number. Today those installs work, because the documented contract
  is watts and a bare number is taken as watts.
- **Every mis-scaling here fails permissive, by different routes.** For the W-valued roles a
  kW-as-W misread inflates the clamp's headroom (above). For `monthly_peak_external` a W-as-kW
  misread produces an operand three orders of magnitude too large, which — through
  `resolve_monthly_peak_operand`'s `max(internal, external)` merge and then
  `min(max(operand, floor), max_peak_kw)` — pins the effective peak limit at `max_peak_kw`. So
  direction of failure does not distinguish the roles.
- **`charger_power`'s misread runs the other way, which only strengthens the grouping.** A
  kW-as-W misread there makes `baseline_w` larger, i.e. headroom smaller — the restrictive
  direction. It is grouped with the other two W roles because the absent-unit assumption is
  equally safe there, not because its failure direction matches.
- **What does distinguish them is how likely the documented unit is to be the true one when
  none is reported.** For the three W-valued roles, W is both the documented unit and the
  ordinary one, so assuming it is usually right. For `monthly_peak_external` the documented unit
  is kW, but ADR-0030 records that DSO/smart-meter peak sensors "commonly report in W" — so for
  that one role the assumption is more likely wrong than right. This, not failure direction, is
  the asymmetry the decision below turns on.
- **The asymmetry argument in the existing adapter is not ADR-0030's.**
  `PowerKilowattReadAdapter`'s docstring attributes to ADR-0030 an asymmetry that record does not
  discuss anywhere; the reasoning originates in the implementation spec that followed. Repeating
  the attribution would make a citation authoritative that its source does not support.

ADR-0030 does not settle the general rule. It decided one optional role and explicitly deferred
the contract: its Consequences state that "a unit contract for the reading — DSO/smart-meter peak
sensors commonly report in W, so the adapter (or its config-flow mapping) must normalize to kW
before the value reaches the coordinator; this is an implementation-spec obligation this ADR
surfaces but does not itself resolve." `PowerKilowattReadAdapter` is an artifact of the
implementation spec that followed, not of that record. Extending its strictness to the required
roles by precedent alone would settle, by accident of which adapter was written first, a contract
that users' existing configurations depend on.

Note the parenthetical inside that quote: ADR-0030 states that DSO peak sensors **commonly report
in W**, while the role's documented unit is kW. That role's likely mis-mapping therefore runs the
opposite way to the other three, which matters below.

## Considered options

### Option A — Status quo: document a watts-only contract, enforce nothing

Keep `NumericReadAdapter` on the power roles and treat a correct mapping as the user's
responsibility, stated in the config-flow strings and `entity-catalog.md`.

- Pro: no code change, no migration risk, and no possibility of a previously-working
  installation faulting after an upgrade.
- Con: leaves the live defect unfixed. The failure mode is silent and indefinite — a mis-mapped
  install never recovers on its own, and the user has no signal short of noticing an implausible
  dashboard number, which is how the mismatch above went unnoticed until a user questioned a
  surplus reading.

### Option B — Strict rejection: any non-power unit, including absent, reads as `None`

Apply `PowerKilowattReadAdapter`'s existing behaviour (in W) to all four power roles.

- Pro: one rule, already implemented and tested for `monthly_peak_external`; no silently wrong
  value can ever reach the control cycle; and for `monthly_peak_external` specifically it is the
  only option that cannot saturate the peak limit.
- Con: turns a working installation into a faulting one on upgrade. For `net_power` and
  `charger_power` — both required — a unitless sensor stops charging entirely under ADR-0007,
  for a mapping that was correct all along and produced correct behaviour. It punishes the
  common, usually-right case in order to catch the rare wrong one.

### Option C — Convert known units; assume watts and warn when absent; reject a present non-power unit

Inspect `unit_of_measurement`. A recognised power unit is converted to the role's documented
unit. An absent unit keeps today's behaviour — taken as the documented unit — and logs a warning
naming the entity and the assumption. A unit that is present but not a power unit (`%`, `A`,
`°C`) reads as `None`, because it is positive evidence the mapping is wrong.

- Pro: fixes the live defect for every install that reports a unit, which is the case that
  actually broke; leaves every currently-working install working; and still fails loudly on the
  one signal that unambiguously indicates a mis-mapping. The warning gives the silent case a
  voice without making it fatal.
- Con: a unitless sensor genuinely reporting kW stays silently wrong — the assumption is only as
  good as the documentation it rests on. Diverges from `PowerKilowattReadAdapter`'s behaviour,
  so either that adapter changes or two power adapters coexist with different rules for the same
  input. Introduces a log line the user must actually read.

### Option D — Option C plus a config-flow selector filtered to `device_class: power`

As C, and additionally constrain the entity pickers so a non-power entity cannot be mapped.

- Pro: moves the failure from runtime to configuration time, where the user is present and can
  act; the strongest end state for new installations.
- Con: does nothing for entries already mapped before the filter existed, which is every
  affected install today — so it cannot replace the adapter-side rule, only supplement it. A
  `device_class` filter also excludes otherwise-valid template sensors that set a unit but no
  device class, narrowing what a user may legitimately map.

### Option E — Option C for the three W-valued roles, Option B for `monthly_peak_external`

As C, except that `monthly_peak_external` keeps strict rejection of an absent unit.

- Pro: keeps assume-and-warn where its failure mode is bounded, and strict rejection on the one
  role where an absent unit's likely true value (W, per ADR-0030) read as the documented unit
  (kW) pins the effective peak limit at `max_peak_kw` — defeating row 2 of the resolution and
  leaving only the urgency ceiling, which is the outcome this record exists to prevent. It is
  also the status quo for that role, so it breaks nothing that works today.
- Con: for a unitless sensor that genuinely reports kW — a `utility_meter` or `statistics`
  helper, a common HA shape — E discards the reading entirely. The role goes absent and the
  external input is silently lost, so the under-reporting gap ADR-0030 exists to close stays open
  for that install. This is precisely the cost Option B's Con condemns ("punishes the common,
  usually-right case"), adopted here for one role. And two rules at one boundary is what Option
  C's Con warned against: a future reader must know which role they are looking at, so the split
  is defensible only while the reason for it stays written down.

## Decision

**Option E.** Power-read adapters convert a recognised power unit to the role's documented unit,
assume the documented unit with a warning when no unit is present, and read `None` when a unit is
present but is not a power unit — except for `monthly_peak_external`, where an absent unit is
also rejected.

There are two distinct warnings, and the carve-out needs both named or it recreates this
record's own headline force — silence — for the role it carves out:

- **Assumption warning** (the three W-valued roles): "no unit reported; assuming W". The reading
  is used.
- **Rejection warning** (`monthly_peak_external`): "no unit reported; reading discarded". The
  reading is *not* used, and the role behaves as absent — but it says so, rather than vanishing
  indistinguishably from an unmapped role.

Both are emitted once per entity per config-entry load, not per read. The control cycle reads
every role every cycle, so a per-read warning would be log spam that trains the user to ignore
exactly the signal these exist to provide.

The deciding trade-off is between B's and C's costs, and they are not symmetric. B's cost falls
on installations that are correct today and would stop charging after an upgrade; C's cost falls
on installations that are already silently wrong and stay wrong, but which C now warns about.
E takes C's side of that trade for the three roles where it holds, and B's side for the one where
it does not.
Option A's "no migration risk" Pro is real, but it buys that by leaving the clamp unable to bind,
which is the defect itself. D's configuration-time guard is the better *long-term* shape and is not
rejected on its merits — it simply cannot reach entries that already exist, which is the entire
affected population, so it is recorded as follow-up rather than part of this contract.

The rejection of a *present* non-power unit is kept from B for every role, because it is the one
case where the reading is positive evidence of a mis-mapping rather than an absence of evidence.
Absence of a unit is not evidence of a wrong unit — which is why the absent case is treated
differently at all, and why the one role whose likely absent-unit value is *known* to differ from
its documented unit is carved out of that leniency.

`PowerKilowattReadAdapter` therefore keeps its absent-unit behaviour and its existing rejection
of a present non-power unit, gaining only the rejection warning. An earlier draft of this record
brought it fully under the uniform rule, reasoning that a warning is strictly more information
than silent absence. That was
wrong: for this role "assumed kW" turns a W-reporting sensor into a peak operand three orders of
magnitude too large, pinning the effective peak limit at `max_peak_kw` — strictly worse than the
`None` it replaced, which had no effect on the limit at all.

**On ADR-0032, which already weighed this exposure.** The saturation argument above is only
reachable because ADR-0032 chose `max(internal, external)` as the merge, and that record
explicitly considered this scenario — "a bad external reading can raise the effective peak limit
as high as `maximum peak` for as long as it persists" — and accepted it, "because `maximum peak`
is itself the ceiling the system is otherwise willing to charge to under deadline urgency (row
1)". That reasoning is not disputed here and the merge rule is untouched. What differs is where
the two records stand: ADR-0032 accepted a *consequence* it could not remove without giving up
the merge's benefits, whereas this decision can remove one *cause* of it at no cost beyond a
reading the system never had. Accepting an exposure downstream is not a reason to manufacture it
upstream. A reader who disagrees should weigh both records, which is why this one names it.

This ADR supersedes neither ADR-0030 nor ADR-0032. ADR-0030's decision was to introduce the role;
ADR-0032's was the merge precedence. Neither is reversed — this record settles the unit handling
ADR-0030 explicitly declined to settle, for that role and the other three. It extends ADR-0003's
adapter boundary, whose "adapter translates in one direction, raw -> canonical" is the existing
warrant for putting conversion in the adapter rather than in the coordinator.

## Consequences

**Blast radius** — every site this decision governs today, and whether each conforms.
`grep -n "Numeric.*Adapter(\|PowerKilowattReadAdapter(" adapters/factory.py` returns ten role
wirings, of which four are power-valued. The wildcard matters: `NumericReadWriteAdapter`
subclasses `NumericReadAdapter` and inherits the identical unitless `float(state.state)` read, but
a literal `NumericReadAdapter(` pattern does not match it — an enumeration keyed on the narrower
string silently drops two roles.

| Role | Adapter today | Documented unit | Conforms? |
|---|---|---|---|
| `net_power` | `NumericReadAdapter` | W | **No** — required role, the live defect |
| `charger_power` | `NumericReadAdapter` | W | **No** — required role, the live defect |
| `solar_power` | `NumericReadAdapter` | W | **No** — optional, diagnostic-only today |
| `monthly_peak_external` | `PowerKilowattReadAdapter` | kW | Nearly — already converts and already rejects both an absent and a present non-power unit; the only gap is that it rejects *silently*, with no rejection warning |

The remaining six wirings read through the same unitless path and are **out of scope of this
ADR**, keeping their current behaviour: `grid_voltage` (V), `ev_soc` (%),
`ev_battery_capacity` (kWh) and `solar_forecast` (kWh) via `NumericReadAdapter`, plus
`charger_current` (A) and `vehicle_charge_limit` (%) via `NumericReadWriteAdapter`. They carry
the same class of hazard and each would need its own unit set decided — and for the two
read/write roles, a written value's unit as well as a read one's. That is named as follow-up
below, not silently assumed to follow from this record.

**Follow-up this creates:**

- Implementation work for the three non-conforming W-valued roles. For
  `monthly_peak_external` the only change is adding the rejection warning —
  `PowerKilowattReadAdapter` already implements the rest of its half of this contract, which is
  why Option E costs so little to adopt.
- Correct `PowerKilowattReadAdapter`'s own docstring while changing it: it currently attributes
  the asymmetry argument to ADR-0030, which does not contain it. Leaving that in place would keep
  the unsupported citation alive in the one place a future reader is most likely to trust it.
- A new issue for the config-flow selector guard (Option D), which this ADR records as the right
  long-term shape but does not adopt now.
- A new issue for the non-power numeric roles above, deciding whether the same contract extends
  to them and with which unit sets.
- ADR-0021's `sensor.smart_charging_adapter_readings` surfaces each wired read role's most
  recently read value. After this decision those values are normalised rather than raw for any
  entity reporting a convertible unit, so the diagnostic answers "what the control cycle used",
  not "what the source entity said". That is the more useful reading for diagnosing a mis-mapping,
  but it is a change of meaning and the catalog should say so.
- `entity-catalog.md`'s unit column for the four power roles should state that the value is
  normalised at the adapter and assumed to be the stated unit when the source reports none. It
  should not stop expressing a source-side expectation altogether: the absent-unit fallback is
  precisely an assumption about the source, and would have nothing to rest on without it.

**What becomes harder:** a role's unit is now part of its adapter's contract, so adding a
power-valued role means deciding its unit set rather than defaulting to "whatever the entity
says". That is the intended cost.

**What this does not do:** it makes no claim about *test* coverage for the contract. That the
mandated adapter cases (ADR-0009) test four states of presence and none of meaning is a separate
gap, tracked separately — and it must be settled by its own ADR extending ADR-0009, not inferred
from this one. A conforming adapter under this record could still ship with no unit test at all.
