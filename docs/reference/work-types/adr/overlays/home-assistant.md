# Work type: `adr` — the `home-assistant` overlay

Stack material for the `adr` work type, read with the core files beside it as one work file, one
bar and one checklist — each core file's **Overlays** section says which section below it takes.
Every entry names the core rule or bar item it extends; what an overlay may and may not say is
this tree's `README.md`'s **Stack overlays**.

## Implement

Nothing: how an ADR is written does not depend on the stack.

## Done

**Item 1, *It should be an ADR at all* — the worthiness test's examples in this stack.** A
choice about structure that would be expensive to reverse or that materially constrains future
options: how integration entities map to hardware, the shape of a config-entry schema, a change
to the coordinator/control-loop structure. Under the calibration test, a *product-code* choice
that stays architectural even when well encapsulated: a config-entry schema shape.

## Review

Nothing: the record is judged against the log and the bar, neither of which is the stack's.
