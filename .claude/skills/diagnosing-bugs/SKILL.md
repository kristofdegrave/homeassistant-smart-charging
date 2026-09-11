---
name: diagnosing-bugs
description: Use when a defect is reported against the shipped Smart Charging integration — a claim that the running system misbehaves — and that claim has to be confirmed or refuted with a reproduction before anything is specified, ticketed or fixed. Not for a test that fails while implementing a planned task (develop-task owns that), and not for the fix itself.
---

# Diagnosing bugs

Confirm or refute a reported defect and leave behind a minimal reproduction. **It stops there.**
No fix, no regression test, no verification — `develop-task`, `write-tests` and
[definition-of-done.md](../../../docs/reference/definition-of-done.md) own those, and a second
copy here would be a second methodology to keep in sync.

Its one job is the step nothing else here performs: judging the system against something other
than this repo's own documents. The reporter's observation is the oracle, so the loop you build
has to be able to disagree with the docs.

**Redact** every secret and personal identifier out of anything you show. If the redacted
version is not enough to diagnose, say so and ask.

## Step 1 — build a loop that goes red

**This is the skill.** With a pass/fail signal that goes red on *this* defect the cause falls
out; without one, reading code only produces a theory. Spend disproportionate effort here.

Ways to construct one, roughly in order:

1. **Failing test** at whatever seam reaches the defect (Step 5 decides where it lands).
2. **Direct call** into the pure engine/mode/profile function with the reporter's numbers.
3. **A real config entry through the HA harness** — `MockConfigEntry` plus
   `coordinator.async_refresh()`, as the `test_*_end_to_end.py` suites do.
4. **Replay a captured real payload.** Ask for the actual state object of the entity involved —
   raw `state` *and* `attributes`, `unit_of_measurement` included — and seed exactly that,
   attributes and all. `tests/helpers.py::seed_charger_states` seeds bare numeric strings with no
   unit attribute, so anything built on it carries the *author's* assumption about units rather
   than the installation's. A replayed payload is the only seeding that can contradict the
   catalog.
5. **Pin the clock.** Any claim mentioning a time of day, a deadline, a rollover, a cooldown, a
   debounce or "every cycle overnight" gets `freezer.move_to(...)` at the reported wall-clock
   instant and is then advanced across the boundary the reporter names — not at a convenient hour
   that keeps the arithmetic simple. Advance with `freezer` plus `async_fire_time_changed`, never
   `sleep`; if the loop must wait, wait on a condition (a state, a captured call), never on a
   duration.
6. **Check what actually renders.** For a claim about a tile, a displayed number, a unit or a
   precision the oracle is a human eye, and nothing in `tests/` supplies one —
   `tests/test_dashboard.py` asserts which tiles exist, not what any of them shows. Get the
   rendered value: the live entity's full state object, or a screenshot. If a human has to click,
   drive them with `scripts/hitl-loop.template.sh` so the loop stays structured and their answer
   comes back to you.
7. **Differential loop** — the same input through two versions or configs, outputs diffed, when
   the defect appeared between two known-good and known-bad states.

**Tighten it.** Narrow the scope, assert the reporter's exact symptom rather than "no exception",
and remove every source of variance. A 2-second deterministic loop beats a flaky 30-second one.
For an intermittent defect the goal is a *higher reproduction rate*, not a clean repro: 50% is
debuggable, 1% is not.

**If you genuinely cannot build one**, stop and say so: list what you tried and ask the human
partner for access to the installation, a redacted capture (full state objects, logbook extract,
timestamped screenshot), or permission to instrument the live install. Do not hypothesise without
a loop.

**Done when** you can name one command you have already run at least once — invocation and output
shown — that is **red-capable** (drives the real code path and asserts the reporter's symptom, so
it can go red now and green once fixed, not merely "runs without erroring"), **deterministic**,
**fast**, and **agent-runnable** unattended. If you are reading code to build a theory before that
command exists, stop: jumping to a hypothesis is the failure this skill prevents.

## Step 2 — reproduce and minimise

Run the loop, watch it go red, and confirm it is **the failure the reporter described** and not a
different one nearby — wrong defect, wrong fix. The reporter's words are the oracle, not the plan
document, the requirement, or a worked example. Capture the exact symptom (the wrong number, the
missing unit, the event firing every cycle) so the eventual fix can be checked against it.

If the loop stays green the claim is **refuted**: say so plainly with the command and its output,
and stop. That is a finished result, not a failure.

**Minimise.** Cut inputs, config, callers and steps one at a time, re-running after each cut, until
every remaining element is load-bearing — removing any one turns it green.

## Step 3 — rank hypotheses

Generate **3–5 hypotheses before testing any of them**. A single hypothesis anchors on the first
plausible idea and scopes the eventual fix to the one call site you happened to be looking at;
several force the question of where else the same shape lives.

Each must be **falsifiable** — state its prediction: *"if X is the cause, changing Y makes the
symptom disappear."* No prediction means it is a vibe; sharpen it or drop it.

Trace backward rather than stopping where the error surfaces: follow the wrong value up the call
chain to where it was first produced and name *that*. Fixing where it appears leaves the source
intact.

**Show the ranked list to the human partner before testing** — they have the install and the
history and often re-rank it instantly. Don't block; proceed with your own ranking if they are away.

## Step 4 — probe

One probe per prediction, one variable at a time. Prefer inspecting state at the boundary that
distinguishes two hypotheses over adding logs; never "log everything and grep". Tag every
temporary log with a unique prefix — `[DEBUG-a4f2]` — so cleanup is one grep.

## Step 5 — hand off

Stop here and report:

1. **Confirmed or refuted**, with the one command and its output.
2. **The minimal reproduction** and the captured symptom.
3. **The cause** — which hypothesis survived, which were eliminated.
4. **Where else this shape lives** — the same wrong assumption at sibling call sites, roles or
   modes. Answer explicitly, even if the answer is "nowhere else".
5. **Which harness a regression test belongs in** — decide it from ADR-0009's placement rule as
   narrowed by [ADR-0037](../../../docs/adl/0037-scenario-timeline-test-tier.md), reading
   [ADR-0009](../../../docs/adl/0009-testing-strategy.md) rather than guessing, and do not restate
   the taxonomy in your report. **If no correct seam exists — the only reachable seam cannot
   replicate the chain that triggers the defect — that is itself the finding.** Record it on the
   issue; a regression test at the wrong seam is false confidence.
6. **Any `[DEBUG-…]` probes or throwaway files still in the tree.**

The fix is then ordinary work through the normal `development` flow —
[contribution-workflow.md](../../../docs/reference/contribution-workflow.md), with `develop-task`
and `write-tests` for the code and the test, and
[definition-of-done.md](../../../docs/reference/definition-of-done.md) for what "done" means.
