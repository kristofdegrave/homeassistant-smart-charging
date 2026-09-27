# Work type: `decompose` — the completion bar

What must be true when a `decompose` run ends — parked, at entry 1, or closed, at entry 2 of
`implement.md`. The author self-checks against it before stopping. No reviewer applies it:
the run produces no pull request, and this work type's review is the checklist pass
`implement.md` runs, as `review.md` states. What that pass scores — the body — is the
checklist `CLAUDE.md`'s **Decomposition checklist** topic routes to, and no item of it is
repeated here. This bar scores what the pass cannot see: that it ran, and what the run left on
the tracker.

## At the park (entry 1)

**(1) The body was derived, and the pass ran exactly once against it.** A body parked with no
`reviewer` run behind it, or one the pass was run twice over → **Critical**: the human's read
then rests on an unreviewed body, or the closing step's single-pass rule is broken. A Critical
or Major finding of the pass neither fixed in the body nor filed against the document that
owns it → **Major**.

**(2) The body on the tracker is the fixed body.** Read back after the last edit, before the
park. No read-back → **Major**: the fix is then assumed.

**(3) The parking comment is the executive summary** — the five parts under the headings
`implement.md`'s entry 1 names, each present or `none` with why.
- A part missing → **Major**.
- A part that pastes a body section instead of summarising it → *Clutter*, per the Vocabulary
  entry of `CLAUDE.md`'s **Authoring AI artifacts** topic, at its severities.
- A task in the children part with no Size → **Minor**.

**(4) The comment ends in the parking marker**, as its last line, and it is the only park the
human has not answered. Missing or elsewhere in the comment → **Critical**: the autopilot
cannot then tell the park from any other comment, and re-parks or never proceeds. A second park
over an unanswered one → **Major**.

**(5) `needs-approval` is on the epic and `needs-decision` is not**, read back after the
apply; every other label on the epic and on the `decompose` issue is as the run found it.
Otherwise → **Major**.

**(6) No child exists.** A task issue filed before the human's go → **Critical**: it is the
failure the park exists to prevent, and one it cannot cheaply undo.

**(7) The `decompose` issue is open and *in progress***, not *in review* and not closed →
**Minor**.

## At the close (entry 2)

**(8) Every task in the body has an issue** — `file-task-issue`'s own done line, applied
here: label, board fields, `Source:` lines, edges. A task without one → **Major**. A child
whose Size differs from the summary's, with no line in the closing comment saying why →
**Minor**.

**(9) Every human comment newer than the marker was applied**, and the closing comment says
how. One ignored → **Major**: the human's instruction at the gate was the point of the gate.

**(10) The `decompose` issue is closed by its closing comment**, which lists the children by
number, and it is *done*. Open, or closed without the list → **Major**.

**(11) No clutter** anywhere the run wrote — the body, the summary, the closing comment — as
the *Clutter* entry named under item 3 defines it, at its severities and in its scope.
