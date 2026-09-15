# Work type: `development` — the `python` overlay

Stack material for the `development` work type, read with the core files beside it as one
work file, one bar and one checklist — each core file's **Overlays** section says which section
below it takes. Nothing here restates a rule of those files: every entry names the rule or the
bar item it extends, and the severity is the item's unless the entry states one. The shape of
an overlay is this tree's `README.md`'s.

## Implement

**Pre-commit self-check**, before each commit — the work file's *Building the task*: run the
**Quick review checklist** at the end of the `python-anti-patterns` skill over the diff, and —
where the change touches async code — the checklist in `async-python-patterns` (that skill's
**When this file applies** section is the single statement of which files those are). The
bar's item 5, *The language bar*, is where a miss is judged; running it here is what keeps it
out of the review.

**The linter** — the Definition of Done's *Builds/lints clean*: `ruff check .` and
`ruff format --check .` for product-code and test changes — pair both, not just the first.

## Done

**Item 3, *Code health* — the enum form.** The enum the no-magic-strings rule asks for is
`enum.StrEnum` where the value must still compare and serialise as a plain `str`; the usual
case is a `phase: str` field checked against `"idle"`/`"charging"`. The one exception to the
rule is the `home-assistant` overlay's, under the same item.

**Item 5, *The language bar*.** The checklists the item names: the **Quick review checklist**
at the end of the `python-anti-patterns` skill, and — where the change touches async code — the
checklist in `async-python-patterns`, whose **When this file applies** section is the single
statement of which files those are; a change confined to `modes/`/`engines/` is outside it. Of
the anti-patterns that can change runtime behaviour, anything blocking the event loop is the
first to look for.

## Review

**Further material the bar names** — the checklist's *What to read first*: the two language
skills above, at the bar's item 5. Read each when the item applies; don't fan out across the
tree ahead of that.
