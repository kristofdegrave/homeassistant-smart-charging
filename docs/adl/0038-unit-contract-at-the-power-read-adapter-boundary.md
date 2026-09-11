# ADR-0038: Unit contract at the power-read adapter boundary

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
- **Guessing wrongly is asymmetric, and the asymmetry differs per role.** Reading a kW value as
  W understates `net_w`, which *widens* the peak clamp — the permissive direction. Reading a W
  value as kW would narrow it. ADR-0030 reasoned about exactly this asymmetry for
  `monthly_peak_external` and chose against the permissive mistake.

ADR-0030 does not settle the general rule. It introduced `PowerKilowattReadAdapter` for one
optional role and explicitly deferred the contract: its Consequences state that a unit contract
for the reading "is an implementation-spec obligation this ADR surfaces but does not itself
resolve." Extending that adapter's strictness to the required roles by precedent alone would
settle, by accident of which adapter was written first, a contract that users' existing
configurations depend on.

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
  value can ever reach the control cycle; consistent with ADR-0030's stated reasoning about the
  asymmetric mistake.
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

## Decision

**Option C.** Power-read adapters convert a recognised power unit to the role's documented unit,
assume the documented unit with a warning when no unit is present, and read `None` when a unit
is present but is not a power unit.

The deciding trade-off is between B's and C's costs, and they are not symmetric. B's cost falls
on installations that are correct today and would stop charging after an upgrade; C's cost falls
on installations that are already silently wrong and stay wrong, but which C now warns about.
Option A's "no migration risk" Pro is real, but it buys that by leaving the clamp disabled, which
is the defect itself. D's configuration-time guard is the better *long-term* shape and is not
rejected on its merits — it simply cannot reach entries that already exist, which is the entire
affected population, so it is recorded as follow-up rather than part of this contract.

The rejection of a *present* non-power unit is kept from B, because it is the one case where the
reading is positive evidence of a mis-mapping rather than an absence of evidence. This is the
same asymmetry ADR-0030 reasoned from, applied one step more narrowly: absence of a unit is not
evidence of a wrong unit.

`PowerKilowattReadAdapter` is brought under this rule rather than left as a second, stricter
regime, so there is one contract per boundary rather than one per role. That changes
`monthly_peak_external`'s behaviour for a unitless sensor from "absent" to "assumed kW, warned" —
acceptable because it is an optional role whose absence already degrades silently, so the
warning is strictly more information than before.

This ADR does not supersede ADR-0030. ADR-0030's decision was to introduce the role and merge it
into the effective-peak-limit resolution; its unit handling was an implementation consequence it
explicitly declined to settle. This record settles it, for that role and the other three.

## Consequences

**Blast radius** — every site this decision governs today, and whether each conforms.
`grep -n "NumericReadAdapter(\|PowerKilowattReadAdapter(" adapters/factory.py` returns eight
role wirings, of which four are power-valued:

| Role | Adapter today | Documented unit | Conforms? |
|---|---|---|---|
| `net_power` | `NumericReadAdapter` | W | **No** — required role, the live defect |
| `charger_power` | `NumericReadAdapter` | W | **No** — required role, the live defect |
| `solar_power` | `NumericReadAdapter` | W | **No** — optional, diagnostic-only today |
| `monthly_peak_external` | `PowerKilowattReadAdapter` | kW | Partially — converts, but rejects an absent unit instead of warning |

The remaining four wirings are non-power `NumericReadAdapter` roles (`grid_voltage` V,
`ev_soc` %, `ev_battery_capacity` kWh, `solar_forecast` kWh) and are **out of scope of this
ADR** and keep their
current behaviour. They carry the same class of hazard and each would need its own unit set
decided; that is named as follow-up below, not silently assumed to follow from this record.

**Follow-up this creates:**

- Implementation work for the three non-conforming power roles, bringing
  `PowerKilowattReadAdapter` under the same rule.
- A new issue for the config-flow selector guard (Option D), which this ADR records as the right
  long-term shape but does not adopt now.
- A new issue for the non-power numeric roles above, deciding whether the same contract extends
  to them and with which unit sets.
- `entity-catalog.md`'s unit column for the four power roles should state that normalisation
  happens at the adapter, rather than reading as a requirement on the source entity.

**What becomes harder:** a role's unit is now part of its adapter's contract, so adding a
power-valued role means deciding its unit set rather than defaulting to "whatever the entity
says". That is the intended cost.

**What this does not do:** it makes no claim about *test* coverage for the contract. That the
mandated adapter cases (ADR-0009) test four states of presence and none of meaning is a separate
gap, tracked separately — and it must be settled by its own ADR extending ADR-0009, not inferred
from this one. A conforming adapter under this record could still ship with no unit test at all.
