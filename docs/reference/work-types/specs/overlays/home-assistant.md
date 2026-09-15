# Work type: `specs` — the `home-assistant` overlay

Stack material for the `specs` work type, read with the core files beside it as one work file,
one bar and one checklist — each core file's **Overlays** section says which section below it
takes. Nothing here restates a rule of those files: every entry names the rule or the bar item
it extends, and the severity is the item's unless the entry states one. The shape of an overlay
is this tree's `README.md`'s.

## Implement

**Respect the test boundary** — the work file's rule: pure logic → plain pytest; HA-coupled → HA
harness.

**A common mistake** — the work file's list: routing pure-logic tests through the HA harness
(or vice versa).

## Done

**Item 4, *ADR compliance and gates*.** An engine reaching Home
Assistant directly, against ADR-0003, is **Major**.

The records a slice is ordinarily gated on, and the list to read the spec against rather than
the whole log: adapters (0003), package layout (0002/0010), config split (0005),
coordinator/two-clamps (0006), fault-on-`None` (0007), testing split (0009), native naming
(0004). This is the enumeration, for both the author and the reviewer; `implement.md`'s
*Honor the ADRs* rule points here rather than keeping a second copy. It is the usual set, not
a closed one — an ADR outside it that the slice touches is judged by the same item.

**Item 5, *TDD plan quality* — the test boundary.** Each task names its **test boundary
per ADR-0009**: plain pytest for `modes/`/`engines/` (no HA import), HA harness
(`pytest-homeassistant-custom-component` + `MockConfigEntry`) for adapters, coordinator,
entities, and the config flow. A missing boundary, a pure-logic task routed through the HA
harness, or an HA-coupled task tested with plain pytest is **Major**.

## Review

Nothing beyond what the bar's items above carry: the checklist's read-first list reaches the
gating records through the bar's item 4, which this overlay enumerates.
