# Work type: `uc` — the `home-assistant` overlay

Stack material for the `uc` work type, read with the core files beside it as one work file, one
bar and one checklist — each core file's **Overlays** section says which section below it takes.
Every entry names the core rule or bar item it extends; what an overlay may and may not say is
this tree's `README.md`'s **Stack overlays**.

## Implement

**The search's tree** — the work file's *Propagating past the analysis layer*: the one targeted
search per in-scope item runs over `custom_components/`.

**What, not how** — the work file's rule: the implementation detail a use-case never carries
is, in this stack, Python, HA services, timer helpers, or persistence.

## Done

**Item 3.1, *What, not how*.** The implementation detail, in this stack, is the list the
*What, not how* entry under **Implement** above carries.

## Review

**Check (A)'s tree** is the one *The search's tree* under **Implement** above names.
