# Work types `uc` and `requirement` — the `home-assistant` overlay

Stack material for the `uc` work type — and for the `requirement` row wherever it routes to the
`uc` files — read with the core files beside it as one work file, one bar and one checklist.
Each core file's **Overlays** section says which section below it takes. Nothing here restates a
rule of those files: every entry names the rule or the bar item it extends, and the severity is
the item's unless the entry states one. The shape of an overlay is this tree's `README.md`'s.

## Implement

**The search's tree** — the work file's *Propagating past the analysis layer*: the one targeted
search per in-scope item runs over `custom_components/`.

**What, not how** — the work file's rule: the implementation detail a use-case never carries
is, in this stack, Python, HA services, timer helpers, or persistence.

## Done

**Item 3.1, *What, not how*.** The implementation detail, in this stack: Python modules, HA
services, timer helpers, persistence.

## Review

**Check (A)'s tree.** The one targeted `Grep` per in-scope item runs over `custom_components/`.
