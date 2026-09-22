# Work type: `development` — the completion bar

This file states *what must be true of the finished **code***. How the code is written — the
reads, the TDD loop, the order the work happens in — is `implement.md`. How a review is
conducted — what to read first, how to anchor findings, the output format, and the checks that
are about the *review* rather than the change — belongs with the reviewer.

**The tests are judged by the `testing` row's bar, not by this one.** A `development` change
produces two artifacts in two trees, and the bar belongs to the artifact rather than to the
label that dispatched the review — the `testing` row's completion bar says so itself. So every
`tests/**` file this change writes is judged there, at the severities stated there, whether it
was written inside a TDD loop or under a `testing` issue. Read it from the `testing` row of
`CLAUDE.md`'s **Model selection** table. Nothing about test quality is restated here: a second,
narrower statement of it is exactly the two-standards defect this split exists to remove. The
route is the whole of what this bar says about tests, and it is stated once, here.

## The bar

**(1) Correctness against the spec.** The code does what its task — the issue body — and the cited analysis
behaviour specify — the acceptance criteria and worked examples come out of the code as written.
An off-by-one, a wrong operand, a sign error or a boundary error is **Major**, and is named with
a concrete failing input rather than as a suspicion. Where the wrong result is a safety
invariant's (a clamp, the floor/cap, the fault path), item 4 governs the severity instead.

**(2) Structural ADR compliance** — the boundaries this project cannot regress. The stack
overlay enumerates them under this item, each with the severity its miss carries. Each miss
names the file and the boundary crossed.

**(3) Code health.** DRY and YAGNI; the change matches the surrounding style and idioms; no dead
code, no speculative generality, no commented-out blocks — **Minor per occurrence**, **Major**
where it is the pattern of the change, so that following its own example reproduces it.

- **Logging follows ADR-0007's once-per-outage rule**, not per-cycle spam — **Minor**: it
  changes no commanded value, but a log the operator stops reading is how the next fault gets
  missed.
- **No magic strings or numbers** — **Major**. A fixed set of states, phases or modes compared
  or assigned as bare string literals belongs in an enum or a named constant; repeated bare
  literals are the finding. The enum form, and the one exception to the rule, are the stack
  overlays' under this item.

**(4) Safety not weakened.** No clamp, floor/cap or fault behaviour is loosened,
short-circuited, or made skippable beyond what the ADRs allow — **Critical**. This is the one
item whose severity does not soften with size: a safety invariant weakened in one branch is
weakened.

**(5) The language bar.** The change passes the checklists the stack overlays name under this
item, over the files those checklists say they apply to. An anti-pattern that can change
runtime behaviour is **Major**; one that only makes the code harder to read is **Minor**.

**(6) Runtime check recorded when the change is observable at runtime.** A change to observable
runtime behaviour carries a **Runtime check** section in the PR description recording what was
driven and what was observed. `definition-of-done.md` owns what counts as observable — it
defines it and routes to the stack overlay under this item for what that is in this stack —
what the section must contain, how it is judged against the diff rather than by its presence,
and the honest cannot-be-driven-yet form; read it there rather than from a summary. A miss is
**Major**, which is the severity that document states and the reason the check is
reviewer-read rather than CI-gated: a mechanical presence check is satisfied by an empty
heading.

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

## Overlays

**Apply the overlays** the profile's declared stacks provide for this work type:
`overlays/<stack>.md` beside this file, its **Done** section read with this file as part of the
same bar. What an overlay is, what a file reading `none` means and what may not live in this file
are this tree's `README.md`'s **Stack overlays**.
