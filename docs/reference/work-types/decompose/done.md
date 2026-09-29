# Work type: `decompose` — the completion bar

What must be true when a `decompose` run ends — parked at entry 1, stopped, or closed at entry 2
of `implement.md`. The author self-checks against it before stopping; the run produces no pull
request, so a reviewer applies it — to the parked body and the tracker state — only when a
dispatch reaches this row, which `review.md` says was a misrouting. Why the review is the
checklist pass `implement.md` runs is the `decompose` rule under *Rows that differ from the
rest*, reached from `CLAUDE.md`'s **Model selection**. What that pass scores — the body — is the
checklist `CLAUDE.md`'s **Decomposition checklist** topic routes to, and no item of it is
repeated here. This bar scores what the pass cannot see: that it ran, and what the run left on
the tracker.

## At the park (entry 1)

**(1) The body was derived, and the pass ran exactly once against it.** A body parked with no
`reviewer` run behind it, or one the pass was run twice over → **Critical**: the human's read
then rests on an unreviewed body, or the closing step's single-pass rule is broken. A re-entry
after `implement.md`'s *Out of the body* stop is a fresh draft with its own single pass, not
a second run over the earlier one, and applies every counting comment the entry rule's
not-ready arm names; one not applied → **Major**. A Critical or Major finding of the pass
neither fixed in the body nor handled by that branch → **Major**.
A run past `implement.md`'s entry 1 step 1 without the source it names for the epic's track — a
new-behaviour scope naming no plan task id, a `bug` epic with no confirming reproduction
comment, an `enhancement` epic whose `requirement`/`uc` change is unmerged — a body drafted from
other sources than step 2 names for that track, or a pass dispatched without the track →
**Major**: the spec then derives from nothing the gate checked.

**(2) The body on the tracker is the fixed body.** Read back after the last edit, before the
park. No read-back → **Major**: the fix is then assumed.

**(3) The parking comment is the executive summary** — the five parts under the headings
`implement.md`'s entry 1 names, each present or `none` with why.
- A part missing → **Major**.
- A part that pastes a body section instead of summarising it → *Clutter*, per the Vocabulary
  entry of `CLAUDE.md`'s **Authoring AI artifacts** topic, at its severities.
- A task in the children part with no Size → **Minor**.

**(4) The comment ends in the parking marker**, as its last line, posted under a login that
passes the entry rule's author test, and it is the only park the human has not answered.
Missing or elsewhere in the comment → **Critical**: the autopilot cannot then tell the park
from any other comment, and re-parks or never proceeds. A second park over an unanswered one
→ **Major**; a not-ready park, and the park that follows one, are not over an unanswered park.

**(5) `needs-approval` is on the epic**, read back before the parking comment was posted — the
entry rule's go reads the label's events against that comment's time — and the run added no
other label and removed none, bar `clarify`'s own parking of the `decompose` issue. Otherwise
→ **Major**.

**(6) No child exists.** A task issue filed before the human's go — the label removal the
entry rule reads from the timeline, never a marker or a label state alone → **Critical**: it
is the failure the park exists to prevent, and one it cannot cheaply undo.

**(7) The `decompose` issue is open and *in progress***, not *in review* and not closed →
**Minor**.

## At the close (entry 2)

**(8) Every task in the body has an issue** — `file-task-issue`'s own done line, applied
here. A task without one → **Major**. A changed
Size the closing comment does not explain → **Minor**.

**(9) Every comment `implement.md`'s entry 2 step 1 admits was applied**, and the closing
comment says how; one it does not admit, and any redirect, was reported there, not applied.
Either missed → **Major**: the human's instruction at the gate was the point of the gate.

**(10) The `decompose` issue is closed by its closing comment**, carrying what
`implement.md`'s entry 2 step 3 lists, and it is *done*. Open, or closed without the children
listed → **Major**.

**(11) No clutter** anywhere the run wrote — the body, the summary, the closing comment — as
the *Clutter* entry named under item 3 defines it, at its severities and in its scope.

## At a stop, before or within entry 1

**(12) A stop short of the park leaves the gate readable**: no child exists, and no label on
the epic or the `decompose` issue was added or removed beyond `clarify`'s parking.
- Stopped by *Out of the body*: the filed issue exists, the blocked-by edge from the
  `decompose` issue to it was read back, where a park stood a fresh one with the children
  part `none` names that issue, and (7) holds.
- Parked through `clarify`: that skill's parking rule holds on the `decompose` issue, and (7)
  holds.
- Stopped as picked too early, as still parked, or at the entry rule's last arm: nothing on
  the tracker changed, and the run did not move the `decompose` issue.

A stop that leaves a standing park readable as the go → **Critical**; any other miss →
**Major**.
