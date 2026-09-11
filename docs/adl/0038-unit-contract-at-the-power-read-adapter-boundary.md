# ADR-0038: Unit contract at the power-read adapter boundary — convert known units, assume-and-warn when absent, reject a present non-power unit

Date: 2026-09-11
Status: Proposed

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
`solar_surplus_w` reports the charger's own consumption as solar surplus. More seriously,
`net_w` also feeds the Peak-Demand Tracker, which tracks a ~3 W monthly peak instead of ~3 kW,
so R3's billing-protection clamp — the reason CapTar mode exists — is inert on any installation
whose grid meter reports kW. Grid-safety headroom (C4) and R10 smoothing take the same
mis-scaled value.

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
- **Guessing wrongly is asymmetric, and the asymmetry differs per role.** For `net_power`,
  reading a kW value as W understates it, which *widens* the peak clamp — the permissive
  direction. For `monthly_peak_external` the direction reverses: reading a W value as kW
  produces a huge operand, and since the effective peak limit resolves as
  `min(max(monthly_peak, floor), max_peak_kw)`, it saturates at `max_peak_kw` — also fully
  permissive, but reached the opposite way. `PowerKilowattReadAdapter`'s own docstring reasons
  from this asymmetry; ADR-0030 itself does not, and attributing the argument to that record
  rather than to the implementation would be a citation the record does not support.

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
  (kW) saturates the effective peak limit at `max_peak_kw` — disabling the clamp outright, the
  same outcome this ADR exists to prevent. It is also the status quo for that role, so it breaks
  nothing that works today.
- Con: two rules at one boundary, which is exactly what Option C's Con warned against; a future
  reader must know which role they are looking at. The split is defensible only while the reason
  for it stays written down, which makes this record load-bearing rather than merely informative.

## Decision

**Option E.** Power-read adapters convert a recognised power unit to the role's documented unit,
assume the documented unit with a warning when no unit is present, and read `None` when a unit is
present but is not a power unit — except for `monthly_peak_external`, where an absent unit is
also rejected.

The warning is emitted once per entity per config-entry load, not per read. The control cycle
reads every role every cycle, so a per-read warning would be log spam that trains the user to
ignore exactly the signal this option exists to provide.

The deciding trade-off is between B's and C's costs, and they are not symmetric. B's cost falls
on installations that are correct today and would stop charging after an upgrade; C's cost falls
on installations that are already silently wrong and stay wrong, but which C now warns about.
E takes C's side of that trade for the three roles where it holds, and B's side for the one where
it does not.
Option A's "no migration risk" Pro is real, but it buys that by leaving the clamp disabled, which
is the defect itself. D's configuration-time guard is the better *long-term* shape and is not
rejected on its merits — it simply cannot reach entries that already exist, which is the entire
affected population, so it is recorded as follow-up rather than part of this contract.

The rejection of a *present* non-power unit is kept from B for every role, because it is the one
case where the reading is positive evidence of a mis-mapping rather than an absence of evidence.
Absence of a unit is not evidence of a wrong unit — which is why the absent case is treated
differently at all, and why the one role whose likely absent-unit value is *known* to differ from
its documented unit is carved out of that leniency.

`PowerKilowattReadAdapter` therefore keeps its absent-unit behaviour, gaining only the warning
and the present-non-power-unit rule. An earlier draft of this record brought it fully under the
uniform rule, reasoning that a warning is strictly more information than silent absence. That was
wrong: for this role "assumed kW" turns a W-reporting sensor into a peak operand three orders of
magnitude too large, saturating the effective peak limit and disabling the clamp — strictly worse
than the `None` it replaced, and the same failure this record exists to prevent.

This ADR does not supersede ADR-0030. ADR-0030's decision was to introduce the role and merge it
into the effective-peak-limit resolution; its unit handling was an implementation consequence it
explicitly declined to settle. This record settles it, for that role and the other three.

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
| `monthly_peak_external` | `PowerKilowattReadAdapter` | kW | Partially — converts, but rejects an absent unit instead of warning |

The remaining six wirings read through the same unitless path and are **out of scope of this
ADR**, keeping their current behaviour: `grid_voltage` (V), `ev_soc` (%),
`ev_battery_capacity` (kWh) and `solar_forecast` (kWh) via `NumericReadAdapter`, plus
`charger_current` (A) and `vehicle_charge_limit` (%) via `NumericReadWriteAdapter`. They carry
the same class of hazard and each would need its own unit set decided — and for the two
read/write roles, a written value's unit as well as a read one's. That is named as follow-up
below, not silently assumed to follow from this record.

**Follow-up this creates:**

- Implementation work for the three non-conforming W-valued roles, and bringing the fourth
  (`monthly_peak_external`, via `PowerKilowattReadAdapter`) under the warning and the
  present-non-power-unit rule while leaving its absent-unit rejection intact.
- A new issue for the config-flow selector guard (Option D), which this ADR records as the right
  long-term shape but does not adopt now.
- A new issue for the non-power numeric roles above, deciding whether the same contract extends
  to them and with which unit sets.
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
