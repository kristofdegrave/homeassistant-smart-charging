# Work type: `development` — the completion bar

**Who reads this.** Both sides of the review, which is why it is its own file rather than a
section of either one:

- **The author**, as the self-check before requesting review — `definition-of-done.md` sends the
  author to a row's completion bar, and this is the `development` row's. That document states
  how its builds/lints/tests checklist and a bar meet for a change touching
  `custom_components/`/`tests/`; both apply, in full, on the terms it states there.
- **The reviewer**, as the bulk of the review criteria. Each item states the severity a miss
  carries, so the two sides judge the same change against the same bar.

It states *what must be true of the finished **code***. How the code is written — the reads, the
TDD loop, the order the work happens in — is `implement.md`. How a review is conducted — what to
read first, how to anchor findings, the output format, and the checks that are about the
*review* rather than the change — belongs with the reviewer.

**The tests are judged by the `testing` row's bar, not by this one.** A `development` change
produces two artifacts in two trees, and the bar belongs to the artifact rather than to the
label that dispatched the review — the `testing` row's completion bar says so itself. So every
`tests/**` file this change writes is judged there, at the severities stated there, whether it
was written inside a TDD loop or under a `testing` issue. Read it from the `testing` row of
`CLAUDE.md`'s **Model selection** table. Nothing about test quality is restated here: a second,
narrower statement of it is exactly the two-standards defect this split exists to remove. The
route is the whole of what this bar says about tests, and it is stated once, here.

## The bar

**(1) Correctness against the spec.** The code does what its plan task and the cited analysis
behaviour specify — the acceptance criteria and worked examples come out of the code as written.
An off-by-one, a wrong operand, a sign error or a boundary error is **Major**, and is named with
a concrete failing input rather than as a suspicion. Where the wrong result is a safety
invariant's (a clamp, the floor/cap, the fault path), item 4 governs the severity instead.

**(2) Structural ADR compliance** — the boundaries this project cannot regress. Each miss names
the file and the boundary crossed.

- **Engine purity (ADR-0006/0009/0010):** nothing under `modes/` or `engines/` imports
  `homeassistant.*` or calls another engine; a stateful engine takes its state as a parameter
  and never holds HA state. An `import homeassistant` under `modes/`/`engines/` is **Critical** —
  it defeats the package boundary the plain-pytest half of the suite rests on.
- **Adapter isolation (ADR-0003):** all HA-entity I/O goes through an adapter, and no logic
  layer reads a raw `entity_id` directly — **Major**. A role returning `None` is the fault
  signal, never a guessed default.
- **Two distinct clamps (ADR-0006):** the grid-safety clamp is a separate call site from the
  peak clamp, with no shared opt-out. Merging the two into one conditional is **Critical**.
- **Fault path (ADR-0007):** every adapter `None` or exception funnels to force-0 A + `Fault` —
  **Major** where one does not. Grid voltage `None` is the single exception (the NF4 nominal
  fallback) and is **Major** if routed to the fault path instead.
- **Config data/options split (ADR-0005):** mappings, translations and thresholds in data;
  tunables (the control interval) in options; an options change reloads the entry — **Major**.
- **Native naming and package layout (ADR-0004/0002/0010):** owned entities use the
  `smart_charging_` native names, and files sit in the ADR-mandated package (`adapters/`,
  `modes/`, `engines/`, platform files and `coordinator.py`/`entity.py` at root) — **Major**,
  because both are contracts other code and the entity registry already depend on.

**(3) Code health.** DRY and YAGNI; the change matches the surrounding style and idioms; no dead
code, no speculative generality, no commented-out blocks — **Minor per occurrence**, **Major**
where it is the pattern of the change, so that following its own example reproduces it.

- **Logging follows ADR-0007's once-per-outage rule**, not per-cycle spam — **Minor**: it
  changes no commanded value, but a log the operator stops reading is how the next fault gets
  missed.
- **No magic strings or numbers** — **Major**. A fixed set of states, phases or modes compared
  or assigned as bare string literals (a `phase: str` field checked against
  `"idle"`/`"charging"`) belongs in an enum (`enum.StrEnum` where the value must still compare
  and serialise as a plain `str`) or a named constant; repeated bare literals are the finding.
  The one exception: a value that must round-trip through HA config-entry storage or
  `vol.In(...)` as a bare `str` may use module-level string constants instead of an enum (see
  `const.py`'s `ROUND_UP`/`ROUND_DOWN`/`ROUND_NEAREST`) — repeated bare literals are still the
  finding there, the choice of constant over enum is not.

**(4) Safety not weakened.** No clamp, floor/cap or fault behaviour is loosened,
short-circuited, or made skippable beyond what the ADRs allow — **Critical**. This is the one
item whose severity does not soften with size: a safety invariant weakened in one branch is
weakened.

**(5) The general-Python and async bar.** The change passes the **Quick review checklist** at
the end of the `python-anti-patterns` skill, and — where it touches async code — the checklist
in `async-python-patterns`, whose **When this file applies** section is the single statement of
which files those are; a change confined to `modes/`/`engines/` is outside it. An anti-pattern
that can change runtime behaviour — anything blocking the event loop above all — is **Major**;
one that only makes the code harder to read is **Minor**.

**(6) Runtime check recorded when the change is observable at runtime.** A change to observable
runtime behaviour carries a **Runtime check** section in the PR description recording what was
driven and what was observed. `definition-of-done.md` owns what counts as observable, what the
section must contain, how it is judged against the diff rather than by its presence, and the
honest cannot-be-driven-yet form; read it there rather than from a summary. A miss is **Major**,
which is the severity that document states and the reason the check is reviewer-read rather than
CI-gated: a mechanical presence check is satisfied by an empty heading.

Two cases are not a finding and must not be reported as one: a change with no PR yet, and a PR
opened by the CI pipeline's bot account — that document states the second and why no fix cycle
can produce it. In both, state what the Runtime check will have to record and leave it there.

A third case is **judged, not excused**: a section in the honest cannot-be-driven-yet form. That
the behaviour could not be driven is not itself the finding — judge the substitute it names, say
so in the review either way, and report an inadequate substitute at this item's severity. What
is excused is the absence of drivable evidence, never the content of the section standing in
for it.

**The one overlap with the `testing` bar, stated once.** A diff that changes how an adapter
**reads or converts a source entity's unit** trips this item, through the computation that
produces an owned entity's state, and also trips the `testing` bar's mandated fifth, unit case
on the adapter class defining that read. Where **both** are missing, that is one defect with two
symptoms: it is raised **once within this review, as the coverage miss**, with the absent or
inadequate runtime evidence named inside that finding, and this item raises nothing further.
This binds the review that holds both bars; it arranges no suppression across two separately
dispatched reviewers, and nothing here asks one to stay silent about the other's tree. The
tests are the
durable fix — a state pasted into a PR body proves the value once, where the mandated cases keep
proving it. Where that coverage is present, this item applies on its own as usual. A change to an
**owned** entity's own unit is not this overlap — the fifth-case rule does not reach the entities
this integration publishes — and is judged here in full however the role's coverage stands.
