# Notifications — design

**Date:** 2026-07-21
**Status:** draft (issue #275, epic #257)
**Type:** implementation design (a slice of the approved architecture — not a new decision)

This document defines the **Notifications** build slice: **RA4** (Notification access, Resource
Access V11) and **M3** (Notification Manager, V11) — the plug-in reminder (UC10), the evening
home-day prompt (UC08), and delivery of R5's deadline-unreachable notice.

It is a deliberate **subset** of the full architecture, built the same way the Power MVP and the
Captar slice were: every component below is a slice of a service already named in
[`../design/system-design.md`](../design/system-design.md) §3 and sequenced in
[`../design/project-plan.md`](../design/project-plan.md) (RA4, M3, Phase 3 checkpoint). Nothing
here introduces a new service, call direction, or structural decision. RA4 reuses the ADR-0003
adapter-role protocol as a role extension (an extension ADR-0003 explicitly anticipates — like RA2
and RA3, it needs **no new ADR**, and this document says so explicitly in §6). M3's cross-Manager
coordination follows the already-Accepted **ADR-0011** (G-ADR-0011, resolved).

Behavior is owned by
[UC10](../analysis/use-cases/UC10-remind-to-plug-in.md) (plug-in reminder, R12) and
[UC08](../analysis/use-cases/UC08-plan-tomorrow-home-day.md) (evening home-day prompt, R13);
this document cites their state models, triggers, and thresholds as test anchors and does **not**
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
two outputs this slice's use-cases reference, both currently **unbuilt** (E4's spec is drafted in
PR #273, not merged as of this writing — `engines/deadline.py` does not exist and the coordinator
publishes no `DeadlineUnreachableNotified` event; confirmed against the current tree):

1. **`DeadlineUnreachableNotified`** (the ADR-0011 published event) — consumed by the **R5-delivery**
   task. This is the **one task in this plan gated on E4/M1**: its subscription handler can be
   unit-tested now by firing a synthetic event on the HA bus, but the real end-to-end path depends
   on M1 actually publishing it. It is written as the **last** implementation task (Phase 6), and
   its "before you start" check is: *does the coordinator publish `DeadlineUnreachableNotified` as a
   bus event yet, and under what concrete signal name/payload?* (that name is owned by E4's spec —
   this slice matches it, it does not invent it).
2. **The resolved next-departure deadline (R14)** — UC10's trigger ("within the configured lead
   time of the next departure time") and its 3b re-arm ("the next departure time changes") both need
   E4's deadline resolution. This is **distinct from** the `DeadlineUnreachableNotified` event: UC10
   is *not* gated on that event, but it *is* gated on E4's R14 output. Handled per §9's open question:
   UC10's pure de-dup/gating logic is built and tested now against the resolved deadline supplied as
   an **injected input**; the M1/E4 wiring that feeds it a real R14 resolution is deferred until E4
   lands, exactly like R5-delivery. This slice never builds a departure-deadline resolver of its own
   (that is E4's epic, out of scope — §8).

Every other task (RA4, UC08, the pure UC10 de-dup logic, the supporting Resource-Access roles and
owned entities) has **no** E4 dependency and is built and tested first.

---

## 1. Why this slice is wider than "just the Manager"

M3 composes services and Resource-Access roles that the shipped code does not have yet. Each is a
named `project-plan.md` service; this slice builds the minimal, mechanical slice of each that M3
consumes, following the Captar slice's **"extend if it exists, create if it doesn't"** rule (§10).

| M3 (UC08/UC10) needs | Shipped status | This slice |
| --- | --- | --- |
| Reach the HA `notify` domain, send actionable messages, capture responses (RA4, V11) | Absent | **In scope** — `adapters/notify.py`, new role (§4/§6) |
| `car_home`, `solar_forecast`, `home_day_external` read roles (RA2, V1) | Absent | **In scope** — factory extension, create-if-not (§4) |
| Home-day flag as owned state, written on "yes" (C2; `switch.smart_charging_home_day`) | Absent (no `switch.py`) | **In scope** — create-if-not (§4/§7) |
| Plug-in-reminder due indicator (C3; `binary_sensor.smart_charging_plug_in_reminder`) | Absent (no `binary_sensor.py`) | **In scope** — create-if-not (§4/§7) |
| Active-SOC-limit resolution (E3, `resolve_active_soc_limit`) | Shipped (`engines/soc_target.py`) | **Reused unchanged** |
| `charger_status`, `ev_soc` read roles (RA1) | Shipped | **Reused unchanged** |
| Resolved next-departure deadline + lead-time window (E4/R14) | Absent (epic #255) | **Deferred hookup** — injected input now (§0/§9) |
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
3. **UC10 single reminder.** With the car home, disconnected, below the active SOC limit, the next
   departure deadline resolved, and within the configured lead time
   (`sc_reminder_lead_h`, default 8 h — UC10 trigger), M3 sends exactly **one** plug-in reminder for
   that departure window (UC10 Armed→Sent); no further reminder is sent while the preconditions keep
   holding (UC10 de-dup).
4. **UC10 re-arm.** After a reminder has been sent, a `disconnected→connected→disconnected` cycle
   (3a) **or** a departure-window change (3b) returns M3 to Armed so it can send again (UC10 state
   model). The `binary_sensor.smart_charging_plug_in_reminder` is `on` exactly while a reminder is
   currently due (entity-catalog).
5. **UC10 suppression.** No reminder while connected/charging, or while SOC is at/above the active
   limit, or while the deadline resolves to "no deadline" (UC10 exception flows).
6. **UC08 prompt.** With the evening prompt enabled (`sc_evening_prompt_enabled`, default on), the
   next-day forecast above threshold (`sc_solar_forecast_threshold_kwh`, default 12 kWh — the same
   threshold R9 uses), no external source having set tomorrow's home-day flag, and the car connected
   at home at/after `sc_evening_prompt_time` (default 18:00) before midnight, M3 sends **one**
   actionable yes/no notification (UC08 Not-sent→Pending).
7. **UC08 answer.** A `HOMEDAY_YES` response before midnight sets the home-day flag for tomorrow
   (Pending→Answered-yes); `HOMEDAY_NO` (Answered-no) or midnight with no answer (Timed-out) leaves
   it unset (UC08 state model). Each terminal state is reached at most once per evening; the lifecycle
   re-arms to Not-sent at the midnight date rollover.
8. **UC08 skips.** No prompt when the prompt is disabled, the forecast is at/below threshold, an
   external source already set the flag, or the car never connects before midnight (UC08 1a/1b/1c).
9. **R5 delivery** *(gated — §0/§9)*. On the subscribed `DeadlineUnreachableNotified` event, M3
   delivers the deadline-unreachable notice via RA4.

---

## 3. Install-time / options additions

Extends the config/options flow (ADR-0005 data/options split retained; ADR-0003 role mapping for the
notify target). The reminder/prompt tuning values are **catalogued** in
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

| Field | Bucket | Constant / default | Source |
| --- | --- | --- | --- |
| **Notification target** entity (a `notify`-domain entity) | data — required for M3 to deliver at all | `CONF_NOTIFICATION_TARGET_ENTITY = "notification_target_entity"`; role `ROLE_NOTIFICATION_TARGET = "notification_target"` | RA4 (§6); named to match the existing `ROLE_EV_SOC`/`ROLE_CHARGER_STATUS` convention in `const.py` |
| **Plug-in reminder lead time** | options | `CONF_REMINDER_LEAD_H`, default **8 h** | `input_number.sc_reminder_lead_h` (entity-catalog); UC10 trigger (R12) |
| **Evening prompt enabled** | options | `CONF_EVENING_PROMPT_ENABLED`, default **on** | `input_boolean.sc_evening_prompt_enabled`; UC08 precondition |
| **Evening prompt time** | options | `CONF_EVENING_PROMPT_TIME`, default **18:00** | `input_datetime.sc_evening_prompt_time`; UC08 trigger |
| `car_home`, `solar_forecast`, `home_day_external` entity mappings (data) | data | RA2 roles, create-if-not (§4) | entity-catalog (RA2) |

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
- **RA2 read roles** — `car_home` (bool), `solar_forecast` (kWh), `home_day_external` (bool):
  factory extensions using the existing `NumericReadAdapter` / a boolean-read variant, **create-if-not**.
  `departure_external` is **not** built here (it feeds the deferred E4 R14 hookup — §0/§8).
- **`switch.smart_charging_home_day`** — owned home-day flag (C2; entity-catalog "Home day" row:
  `off`, resets daily at midnight, R13). New (`switch.py`), **create-if-not**. Written by UC08 on
  "yes"; resets itself to `off` at the midnight date rollover (its own catalogued R13 behavior,
  independent of UC08). Its `wfh` illustrative name in ADR-0004 is superseded by the settled
  `home_day` id (entity-catalog Id note).
- **`binary_sensor.smart_charging_plug_in_reminder`** — owned diagnostic (C3; entity-catalog
  "Reminders & prompts" row: `on` while a plug-in reminder is currently due). New
  (`binary_sensor.py`), **create-if-not**. Reflects M3's live UC10 due-state.
- **Not built this slice:** any deadline/departure owned entity; the R5 notice needs no owned
  entity of its own (it is a one-shot delivery on a subscribed event).

---

## 5. Control flow (matches system-design §5.3's sequence diagram)

M3 is driven per control interval by its own periodic tick plus the HA event bus — the
`Timer / cycle / evening time (Client)` participant in system-design §5.3. Each evaluation reads
owned config + the home-day flag from the Store (RA3), reads the adapter roles (RA1/RA2), consults
E3 (active SOC limit) and — where available — E4 (deadline), and dispatches to exactly one of the
three §5.3 branches. **"Midnight" is realized as a per-evaluation wall-clock comparison**
(`dt_util.now()` date rollover) — the same mechanism M1 already uses for the monthly-peak month
rollover in `coordinator.py`; **no new HA timer/scheduler primitive is introduced.**

### UC10 branch (plug-in reminder)
Per §5.3's first `alt` and UC10:

1. Read `car_home`, `charger_status`, `ev_soc`; read the resolved active SOC limit (E3); obtain the
   resolved next-departure deadline (E4/R14 — **injected input** this slice, §0).
2. Gate on **all** preconditions (car home, `disconnected`, SOC below active limit, deadline resolved
   to an actual deadline, within `sc_reminder_lead_h` of it) — UC10 preconditions/trigger.
3. If the pure de-dup state is **Armed** and the gate holds → send the plug-in reminder via RA4;
   transition Armed→Sent (`PlugInReminderSent`). While **Sent**, send nothing more for the window.
4. Re-arm Sent→Armed on a `disconnected→connected→disconnected` cycle (3a) **or** a departure-window
   change (3b) — `PlugInReminderRearmed`. The `binary_sensor` is `on` exactly while the step-2 gate
   holds and the state is Armed.

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
re-derive urgency — it consumes the event the Coordinator publishes (ADR-0011 Decision row 1). No
`ChargerConnected`/`ChargerDisconnected` event is invented for UC10's re-arm: per ADR-0011,
`charger_status` connect/disconnect is **re-derived** by M3 observing its own `charger_status`
adapter read across evaluations (Decision row 2), which is exactly how step 4's 3a re-arm is detected.

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

**Pure state machines → plain pytest.** UC10's Armed/Sent de-dup and UC08's
Not-sent/Pending/Answered-yes/Answered-no/Timed-out lifecycle are **pure functions of (prior state,
observed inputs, now)** with no I/O — structurally identical to the mode state machines in `modes/`.
Per ADR-0009's split criterion (pure logic with no I/O → plain pytest; only HA-coupled wiring needs
the harness), they are factored into an HA-free module **`notification_state.py`** (package root,
imports no `homeassistant.*`) and unit-tested with plain pytest, test names tracing to UC10/UC08
acceptance criteria. This is the right call because the *decision* ("given preconditions + prior
state + now, should a reminder fire / what is the next prompt state / should the flag be written") is
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

- **Deadline Engine (E4), R14 resolution and the `DeadlineUnreachableNotified` publish** — its own
  epic (#255, PR #273 not merged). UC10's deadline dependency is injected now; R5-delivery is gated
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

1. **UC10's R14 deadline dependency vs. "no dependency" framing.** UC10's trigger and 3b re-arm need
   E4's resolved next-departure deadline (R14), which does not exist yet. UC10 is *not* gated on the
   `DeadlineUnreachableNotified` event (that is R5's), but it *is* gated on E4's R14 output.
   **Resolution:** UC10's pure de-dup/gating logic is built and tested now with the resolved deadline
   (and lead-time-window boolean) as an **injected input**; the M1/E4 wiring that supplies a real R14
   resolution is deferred until E4 lands. Recorded as a deferred obligation, not silently built.
2. **`sc_prompt_timeout_h` (catalog, 2 h) vs UC08 (midnight only).** The entity-catalog "Reminders &
   prompts" row lists a 2-hour prompt timeout (R13), but UC08's "Relationships" section states
   midnight is the only answer deadline with no separate configurable timeout. **These disagree.**
   Per `project-plan.md` §1 (source doc wins over an anchor), UC08 is authoritative: this slice wires
   **no** timeout option and times the prompt out at midnight. Flagged for analysis-doc reconciliation
   (the catalog row should be reconciled with UC08 via the write-requirement flow) — this design opens
   no such change.
3. **Catalog `input_*`/`sc_` ids vs ADR-0005 config realization.** Resolved by precedent, not
   invention: realize the tuning values as config-entry options with `CONF_*` constants (§3), as every
   prior slice did, keeping the catalog ids as analysis-layer names. Flagged as the same deferred
   `sc_`-helper reconciliation `project-plan.md`'s G-NAMING row already records.
4. **Concrete bus signal name/payload for `DeadlineUnreachableNotified`.** Owned by E4's spec
   (PR #273). R5-delivery matches it; this design does not fix a concrete string.

---

## 10. Packaging

```text
custom_components/smart_charging/
  const.py                 # + CONF_NOTIFICATION_TARGET_ENTITY, ROLE_NOTIFICATION_TARGET (data);
                            #   + CONF_REMINDER_LEAD_H, CONF_EVENING_PROMPT_ENABLED, CONF_EVENING_PROMPT_TIME
                            #   (options) + DEFAULT_* ; + RA2 role/CONF constants (create-if-not);
                            #   + home-day flag / reminder action-id constants
  adapters/
    notify.py              # RA4 — new: NotifyAdapter (send + tag-keyed response capture, §6)
    factory.py             # RA1 — extend: wire ROLE_NOTIFICATION_TARGET + RA2 roles (create-if-not)
    numeric.py / base.py   # reuse; note the write-type widening for the notify payload (§6)
  notification_state.py    # M3 pure logic — new: UC10 de-dup + UC08 prompt-lifecycle state machines
                            #   (HA-free, plain pytest — §7)
  notification_manager.py  # M3 — new: orchestration (reads, Store writes, notify dispatch, event subs)
  switch.py                # C2 — new (create-if-not): home-day flag owned entity (R13 midnight reset)
  binary_sensor.py         # C3 — new (create-if-not): plug-in-reminder due indicator
  config_flow.py           # C4 — extend: notify-target data field + validation; reminder/prompt options
  __init__.py              # extend: build RA4/RA2 adapters; instantiate M3 + schedule its tick;
                            #   register SWITCH + BINARY_SENSOR platforms
  strings.json             # + notify-target/reminder/prompt labels; switch/binary_sensor entity names
  translations/en.json     # mirror strings.json (nl.json best-effort)
```

`tests/` mirrors 1:1 per ADR-0002/0009: `tests/test_notification_state.py` (plain pytest);
`tests/adapters/test_notify.py`, `tests/test_notification_manager.py`, `tests/test_switch.py`,
`tests/test_binary_sensor.py`, plus HA-harness additions to `tests/adapters/test_factory.py`,
`tests/test_config_flow.py`, `tests/test_init.py`.

---

## 11. Testing approach (ADR-0009 split)

- **Plain pytest** (no HA) for the pure pieces (§7): UC10's Armed↔Sent de-dup (Armed→Sent on
  gate-holds; Sent stays de-duped; Sent→Armed on a connect/disconnect cycle 3a; Sent→Armed on a
  departure-window change 3b; independence of 3a and 3b) and UC08's prompt lifecycle
  (Not-sent→Pending on trigger; Pending→Answered-yes/Answered-no on a response; Pending→Timed-out at
  midnight; re-arm to Not-sent at the day rollover; the 1a/1b/1c skips). Deterministic given
  identical inputs; `now`/`current_date` injected, never read inside the module.
- **HA harness** (ADR-0009 — HA-coupled) for RA4 and M3:
  - **RA4** — message dispatch (`notify.send_message` called with message/title/actions against the
    mapped notify entity) + simulated action response via a fired `mobile_app_notification_action`
    event, including the **stale-tag → `None`** guard (success criteria 1–2), matching
    project-plan RA4's "message dispatch and simulated action response".
  - **M3** — UC10 reminder gating + de-dup + re-arm (with the resolved deadline injected, §9);
    UC08 prompt + tag-keyed response capture + home-day flag write on "yes"; the skips; the midnight
    timeout and re-arm; and (last, gated) R5 delivery on a synthetic `DeadlineUnreachableNotified`
    bus event — matching project-plan M3's "UC10 reminder gating + de-dup; UC08 prompt + response
    capture; R5 delivery on the subscribed event".
  - Owned entities (`switch`, `binary_sensor`), the factory extensions, the config-flow field +
    validation, and the setup wiring are HA-harness tested per their platform/flow nature.

---

## 12. Next step

This design feeds the `writing-plans` skill to produce the ordered, test-driven implementation plan
([`2026-07-21-notifications.md`](2026-07-21-notifications.md)). Build order: RA4 → pure UC10/UC08
logic → supporting Resource Access + owned entities → M3 orchestration → config/setup wiring →
R5-delivery (gated, last) → translations/strings/README + end-to-end regression. No
`custom_components/` code is written until the paired plan exists and is approved.
