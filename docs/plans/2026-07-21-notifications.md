# Notifications Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build **RA4** (Notification access) and **M3** (Notification Manager) — the UC10 plug-in
reminder, the UC08 evening home-day prompt (writing the home-day flag on "yes"), and delivery of R5's
deadline-unreachable notice — per [`2026-07-21-notifications-design.md`](2026-07-21-notifications-design.md).

**Architecture:** Adds a notify adapter role (`adapters/notify.py`, RA4 — an ADR-0003 role extension,
no new ADR), the RA2 read roles M3 consumes (`car_home`, `solar_forecast`, `home_day_external` —
factory extension), two owned entities (`switch.smart_charging_home_day` C2,
`binary_sensor.smart_charging_plug_in_reminder` C3), the pure notification state machines
(`notification_state.py` — UC10 de-dup + UC08 lifecycle, HA-free), and the Notification Manager
(`notification_manager.py` — package-root module mirroring `coordinator.py`, since there is no
`managers/` package; see design §0/§7/§10). M3 coordinates via ADR-0011 (`DeadlineUnreachableNotified`
subscribed; `charger_status` connect/disconnect **re-derived**, not an invented event).

**Tech Stack:** Same as the shipped slices — Python ≥3.12, Home Assistant, `pytest`,
`pytest-homeassistant-custom-component` (HA harness, test-only per ADR-0009), `ruff`. Pure logic
(`notification_state.py`) uses plain pytest; adapters/manager/entities/config-flow use the HA harness.

**Model:** Per CLAUDE.md, this is development work — execute on **Sonnet**.

---

## Before starting: check E4 / the deferred hookups (design §0/§9)

The Deadline Engine (E4, epic #255, PR #273) is **not merged** as of this writing. Confirm before
starting the gated pieces:

- `git log --all --oneline -- custom_components/smart_charging/engines/deadline.py` and
  `grep -r "DeadlineUnreachable" custom_components/` — **does the coordinator publish
  `DeadlineUnreachableNotified` as a bus event yet, and under what concrete signal name/payload?**
  If **no** (expected today): build **Task 6.1 (R5-delivery)** against a *synthetic* bus event whose
  name/payload you define as a local placeholder, and leave a `TODO(E4/#255)` noting the real
  signal name is owned by E4's spec and must be reconciled once E4 lands (design §9 open question 4).
  If **yes**: match E4's actual signal name/payload — do not invent one.
- **UC10's resolved next-departure deadline (R14)** is also E4's and absent. Per design §0/§9, every
  UC10 task below feeds the resolved deadline (and the within-lead-time boolean) as an **injected
  input** — the pure logic and the manager wiring are fully built and tested that way now; the M1/E4
  wiring that supplies a real R14 resolution is a `TODO(E4/#255)` deferral, not built here.

Also check the "create-if-not" pieces (design §1/§4): `git log --all --oneline --
custom_components/smart_charging/switch.py custom_components/smart_charging/binary_sensor.py` and
grep the factory for `car_home`/`solar_forecast`/`home_day_external`. Build them as written if absent;
extend/reuse if a later-merged slice already added them.

---

## Conventions used throughout

Same as `2026-07-20-captar.md`'s conventions (package root, tests-mirror-1:1, canonical states,
ADR-0007 fault rule, engine/pure-logic purity, commit-after-green, re-check
`git branch --show-current` before every commit, `--author="Claude <noreply@anthropic.com>"` +
`Co-Authored-By: Claude Opus 4.8 (1M context)` trailer). Additionally: the pure state machines in
`notification_state.py` take their prior state, observed inputs, and clock (`now` / `current_date`)
as explicit parameters — never calling `dt_util.now()` inside the module (the coordinator/manager
supplies wall-clock, matching Captar's `update_monthly_peak_demand` convention). Do **not** restate
UC10/UC08 thresholds/formulas as if this plan owns them — cite them as test anchors (UC10 preconditions
& trigger, R12; UC08 preconditions, trigger, and state model, R13), the same way the design doc does.

---

## Phase 1 — RA4 notification adapter (HA harness)

### Task 1.1: Notify role constants

**Files:** Modify `custom_components/smart_charging/const.py`

**Step 1: Append** (naming matches the existing `ROLE_EV_SOC`/`CONF_EV_SOC_ENTITY` convention;
design §3):

```python
# --- DATA addition (RA4 role mapping) ---
ROLE_NOTIFICATION_TARGET = "notification_target"
CONF_NOTIFICATION_TARGET_ENTITY = "notification_target_entity"

# Actionable home-day prompt action ids (UC08; design §5/§6).
ACTION_HOMEDAY_YES = "HOMEDAY_YES"
ACTION_HOMEDAY_NO = "HOMEDAY_NO"
```

**Step 2: Commit** (constants only)

```bash
git add custom_components/smart_charging/const.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add notify role + home-day action-id constants (RA4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: `NotifyAdapter` — send + tag-keyed response capture (RA4, V11)

Honors **ADR-0003** (role extension, no new ADR — design §6) and **ADR-0009** (HA harness — the
adapter is HA-coupled: it calls a service and listens on the event bus). Realizes RA4's
project-plan "message dispatch and simulated action response".

**Files:**
- Create: `custom_components/smart_charging/adapters/notify.py`
- Create: `tests/adapters/test_notify.py`

**Step 1: Failing tests** (HA harness). Cover, per design success criteria 1–2:

```python
"""HA-harness tests for the notify adapter (RA4 -- ADR-0003 role extension, ADR-0009)."""

async def test_write_sends_message_and_title_to_the_mapped_notify_entity(hass, ...):
    """write(payload) calls notify.send_message against the mapped notify-domain entity
    with the payload's message and title."""

async def test_write_includes_action_buttons_when_payload_is_actionable(hass, ...):
    """An actionable payload (HOMEDAY_YES/HOMEDAY_NO) sends the action buttons so a tap fires
    HA's mobile_app_notification_action event."""

async def test_read_returns_the_action_for_the_current_tag(hass, ...):
    """After a mobile_app_notification_action event carrying the CURRENT actionable tag,
    read() returns that action id."""

async def test_read_ignores_a_stale_tag_response(hass, ...):
    """A response carrying a superseded tag -> read() returns None, never the stale value
    (design success criterion 2 / §6 -- the stale-response guard)."""

async def test_read_is_none_before_any_response(hass, ...):
    """No action event yet -> read() returns None."""
```

**Step 2: Run** → `ImportError` / assertion failures.

**Step 3: Implement** — `NotifyAdapter(Adapter)`:
- `write(payload)` → `hass.services.async_call("notify", "send_message", {...})` (HA notify-**entity**
  platform, design §3/§6) with `message`/`title` and, when actionable, the action data; stamp a
  **unique tag** and record it as the current actionable tag.
- Register **one** `mobile_app_notification_action` listener at construction/`async_setup`, recording
  `(tag, action_id)`; `read()` returns `action_id` iff its tag == the current actionable tag, else
  `None`.
- Note the write-value type widening (`float | str | NotificationRequest`) in a comment (design §6);
  define the small `NotificationRequest` payload dataclass here (message, title, optional actions, tag).

**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/adapters/notify.py tests/adapters/test_notify.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add notify adapter -- send + tag-keyed response capture (RA4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 1 checkpoint:** `pytest tests/adapters/test_notify.py -v` green; a simulated action event
> round-trips through `read()`, and a stale tag is ignored.

---

## Phase 2 — Pure notification state machines (plain pytest, no HA)

Per design §7/§11: pure logic with no I/O → plain pytest (ADR-0009). Grep-confirm no
`import homeassistant` in `notification_state.py`.

### Task 2.1: UC10 plug-in-reminder de-dup state machine

**Files:**
- Create: `custom_components/smart_charging/notification_state.py`
- Create: `tests/test_notification_state.py`

**Step 1: Failing tests** (plain pytest) — test names trace to UC10's state model/flows (R12). The
resolved deadline and within-lead-time are **injected inputs** (design §0/§9):

```python
"""Plain-pytest tests for the pure notification state machines (M3 -- UC10/UC08)."""

from custom_components.smart_charging.notification_state import (
    ReminderState,   # Armed | Sent
    evaluate_reminder,
)

# Anchors: UC10 preconditions + trigger (R12); 3a connect/disconnect re-arm; 3b window change.

def test_armed_sends_when_all_preconditions_and_lead_time_hold():
    """Armed + (home, disconnected, below active SOC limit, deadline resolved, within lead time)
    -> send, transition to Sent (PlugInReminderSent)."""

def test_sent_does_not_repeat_while_preconditions_keep_holding():
    """Sent stays Sent and sends nothing further for the same departure window (UC10 de-dup)."""

def test_sent_rearms_on_connect_then_disconnect_cycle():
    """Sent -> Armed after disconnected->connected->disconnected (UC10 3a)."""

def test_sent_rearms_on_departure_window_change():
    """Sent -> Armed when the resolved departure window changes (UC10 3b), independently of 3a."""

def test_no_send_when_connected_or_charging():
    """UC10 exception: connected/charging -> never send."""

def test_no_send_when_soc_at_or_above_active_limit():
    """UC10 exception: SOC >= active limit -> never send."""

def test_no_send_when_deadline_unresolved():
    """UC10 exception: deadline resolves to 'no deadline' -> never send."""

def test_deterministic_given_identical_inputs():
    ...
```

**Step 2: Run** → `ImportError`. **Step 3: Implement** the pure `ReminderState` + `evaluate_reminder`
(returns `(should_send, next_state, is_due)` — `is_due` feeds the binary_sensor, design §4). No HA
imports; `now`/window identity injected. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/notification_state.py tests/test_notification_state.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add UC10 plug-in-reminder de-dup state machine (M3, pure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: UC08 evening-prompt lifecycle state machine

**Files:**
- Modify: `custom_components/smart_charging/notification_state.py`
- Modify: `tests/test_notification_state.py`

**Step 1: Failing tests** (plain pytest) — names trace to UC08's state model (R13). `current_date` /
midnight rollover injected:

```python
from custom_components.smart_charging.notification_state import (
    PromptState,   # NotSent | Pending | AnsweredYes | AnsweredNo | TimedOut
    evaluate_prompt,
)

# Anchors: UC08 preconditions, trigger, and state model (R13).

def test_not_sent_to_pending_on_trigger():
    """Enabled + forecast > threshold + no external flag + connected at/after prompt time before
    midnight -> send, Not-sent -> Pending (HomeDayPromptSent)."""

def test_pending_to_answered_yes_writes_flag_intent():
    """HOMEDAY_YES before midnight -> Answered-yes, flag-write intent True (HomeDaySet)."""

def test_pending_to_answered_no_leaves_flag_unset():
    """HOMEDAY_NO before midnight -> Answered-no, no flag write (HomeDayPromptDeclined)."""

def test_pending_to_timed_out_at_midnight_leaves_flag_unset():
    """Midnight with no answer -> Timed-out, no flag write (HomeDayPromptTimedOut)."""

def test_skips_when_prompt_disabled_or_forecast_below_threshold_or_external_flag_set():
    """UC08 1a/1b: stays Not-sent, no send."""

def test_stays_not_sent_when_car_never_connects_before_midnight():
    """UC08 1c: no trigger before midnight -> stays Not-sent."""

def test_rearms_to_not_sent_at_day_rollover():
    """Terminal states -> Not-sent at the midnight date rollover (fresh each evening)."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** `PromptState` + `evaluate_prompt` (returns
`(should_send, next_state, write_flag)`), pure, clock injected. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/notification_state.py tests/test_notification_state.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add UC08 evening-prompt lifecycle state machine (M3, pure)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 2 checkpoint:** `pytest tests/test_notification_state.py -v` green; grep-confirm no
> `import homeassistant` in `notification_state.py`. Every UC10/UC08 transition has a named test.

---

## Phase 3 — Supporting Resource Access & owned entities (HA harness)

### Task 3.1: RA2 read roles M3 consumes (`car_home`, `solar_forecast`, `home_day_external`)

**Create-if-not** (design §1/§4). Honors ADR-0003 (RA2 roles) / ADR-0009 (HA harness).

**Files:**
- Modify: `custom_components/smart_charging/const.py` (add `ROLE_*` / `CONF_*_ENTITY` for the three
  roles, matching the existing convention)
- Modify: `custom_components/smart_charging/adapters/factory.py`
- Modify: `tests/adapters/test_factory.py`

**Step 1: Failing tests** — factory builds each role when its entity is configured, and omits it when
not (same optional pattern `ev_soc`/`grid_voltage` use). `car_home`/`home_day_external` read as
booleans; `solar_forecast` numeric (kWh). **Step 2: Run** → FAIL. **Step 3: Implement** — reuse
`NumericReadAdapter` for `solar_forecast`; add a small boolean-read adapter (or reuse an existing one)
for `car_home`/`home_day_external`; wire all three into `build_adapters` optionally.
**Note:** `departure_external` is **not** added here (deferred with E4, design §8).
**Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/const.py custom_components/smart_charging/adapters/factory.py tests/adapters/test_factory.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add car_home/solar_forecast/home_day_external read roles (RA2)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: Home-day flag owned entity (`switch.smart_charging_home_day`, C2)

**Create-if-not.** Honors ADR-0004 (owned native entity, `smart_charging_` prefix; the `wfh`
illustrative name is superseded by the settled `home_day` id) / ADR-0002 (`switch.py` at root) /
ADR-0009. Realizes the entity-catalog "Home day" row (R13: `off`, resets daily at midnight).

**Files:**
- Create: `custom_components/smart_charging/switch.py`
- Create: `tests/test_switch.py`

**Step 1: Failing tests** (HA harness): the switch is created under the Smart Charging device, defaults
`off`, is settable on/off, restores state, and **resets to `off` at the midnight date rollover** (its
own R13 behavior, independent of UC08 — cite entity-catalog). **Step 2: Run** → FAIL.
**Step 3: Implement** — `HomeDayFlagSwitch(SmartChargingEntity, RestoreEntity, SwitchEntity)`;
register the midnight reset via `async_track_time_change` at 00:00. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/switch.py tests/test_switch.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add home-day flag switch entity, midnight reset (C2, R13)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 3 checkpoint:** RA2 roles resolve through the factory; the home-day switch materializes
> under the Smart Charging device and resets at a simulated midnight. (The reminder binary_sensor is
> built in Phase 4, Task 4.3, after its only data source — M3's `is_due` — exists; project-plan §2's
> own rule places C3 diagnostic entities after their writer, "for build-order reasons only".)

---

## Phase 4 — Notification Manager (M3) orchestration (HA harness)

M3 is a package-root module (`notification_manager.py`, mirroring `coordinator.py` — design §7/§10),
composing RA1/RA2/RA4 + the Store + the pure state machines. Honors **ADR-0011** (`charger_status`
connect/disconnect re-derived by observing the adapter; no invented event) and **ADR-0009** (HA
harness — Managers are HA-coupled). **Never** calls M1 directly (system-design §4 rule 5).

### Task 4.1: UC10 reminder orchestration + due-state exposure

**Files:**
- Create: `custom_components/smart_charging/notification_manager.py`
- Create: `tests/test_notification_manager.py`

**Step 1: Failing tests** (HA harness) — the resolved deadline injected (design §0/§9,
`TODO(E4/#255)`):

```python
async def test_sends_one_reminder_when_gate_holds(hass, ...):
    """Home, disconnected, below active SOC limit (E3), deadline resolved + within lead time
    (injected) -> exactly one notify send; a second evaluation sends nothing (UC10 de-dup)."""

async def test_rearms_and_resends_after_connect_disconnect_cycle(hass, ...):
    """charger_status disconnected->connected->disconnected (re-derived via the adapter, ADR-0011)
    -> reminder can fire again (UC10 3a)."""

async def test_rearms_on_departure_window_change(hass, ...):
    """Injected resolved deadline changes -> reminder can fire again (UC10 3b)."""

async def test_no_reminder_when_connected_or_soc_reached_or_no_deadline(hass, ...):
    """UC10 exception flows -> no send; binary_sensor due-state is off."""

async def test_binary_sensor_due_state_tracks_the_gate(hass, ...):
    """is_due is True exactly while the UC10 gate holds (car home, disconnected, below limit,
    within lead time) -- independent of Armed/Sent, matching entity-catalog's own definition
    (design §5); feeds Task 4.3."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — the Manager reads `car_home`/`charger_status`/`ev_soc`
(RA1/RA2), the active SOC limit via `resolve_active_soc_limit` (E3, reused), takes the injected
resolved deadline, calls `evaluate_reminder` (Task 2.1), sends via RA4 (Task 1.2) on `should_send`,
threads `ReminderState`, and exposes `is_due` for the binary_sensor. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/notification_manager.py tests/test_notification_manager.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Notification Manager UC10 reminder orchestration (M3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.2: UC08 prompt orchestration + response capture + home-day flag write

**Files:**
- Modify: `custom_components/smart_charging/notification_manager.py`
- Modify: `tests/test_notification_manager.py`

**Step 1: Failing tests** (HA harness):

```python
async def test_sends_actionable_prompt_when_uc08_trigger_holds(hass, ...):
    """Enabled + forecast > threshold + no external flag + connected at home at/after prompt time
    before midnight -> one actionable yes/no notify send (UC08 HomeDayPromptSent)."""

async def test_yes_response_writes_home_day_flag(hass, ...):
    """RA4 read() returns HOMEDAY_YES (tag-matched) before midnight -> writes
    switch.smart_charging_home_day on (Store); Answered-yes (HomeDaySet)."""

async def test_no_response_leaves_flag_unset(hass, ...):
    """HOMEDAY_NO -> flag stays unset (HomeDayPromptDeclined)."""

async def test_midnight_without_answer_times_out_and_leaves_flag_unset(hass, ...):
    """Simulated midnight rollover with a Pending prompt -> Timed-out, flag unset
    (HomeDayPromptTimedOut); lifecycle re-arms to Not-sent."""

async def test_skips_prompt_on_uc08_1a_1b_1c(hass, ...):
    """Prompt disabled / forecast <= threshold / external flag already set / car never connects
    before midnight -> no send (UC08 skips)."""

async def test_stale_prompt_response_is_not_misread(hass, ...):
    """A prior evening's response tag must not resolve tonight's prompt (RA4 stale-tag guard, §6)."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — reads `solar_forecast`/`home_day_external`/`car_home`/
`charger_status` + the evening-prompt options (comparing `solar_forecast` against
`CONF_SOLAR_FORECAST_THRESHOLD_KWH`, Task 5.1), calls `evaluate_prompt` (Task 2.2), sends the
actionable payload via RA4, captures the response via RA4 `read()` (tag-keyed), writes the home-day
flag through the Store on `write_flag`, and detects midnight via `dt_util.now()` date rollover
(design §5 — no new timer). **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/notification_manager.py tests/test_notification_manager.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add UC08 evening prompt + response capture + flag write (M3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.3: Plug-in-reminder indicator (`binary_sensor.smart_charging_plug_in_reminder`, C3)

**Create-if-not.** Honors ADR-0004 (owned entity) / ADR-0002 (`binary_sensor.py` at root) / ADR-0009.
Realizes the entity-catalog "Reminders & prompts" row (`on` while a reminder is currently due, R12).
Placed here, after Task 4.1 (not in Phase 3), because it depends on M3's `is_due` signal —
project-plan §2's own rule places C3 diagnostic entities after their writer, "for build-order
reasons only", not reclassified as anything but an owned entity (design §4).

**Files:**
- Create: `custom_components/smart_charging/binary_sensor.py`
- Create: `tests/test_binary_sensor.py`

**Step 1: Failing tests** (HA harness): `is_on` reflects M3's live UC10 due-state (the `is_due`
signal Task 4.1 exposes) — `on` exactly while the UC10 gate holds, independent of Armed/Sent (design
§5, entity-catalog's own definition — see success criterion 4); created under the Smart Charging
device. **Step 2: Run** → FAIL. **Step 3: Implement** — `PlugInReminderBinarySensor(SmartChargingEntity,
BinarySensorEntity)` reading M3's exposed due-state. **Step 4: Run** → PASS. **Step 5: Commit**

```bash
git add custom_components/smart_charging/binary_sensor.py tests/test_binary_sensor.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add plug-in-reminder binary_sensor (C3, R12)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 4 checkpoint:** M3 sends/de-dups UC10 reminders and runs the UC08 prompt lifecycle
> end-to-end against mocked adapters/Store; the reminder binary_sensor tracks M3's due-state; no
> direct M1↔M3 call (assert no coordinator import in `notification_manager.py` beyond types).

---

## Phase 5 — Config/options flow & setup wiring (HA harness)

### Task 5.1: Config keys + config-flow extension (C4)

Honors ADR-0005 (data/options split) / ADR-0003 (notify-target validation) / ADR-0009.

**Files:**
- Modify: `custom_components/smart_charging/const.py` (options `CONF_*` + `DEFAULT_*`)
- Modify: `custom_components/smart_charging/config_flow.py`
- Modify: `tests/test_config_flow.py`

**Step 1: Append constants** (design §3; catalog defaults cited, not re-derived):

```python
CONF_REMINDER_LEAD_H = "reminder_lead_h"          # input_number.sc_reminder_lead_h
CONF_EVENING_PROMPT_ENABLED = "evening_prompt_enabled"  # input_boolean.sc_evening_prompt_enabled
CONF_EVENING_PROMPT_TIME = "evening_prompt_time"  # input_datetime.sc_evening_prompt_time
CONF_SOLAR_FORECAST_THRESHOLD_KWH = "solar_forecast_threshold_kwh"  # input_number.sc_solar_forecast_threshold_kwh

DEFAULT_REMINDER_LEAD_H = 8.0
DEFAULT_EVENING_PROMPT_ENABLED = True
DEFAULT_EVENING_PROMPT_TIME = "18:00:00"
DEFAULT_SOLAR_FORECAST_THRESHOLD_KWH = 12.0
```

**Step 2: Failing tests** — the user flow accepts and stores the notify-target **data** field and
validates it is a `notify`-domain entity (rejecting a non-notify entity, mirroring the existing
platform-validation guard); the four reminder/prompt fields (including the forecast threshold, UC08
precondition 2, design §3) seed into **options** with their `DEFAULT_*`; the options flow round-trips
edits to each; a pre-existing entry reads each with its `DEFAULT_*` (no migration). **Note:**
`sc_prompt_timeout_h` is deliberately **not** added (design §3/§9 — UC08 has no separate timeout;
source doc wins). **Step 3: Run** → FAIL.
**Step 4: Implement** — add the notify-target field to `MAPPING_SCHEMA` with `notify`-platform
validation; add the four options fields to `OPTION_KEYS` + `_threshold_schema()`. **Step 5: Run** →
PASS. **Step 6: Commit**

```bash
git add custom_components/smart_charging/const.py custom_components/smart_charging/config_flow.py tests/test_config_flow.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: map notify target + add reminder/prompt options (C4)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5.2: Setup wiring — build RA4/RA2 adapters, instantiate M3, schedule its tick, register platforms

**Files:**
- Modify: `custom_components/smart_charging/__init__.py`
- Modify: `tests/test_init.py`

**Step 1: Failing tests** — setup builds the notify + RA2 adapters, instantiates the Notification
Manager, registers the `SWITCH` and `BINARY_SENSOR` platforms, and schedules M3's periodic evaluation
(`async_track_time_interval` on the same control interval — the design §5 tick, a C1-style timer);
teardown cancels the tick and the event listeners cleanly. **Step 2: Run** → FAIL.
**Step 3: Implement** — thread the three new options into M3's config; add
`Platform.SWITCH, Platform.BINARY_SENSOR` to `PLATFORMS`; store M3 in `hass.data[DOMAIN][entry_id]`;
register the tick via `entry.async_on_unload(async_track_time_interval(...))`. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/__init__.py tests/test_init.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: wire Notification Manager + switch/binary_sensor platforms at setup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 5 checkpoint:** a full config entry maps the notify target and round-trips the
> reminder/prompt options; setup instantiates M3, schedules its tick, and registers all platforms;
> the switch/binary_sensor appear on the device.

---

## Phase 6 — R5-delivery (gated, last), docs & end-to-end regression

### Task 6.1: R5 deadline-unreachable delivery — subscribe to `DeadlineUnreachableNotified` (LAST, GATED)

**This is the one task gated on E4/M1 (design §0/§9).** Run the "Before starting" E4 check first.
Honors **ADR-0011** (consume the published event; do not re-derive urgency) / ADR-0009.

**Files:**
- Modify: `custom_components/smart_charging/notification_manager.py`
- Modify: `tests/test_notification_manager.py`

**Step 1: Failing test** (HA harness) — fire a **synthetic** `DeadlineUnreachableNotified` bus event
and assert M3 delivers the deadline-unreachable notice via RA4 exactly once per event:

```python
async def test_delivers_deadline_unreachable_notice_on_subscribed_event(hass, ...):
    """On a DeadlineUnreachableNotified bus event, M3 sends the deadline-unreachable notice via
    RA4 -- consuming the event, not re-deriving urgency (ADR-0011 Decision row 1)."""
```

**Step 2: Run** → FAIL. **Step 3: Implement** — subscribe M3 to the event bus
(`hass.bus.async_listen(...)`, unsubscribed on unload); on receipt, send the notice via RA4. Leave a
`TODO(E4/#255)`: the concrete signal name/payload is owned by E4's spec (design §9 open question 4) —
match it once E4 lands; until then the placeholder name defined here stands. **Step 4: Run** → PASS.
**Step 5: Commit**

```bash
git add custom_components/smart_charging/notification_manager.py tests/test_notification_manager.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: deliver R5 deadline-unreachable notice on subscribed event (M3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.2: End-to-end HA-harness regression (UC10 + UC08)

**Files:** Create `tests/test_notifications_end_to_end.py`

**Step 1: Failing tests** (HA harness), driven through `hass.config_entries` + M3's scheduled
evaluation + fired action/`DeadlineUnreachableNotified` events against mocked entity states — not
calling `notification_state` functions directly (Phase 2's job; this suite proves the wiring). The
resolved deadline stays injected (design §0/§9):

```python
"""End-to-end HA-harness regression for UC10 (R12) and UC08 (R13), setup-to-teardown."""

async def test_e2e_uc10_main_success_sends_one_reminder(hass, ...): ...
async def test_e2e_uc10_rearms_on_connect_disconnect_cycle(hass, ...): ...       # 3a
async def test_e2e_uc10_rearms_on_departure_window_change(hass, ...): ...        # 3b
async def test_e2e_uc10_no_reminder_when_connected_or_charging(hass, ...): ...
async def test_e2e_uc10_no_reminder_when_soc_at_or_above_limit(hass, ...): ...
async def test_e2e_uc10_no_reminder_when_deadline_unresolved(hass, ...): ...

async def test_e2e_uc08_main_success_prompt_then_yes_sets_flag(hass, ...): ...
async def test_e2e_uc08_no_response_leaves_flag_unset(hass, ...): ...           # 3a
async def test_e2e_uc08_timeout_at_midnight_leaves_flag_unset(hass, ...): ...
async def test_e2e_uc08_skips_when_prompt_disabled(hass, ...): ...              # 1a
async def test_e2e_uc08_skips_when_forecast_below_threshold(hass, ...): ...     # 1b
async def test_e2e_uc08_skips_when_external_source_already_set_flag(hass, ...): ...  # 1a
async def test_e2e_uc08_stays_not_sent_when_car_never_connects(hass, ...): ...  # 1c
```

**Step 2: Run** → FAIL. **Step 3: Implement** — nothing new; this suite exercises the wiring built in
Phases 1–5. **Step 4: Run** → PASS. **Step 5: Commit.**

```bash
git add tests/test_notifications_end_to_end.py
git commit --author="Claude <noreply@anthropic.com>" -m "test: add end-to-end HA-harness regression for UC10/UC08

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.3: Translations, strings, README

**Files:**
- Modify: `custom_components/smart_charging/strings.json` + `translations/en.json` (new config
  `notification_target_entity` label + `notify`-validation error; new options
  `reminder_lead_h`/`evening_prompt_enabled`/`evening_prompt_time` labels; `switch.home_day` and
  `binary_sensor.plug_in_reminder` entity names); `translations/nl.json` best-effort
- Modify: `README.md` (Configuration table: notification target, reminder lead time, evening prompt
  enable/time; move the plug-in reminder + evening prompt from "Deferred" to the feature list; note
  R5-delivery is gated on the Deadline Engine)

**Step 1:** Run `python -m script.hassfest` (or the project's validation task) to confirm strings
completeness. **Step 2: Commit.**

```bash
git add custom_components/smart_charging/strings.json custom_components/smart_charging/translations/en.json custom_components/smart_charging/translations/nl.json README.md
git commit --author="Claude <noreply@anthropic.com>" -m "docs: translations + README for notifications (RA4/M3)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **⎔ Phase 6 / slice checkpoint:** `ruff check . && ruff format --check . && pytest -q` all green;
> hassfest/HACS validation passes; a manual HA install can map a notify entity, receive a plug-in
> reminder (de-dup + re-arm), receive and answer the evening home-day prompt (flag set on "yes",
> unset on "no"/timeout), and — once E4 publishes `DeadlineUnreachableNotified` (Task 6.1's gate) —
> receive the deadline-unreachable notice. The two deferred hookups (UC10's R14 deadline resolution;
> the real `DeadlineUnreachableNotified` signal name) remain `TODO(E4/#255)`, tracked, not silently
> built (design §0/§9).
