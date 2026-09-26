---
name: improve-architecture
description: Use in an interactive session only when the human partner asks for an architecture review of this codebase — to find deepening opportunities and walk one through. Never self-invoke it, and never in a non-interactive run, since its dialogue blocks on answers nothing will provide.
---

# Improve architecture

How this project runs `improve-codebase-architecture`. That skill is vendored unchanged, and
it cannot be started with the Skill tool, so read
`.claude/skills/improve-codebase-architecture/SKILL.md` and follow it. It calls
`codebase-design` and `domain-modeling` by name, and those two are vendored unchanged as well.
All three are written for a generic repository. Where this skill differs from them, this
skill wins:

1. **`CONTEXT.md` is the glossary in `docs/analysis/system-overview.md`** — its **Ubiquitous
   Language** section. Read the domain vocabulary there. Never create or write a `CONTEXT.md`.
   When a term is new or sharpened, file a `requirement` issue for it with the
   `file-task-issue` skill, and do not edit the glossary inline.
2. **Upstream's `docs/adr` is `docs/adl/`**, and it is read before any candidate is proposed.
   Where the upstream skill would write or offer an ADR, file an `adr` issue with
   `file-task-issue` instead. The `adr` work type drafts it; numbering, review and immutability are
   `CLAUDE.md`'s **Architecture Decision Records (ADRs)** topic. Never write an ADR directly.
3. **`grilling` is `clarify`.** Every question put to the human partner, including "which of
   these would you like to explore?", goes through the `clarify` skill.
4. **The HTML report stays in the OS temp directory**, as the upstream skill already says.
   Nothing it writes lands in the repository.
5. **An accepted candidate becomes an issue**, filed with `file-task-issue`: an `idea` issue,
   or an epic, as `CLAUDE.md`'s **Idea-to-product flow** decides for its shape. It is never a
   direct code change, and this skill stops once the issue is filed. The issue then follows
   `CLAUDE.md`'s **Contribution workflow**.
