# Notifications — design

**Date:** 2026-07-21
**Status:** draft (issue #275, epic #257)
**Type:** implementation design (a slice of the approved architecture — not a new decision)

This document defines the **Notifications** build slice: **RA4** (Notification access, Resource
Access V11) and **M3** (Notification Manager, V11) — the evening home-day prompt (UC08) and
delivery of R5's deadline-unreachable notice.

It is a deliberate **subset** of the full architecture, built the same way the Power MVP and the
Captar slice were: every component below is a slice of a service already named in
[`../design/system-design.md`](../design/system-design.md) §3 and sequenced in
[`../design/project-plan.md`](../design/project-plan.md) (RA4, M3, Phase 3 checkpoint). Nothing
here introduces a new service, call direction, or structural decision. RA4 reuses the ADR-0003
adapter-role protocol as a role extension (an extension ADR-0003 explicitly anticipates — like RA2
and RA3, it needs **no new ADR**, and this document says so explicitly in §6). M3's cross-Manager
coordination follows the already-Accepted **ADR-0011** (G-ADR-0011, resolved).

Behavior is owned by
[UC08](../analysis/use-cases/UC08-plan-tomorrow-home-day.md) (evening home-day prompt, R13);
this document cites its state model, triggers, and thresholds as test anchors and does **not**
restate them as if it owns them. Where an anchor and its source doc disagree (see §9's open
questions), the source doc wins (`project-plan.md` §1).

---

## 0. Relationship to prior slices and to the Deadline Engine (E4)

The shipped code today is the Power MVP + Solar/SolarOnly + Captar slices: `coordinator.py` (M1),
`engines/` (E3/E5/E6/E7/E8 + `soc_target`), `modes/`, `adapters/` (RA1 roles:
`charger_current`, `charger_status`, `net_power`, `charger_power`, `grid_voltage`, `ev_soc`),
`select.py`/`number.py`/`sensor.py` (C2/C3), `config_flow.py` (C4), `__init__.py`. There is **no
`managers/` package** — M1 lives directly at the package root in `coordinator.py`. This slice
follows that same convention: M3 is a package-root module (`notification_manager.py`), mirroring
`coordinator.py`, per ADR-0002's layout (which reserves root modules and names no `managers/`
home). See §10.

**This slice's one real cross-slice dependency is on the Deadline Engine (E4, epic #255).** E4 owns
`DeadlineUnreachableNotified` — the one output this slice references — currently **unbuilt** (E4's
spec is drafted in PR #273, not merged as of this writing — `engines/deadline.py` does not exist and
the coordinator publishes no `DeadlineUnreachableNotified` event; confirmed against the current tree):

**`DeadlineUnreachableNotified`** (the ADR-0011 published event) is consumed by the **R5-delivery**
task. This is the **one task in this plan gated on E4/M1**: its subscription handler can be
unit-tested now by firing a synthetic event on the HA bus, but the real end-to-end path depends
on M1 actually publishing it. It is written as the **last** implementation task (Phase 6), and
its "before you start" check is: *does the coordinator publish `DeadlineUnreachableNotified` as a
bus event yet, and under what concrete signal name/payload?* (that name is owned by E4's spec —
this slice matches it, it does not invent it).

Every other task (RA4, UC08, the supporting Resource-Access roles and owned entities) has **no** E4
dependency and is built and tested first.

---

## 1. Why this slice is wider than "just the Manager"

M3 composes services and Resource-Access roles that the shipped code does not have yet. Each is a
named `project-plan.md` service; this slice builds the minimal, mechanical slice of each that M3
consumes, following the Captar slice's **"extend if it exists, create if it doesn't"** rule (§10).

| M3 (UC08) needs | Shipped status | This slice |
| --- | --- | --- |
| Reach the HA `notify` domain, send actionable messages, capture responses (RA4, V11) | Absent | **In scope** — `adapters/notify.py`, new role (§4/§6) |
| `solar_forecast`, `home_day_external` read roles (RA2, V1) | Absent | **In scope** — factory extension, create-if-not (§4) |
| Home-day flag as owned state, written on "yes" (C2; `switch.smart_charging_home_day`) | Absent (no `switch.py`) | **In scope** — create-if-not (§4/§7) |
| `charger_status` read role (RA1) | Shipped | **Reused unchanged** |
| `DeadlineUnreachableNotified` event (E4/M1 publish) | Absent (epic #255) | **Gated last task** (§0/§9) |

§8 lists what is explicitly deferred.

---

## 2. Success criteria (what "works" means)

Each is concrete and testable against the HA harness (or plain pytest for the pure pieces, §9):

1. **RA4 send.** With a `notify`-domain entity mapped to the notification-target role, the adapter's
   `write(payload)` calls `notify.send_message` against that entity with the message and title, and —
   when the payload carries actions — the actionable action buttons (§6).
2. **RA4 response capture.** After a `mobile_app_notification_action` event fires carrying the tag of
   the **most recently sent actionable** notification, the adapter's `read()` returns that action id
   (e.g. `HOMEDAY_YES`); a response carrying a **stale** tag (from a previously sent notification)
   makes `read()` return `None`, never the stale value (§6).
3. **UC08 prompt.** With the evening prompt enabled (`sc_evening_prompt_enabled`, default on), the
   next-day forecast above threshold (`sc_solar_forecast_threshold_kwh`, default 12 kWh — the same
   threshold R9 uses), no external source having set tomorrow's home-day flag, and the car connected
   at home at/after `sc_evening_prompt_time` (default 18:00) before midnight, M3 sends **one**
   actionable yes/no notification (UC08 Not-sent→Pending).
4. **UC08 answer.** A `HOMEDAY_YES` response before midnight sets the home-day flag for tomorrow
   (Pending→Answered-yes); `HOMEDAY_NO` (Answered-no) or midnight with no answer (Timed-out) leaves
   it unset (UC08 state model). Each terminal state is reached at most once per evening; the lifecycle
   re-arms to Not-sent at the midnight date rollover.
5. **UC08 skips.** No prompt when the prompt is disabled, the forecast is at/below threshold, an
   external source already set the flag, or the car never connects before midnight (UC08 1a/1b/1c).
6. **R5 delivery** *(gated — §0/§9)*. On the subscribed `DeadlineUnreachableNotified` event, M3
   delivers the deadline-unreachable notice via RA4.

---

## 3. Install-time / options additions

Extends the config/options flow (ADR-0005 data/options split retained; ADR-0003 role mapping for the
notify target). The prompt tuning values are **catalogued** in
[`entity-catalog.md`](../analysis/entity-catalog.md)'s "Notification configuration" table — this
slice cites those ids and defaults; it does not re-derive or rename them.

**Realization note (consistent with prior slices).** The catalog lists these as
`input_number.sc_*` / `input_boolean.sc_*` / `input_datetime.sc_*` helper-style ids. Every
install-time threshold the Power/Captar slices actually shipped is realized as **config-entry
data/options with a `CONF_*` constant + a config-flow field** (ADR-0005), *not* as HA `input_*`
helper entities — and `project-plan.md`'s G-NAMING row explicitly scopes the `sc_`-prefixed helper
rows as a *separate, deferred* catalog-reconciliation concern. This slice therefore realizes the
notification tuning values the same ADR-0005 way as every other threshold, keeping the catalog ids as
the analysis-layer names. (This is the mechanism precedent, not a new decision — see §9's open
question on the catalog-vs-ADR-0005 naming.)

**Bucket note.** `entity-catalog.md` classifies `sc_evening_prompt_enabled`, `sc_evening_prompt_time`,
**and** `sc_solar_forecast_threshold_kwh` as **install-time** (its "Notes" section groups
`sc_evening_prompt_enabled` explicitly among the "set once and rarely revisited" install-time
choices). This slice realizes all three as **options** instead, matching the "runtime-tunable
threshold" bucket the Power/Captar slices used for comparable values — behaviorally harmless (options
are editable anytime from the HA UI, a superset of install-time editability), but a real divergence
from the catalog's own bucket, flagged here rather than silently folded into the
ADR-0005-realization precedent above.

| Field | Bucket | Constant / default | Source |
| --- | --- | --- | --- |
| **Notification target** entity (a `notify`-domain entity) | data — required for M3 to deliver at all | `CONF_NOTIFICATION_TARGET_ENTITY = "notification_target_entity"`; role `ROLE_NOTIFICATION_TARGET = "notification_target"` | RA4 (§6); named to match the existing `ROLE_EV_SOC`/`ROLE_CHARGER_STATUS` convention in `const.py` |
| **Evening prompt enabled** | options | `CONF_EVENING_PROMPT_ENABLED`, default **on** | `input_boolean.sc_evening_prompt_enabled`; UC08 precondition |
| **Evening prompt time** | options | `CONF_EVENING_PROMPT_TIME`, default **18:00** | `input_datetime.sc_evening_prompt_time`; UC08 trigger |
| **Solar-forecast threshold** | options | `CONF_SOLAR_FORECAST_THRESHOLD_KWH`, default **12 kWh** | `input_number.sc_solar_forecast_threshold_kwh` (entity-catalog); UC08 precondition 2 (R9's threshold, read independently — UC08 §"Relationships") |
| `solar_forecast`, `home_day_external` entity mappings (data) | data | RA2 roles, create-if-not (§4) | entity-catalog (RA2) |

Config-flow validation for the notify target mirrors ADR-0003's other roles: the mapped entity must
exist and its expected platform must be the **`notify`** domain (HA's newer notify-**entity** platform,
per the human-partner decision — not the legacy notify-service-only style). No config-entry migration
is needed: an entry that predates these keys reads each with its `DEFAULT_*` fallback, the same
pattern the Captar slice established; the notify-target *data* field, being install-time, is validated
in the flow rather than migrated.

**Deliberately not wired: `input_number.sc_prompt_timeout_h` (catalog default 2 h).** UC08's own
"Relationships" section states midnight is the *only* answer deadline and there is **no** separate
configurable timeout. Source doc wins (§9 open question) — this slice does not wire a prompt-timeout
option.

---

## 4. Runtime surface (Resource Access + owned entities)

- **`adapters/notify.py` — `NotifyAdapter`** (RA4, V11). Reuses the ADR-0003 `Adapter` protocol
  (`read()`/`write()`), added to the factory under `ROLE_NOTIFICATION_TARGET`, optional at the
  factory level (only present when the target is mapped), the same shape `ev_soc`/`grid_voltage`
  already use. `write(payload)` sends; `read()` returns the last captured actionable response (§6).
- **RA2 read roles** — `solar_forecast` (kWh), `home_day_external` (bool): factory extensions using
  the existing `NumericReadAdapter` / a boolean-read variant, **create-if-not**. `car_home` is **not**
  built here — entity-catalog attributes it to R12/UC09, not UC08 (UC08's "connected at home" is
  derived from `charger_status` alone, §5); building it would feed the deferred UC10 slice, not this
  one (§8). `departure_external` is likewise **not** built here (it feeds the deferred UC10/E4 R14
  hookup — §8).
- **`switch.smart_charging_home_day`** — owned home-day flag (C2; entity-catalog "Home day" row:
  `off`, resets daily at midnight, R13). New (`switch.py`), **create-if-not**. Written by UC08 on
  "yes"; resets itself to `off` at the midnight date rollover (its own catalogued R13 behavior,
  independent of UC08). Its `wfh` illustrative name in ADR-0004 is superseded by the settled
  `home_day` id (entity-catalog Id note).
- **Not built this slice:** any deadline/departure owned entity; the R5 notice needs no owned
  entity of its own (it is a one-shot delivery on a subscribed event).

---

## 5. Control flow (matches system-design §5.3's sequence diagram)

M3 is driven per control interval by its own periodic tick plus the HA event bus — the
`Timer / cycle / evening time (Client)` participant in system-design §5.3. Each evaluation reads
owned config + the home-day flag from the Store (RA3), reads the adapter roles (RA1/RA2), and
dispatches to one of the §5.3 branches. **This slice implements the UC08 and R5-delivery branches of
that diagram, deferring §5.3's UC10 plug-in-reminder branch to a later slice (§8);** system-design
§5.3 itself (an approved artifact) is unchanged. **"Midnight" is realized as a per-evaluation
wall-clock comparison** (`dt_util.now()` date rollover) — the same mechanism M1 already uses for the
monthly-peak month rollover in `coordinator.py`; **no new HA timer/scheduler primitive is introduced.**

### UC08 branch (evening home-day prompt)
Per §5.3's second `alt` and UC08:

1. Skip entirely (Not-sent, no notification) if the prompt is disabled, `solar_forecast` ≤
   `sc_solar_forecast_threshold_kwh`, or `home_day_external` already set tomorrow's flag (1a/1b).
2. Trigger: the car is `connected`/`charging` at home at/after `sc_evening_prompt_time`, before
   midnight → send the actionable yes/no notification via RA4; Not-sent→Pending (`HomeDayPromptSent`).
3. Capture the response via RA4's `read()`: `HOMEDAY_YES` before midnight → **write the home-day flag**
   (Store, `switch.smart_charging_home_day`) and Pending→Answered-yes (`HomeDaySet`); `HOMEDAY_NO` →
   Answered-no, flag left unset (`HomeDayPromptDeclined`).
4. Midnight with no answer → Timed-out, flag left unset (`HomeDayPromptTimedOut`); car never connected
   before midnight → stays Not-sent (1c). The lifecycle re-arms to Not-sent at the midnight rollover.

### R5-delivery branch *(gated — §0/§9)*
Per §5.3's `else R5 delivery`: M3 **subscribes** to `DeadlineUnreachableNotified` (ADR-0011's one
published event) and, on receipt, delivers the deadline-unreachable notice via RA4. M3 does **not**
re-derive urgency — it consumes the event the Coordinator publishes (ADR-0011 Decision row 1).

---

## 6. RA4 notification adapter (mechanics — ADR-0003 role extension, no new ADR)

RA4 is a **role extension of ADR-0003**, not a new abstraction — the same way RA2/RA3 needed no new
ADR. The notify target is mapped once at config-flow time to a real HA entity in the `notify` domain,
validated like every other role (entity exists; expected platform == `notify`). The adapter class
implements the shared `Adapter` protocol:

- **`write(payload)` — send.** Calls `notify.send_message` against the mapped notify entity with the
  message and title; when the payload is actionable, it includes the action buttons (action ids such
  as `HOMEDAY_YES` / `HOMEDAY_NO`) so a tap fires HA's standard **`mobile_app_notification_action`**
  event (human-partner decision 2 — the standard event mechanism, not a separate
  input_boolean/dashboard-button path). Each actionable send is stamped with a **unique tag/id**,
  which the adapter records as "the current actionable tag." *(Protocol-typing note: the shared
  `Adapter.write` value is annotated `float | str` today; RA4's payload is a small structured object
  — message, title, optional actions, tag — so the practical contract widens to
  `float | str | NotificationRequest`, the same way the status role already narrows `read` to `str`.
  Widening the annotation is a one-line code detail, not a structural decision — no ADR.)*
- **`read()` — last actionable response.** A single `mobile_app_notification_action` event-bus
  listener, registered **once at setup**, records `(tag, action_id)` for each incoming action.
  `read()` returns the recorded `action_id` **only if its tag matches the current actionable tag**
  the adapter last sent; otherwise it returns `None` (no response yet, or the recorded response
  belongs to a superseded notification). **This tag-keying is the guard that a stale response from a
  previous notification is never misread as the current one** — required by success criterion 2 and
  by UC08's per-evening lifecycle (a prior evening's `HOMEDAY_YES` must not resolve tonight's prompt).

This is precisely the adapter-role extension ADR-0003 anticipates ("mapping the remaining
entity-catalog rows … deferred to a follow-up design … will need its own ADR *if it changes this
mapping/adapter mechanism*"). RA4 does **not** change the mechanism — one class per role in
`adapters/`, config-flow entity mapping, `ROLE_*` constant, factory wiring — so **no new ADR is
required**, matching RA2/RA3.

---

## 7. Where M3's logic lives, and the pure/HA split (ADR-0009)

**Pure state machine → plain pytest.** UC08's
Not-sent/Pending/Answered-yes/Answered-no/Timed-out lifecycle is a **pure function of (prior state,
observed inputs, now)** with no I/O — structurally identical to the mode state machines in `modes/`.
Per ADR-0009's split criterion (pure logic with no I/O → plain pytest; only HA-coupled wiring needs
the harness), it is factored into an HA-free module **`notification_state.py`** (package root,
imports no `homeassistant.*`) and unit-tested with plain pytest, test names tracing to UC08
acceptance criteria. This is the right call because the *decision* ("given preconditions + prior
state + now, what is the next prompt state / should the flag be written") is
decidable from plain data; only the *observation* of preconditions and the *effects* (send, write)
touch HA.

**HA-coupled orchestration → HA harness.** `notification_manager.py` (package root, mirroring
`coordinator.py`) holds only the I/O: adapter reads (RA1/RA2/RA4), Store reads/writes (owned config +
home-day flag), `notify` dispatch, the `mobile_app_notification_action` and `DeadlineUnreachableNotified`
subscriptions, and per-evaluation wall-clock sampling. Tested via the HA harness (ADR-0009 — Managers
are HA-coupled), per project-plan M3's "Testable on its own: HA harness". A future `managers/` package
could gather M1/M3; it is not needed now, and this slice does not create one (extend-if-exists).

---

## 8. Deliberately deferred

Out of scope for this slice, each a later slice of `project-plan.md`:

- **UC10 plug-in reminder (R12)** — **deferred to a later slice, not cancelled.** UC10 and R12
  remain valid and approved; they are simply not part of this build slice. This slice therefore builds
  **no** plug-in-reminder de-dup state machine, **no** `binary_sensor.smart_charging_plug_in_reminder`,
  **no** reminder-lead-time (`sc_reminder_lead_h`) option, and **no** `car_home` role (entity-catalog
  attributes `car_home` to R12/UC09, not UC08 — §4); a future slice builds `car_home` when it picks
  UC10 up, alongside its E4/R14 deadline dependency (below). No reader should infer a silent scope
  cut — this is an explicit deferral of an approved feature.
- **Deadline Engine (E4), R14 resolution and the `DeadlineUnreachableNotified` publish** — its own
  epic (#255, PR #273 not merged). R5-delivery is gated on the `DeadlineUnreachableNotified` event
  (§0/§9). This slice builds **no** departure-deadline resolver and **no** `departure_external` role.
- **`Auto` profile / `sc_prompt_timeout_h` wiring** — the prompt-timeout catalog row is not wired
  (§3/§9); midnight is the only deadline (UC08).
- **Vehicle-limit sync (M2, UC09)** — a different Manager; no shared work here.
- **Dashboard (C5, UC11), external-event Client wiring (C6)** — M3's action-event and tick wiring in
  this slice is the minimal in-Manager form; the formal C6 external-event-source Client is deferred.
- **R5's `Auto`-escalation and Billing-Protection ceiling raise** — those are E4/E5 concerns; this
  slice only *delivers* the notice, per UC05's split (system-design §6).

---

## 9. Open questions / genuine gaps (flagged, not silently answered)

1. **No prompt-timeout option is needed — settled, not open.** The entity-catalog "Reminders &
   prompts" row lists a 2-hour `sc_prompt_timeout_h` (R13), but UC08's "Relationships" section states
   midnight is the only answer deadline, with no separate configurable timeout. Per `project-plan.md`
   §1 (source doc wins over an anchor), UC08 is authoritative: this slice wires **no** timeout option
   and times the prompt out at midnight — that part is decided, not a gap. What remains genuinely open
   is only the **analysis-doc discrepancy itself**: the catalog row and UC08 disagree with each other,
   independent of what this slice builds, and should be reconciled via the write-requirement flow —
   this design does not open that reconciliation.
2. **Should the catalog's `input_*`/`sc_` helper-style ids eventually be renamed to match their
   `CONF_*` config-entry realization, or do the two naming layers stay intentionally distinct?**
   **Resolution:** by precedent, not invention — realize the tuning values as config-entry options
   with `CONF_*` constants (§3), as every prior slice did, and keep the catalog ids as analysis-layer
   names for now; this design does not rename them. The renaming question itself is not settled here —
   it is the same deferred `sc_`-helper reconciliation `project-plan.md`'s G-NAMING row already
   records, and stays open until that reconciliation happens.
3. **What concrete HA bus event type/payload will carry `DeadlineUnreachableNotified`?** The
   *domain-event name* `DeadlineUnreachableNotified` is already settled — ADR-0011 keeps it as the one
   published cross-Manager event (its Decision row 1). What is **not** yet fixed is E4's technical
   realization: the actual `hass.bus` event-type string and payload shape the Coordinator will fire
   once E4 (epic #255, PR #273) is merged. Owned by E4's spec, not this design; R5-delivery matches
   whatever E4 lands with rather than inventing a concrete string now (§0's `TODO(E4/#255)`).

---

## 10. Packaging

```text
custom_components/smart_charging/
  const.py                 # + CONF_NOTIFICATION_TARGET_ENTITY, ROLE_NOTIFICATION_TARGET (data);
                            #   + CONF_EVENING_PROMPT_ENABLED, CONF_EVENING_PROMPT_TIME
                            #   (options) + DEFAULT_* ; + RA2 role/CONF constants (create-if-not);
                            #   + home-day flag / home-day prompt action-id constants
  adapters/
    notify.py              # RA4 — new: NotifyAdapter (send + tag-keyed response capture, §6)
    factory.py             # RA1 — extend: wire ROLE_NOTIFICATION_TARGET + RA2 roles (create-if-not)
    numeric.py / base.py   # reuse; note the write-type widening for the notify payload (§6)
  notification_state.py    # M3 pure logic — new: UC08 prompt-lifecycle state machine
                            #   (HA-free, plain pytest — §7)
  notification_manager.py  # M3 — new: orchestration (reads, Store writes, notify dispatch, event subs)
  switch.py                # C2 — new (create-if-not): home-day flag owned entity (R13 midnight reset)
  config_flow.py           # C4 — extend: notify-target data field + validation; prompt options
  __init__.py              # extend: build RA4/RA2 adapters; instantiate M3 + schedule its tick;
                            #   register SWITCH platform
  strings.json             # + notify-target/prompt labels; switch entity name
  translations/en.json     # mirror strings.json (nl.json best-effort)
```

`tests/` mirrors 1:1 per ADR-0002/0009: `tests/test_notification_state.py` (plain pytest);
`tests/adapters/test_notify.py`, `tests/test_notification_manager.py`, `tests/test_switch.py`,
plus HA-harness additions to `tests/adapters/test_factory.py`,
`tests/test_config_flow.py`, `tests/test_init.py`.

---

## 11. Testing approach (ADR-0009 split)

- **Plain pytest** (no HA) for the pure piece (§7): UC08's prompt lifecycle
  (Not-sent→Pending on trigger; Pending→Answered-yes/Answered-no on a response; Pending→Timed-out at
  midnight; re-arm to Not-sent at the day rollover; the 1a/1b/1c skips). Deterministic given
  identical inputs; `now`/`current_date` injected, never read inside the module.
- **HA harness** (ADR-0009 — HA-coupled) for RA4 and M3:
  - **RA4** — message dispatch (`notify.send_message` called with message/title/actions against the
    mapped notify entity) + simulated action response via a fired `mobile_app_notification_action`
    event, including the **stale-tag → `None`** guard (success criteria 1–2), matching
    project-plan RA4's "message dispatch and simulated action response".
  - **M3** — UC08 prompt + tag-keyed response capture + home-day flag write on "yes"; the skips; the
    midnight timeout and re-arm; and (last, gated) R5 delivery on a synthetic
    `DeadlineUnreachableNotified` bus event — matching project-plan M3's "UC08 prompt + response
    capture; R5 delivery on the subscribed event".
  - The owned `switch`, the factory extensions, the config-flow field +
    validation, and the setup wiring are HA-harness tested per their platform/flow nature.

---

## 12. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
([`2026-07-21-notifications.md`](2026-07-21-notifications.md)). Build order: RA4 → pure UC08
logic → supporting Resource Access + owned entities → M3 orchestration → config/setup wiring →
R5-delivery (gated, last) → translations/strings/README + end-to-end regression. No
`custom_components/` code is written until the paired plan exists and is approved.
