#!/usr/bin/env python3
"""The method check: does the method package still hold together as one structure?

Five repo-wide checks, each a structural agreement between files that are edited separately
and drift silently when one moves without the other. Each check re-derives its set from the
files on each run rather than from a list kept here. What IS kept here is the scope each
check runs over (the trees, the role files a work type must hold) and check 5's choice of
WHICH profile keys count as values (below) -- selections, not copies of anything.

  1  anchors, outward   every `CLAUDE.md`'s **Topic** pointer under .claude/**, docs/**
                        (minus the two frozen trees, below) and .github/workflows/**
                        resolves, by prefix, to a `##` heading of CLAUDE.md or to a **Topic**
                        row of its routing table
  2  anchors, inward    in CLAUDE.md and in every file check 1 walks minus the snapshot
                        trees (below): every markdown link resolves, against the directory of
                        the file it is written in, to an existing path and, where it carries a
                        #fragment, to a heading of that markdown file; every repo-rooted path
                        named in backticks -- a file, or a directory written with its trailing
                        slash -- exists. A link is resolved whether or not its text wraps onto
                        a second line. Plus, in CLAUDE.md alone: every routing-table entry
                        links to a document, and no `###` heading in CLAUDE.md or
                        docs/reference/** appears before its `##`
  3  profile agreement  CLAUDE.md's Model selection table has exactly one row per
                        work_types.enabled in .claude/profile.yml; labels.context names the
                        same set; the commit-prefix table of the document the **Definition of
                        Done** topic routes to has a row for every one of those labels;
                        docs/reference/profile.md exists and has a `## Flow` section, and
                        every flow deviation -- a `###` under it -- names, in backticks, at
                        least one work type, each of them enabled
  4  work-type          every enabled work type has review.md, and implement.md and done.md
     completeness       unless its row says its work is `none`; every work file has a
                        `### Skills` rule naming only method skills -- a skill directory the
                        profile does not declare as stack, or a declared non-stack
                        dependency; every work type with an overlay slot (a `## Overlays`
                        section in a label-level role file) has overlays/<stack>.md for every
                        declared stack, no label without a slot has an overlays/ directory,
                        no overlay is named for an undeclared stack, and every stack a
                        dependency declares has a `stacks` entry; every dependency declared
                        `installed: repo` is present; every `layer:` frontmatter, where a
                        file carries one, names a known layer; no overlays/ directory sits
                        under a label that is not enabled or under a branch directory
  5  no profile values  no value from profile.yml (owner, repository name, board name, node
     in method files    ids, status column names) appears in a method-layer file; no stack
                        token (profile.yml `stacks.<stack>.tokens`) and no stack skill name
                        appears in a method-layer file under docs/reference/work-types/

Which layer a file belongs to is a rule, and `layer:` frontmatter is the override for a file
that deviates from it. The defaults: every document under docs/reference/** and every agent
under .claude/agents/ is method; every markdown file of a skill under .claude/skills/ is
method unless the profile's `dependencies` declares the skill, in which case it is a vendored
dependency and belongs to no layer here (it is never scanned, and never edited to say so).
A work-type overlay -- docs/reference/work-types/<label>/overlays/<stack>.md -- is stack by
position: a stack package installs it, and it is never edited to say so either.
Each file's own frontmatter is what overrides, so a skill's reference file can differ from
its SKILL.md. `layer: project` on a file --
docs/reference/profile.md is the standing case -- takes it out of check 5; `layer: stack` as
an override is reserved for a stack file found anywhere but an overlays/ directory.

Why check 5's stack-token half is scoped to the work-type tree and not to every method file:
the issue that introduced it split that tree into method core plus stack overlays, and the
tree is where a stack sentence has a home to move to. The rest of the method (the contribution
workflow, the flow document, the Definition of Done) still spells the stack in places, and
widening the scan there is its own issue -- a blocking gate must not demand a move with no
destination. The scope is a stated limit, not a claim the rest is clean.

The token list is the profile's, hand-kept like check 5's key list: matched as whole words in
any case, with any whitespace (a line wrap included) between the words of a multi-word token,
inside code spans and fences too -- a stack path in backticks is exactly the thing to catch.
A word the method uses everywhere in its own right is deliberately not on it, so a stack
sentence built only from such words passes; that is judgment, and the `workflow` checklist's.

Why the scope of check 1 is wider than the rule that created it: a CI worker prompt is not
bound by the routing rule, and neither is an ADR, a design document or a plan, but all of them
do point at CLAUDE.md sections, so a heading rename would break them exactly as it would
break a skill. Two trees under docs/ are left out on purpose: docs/postmortems/** is a
snapshot of reasoning at a date that is never revised, and docs/archive/** is a previous
iteration kept for the record -- a blocking gate must never ask for an edit the rules forbid,
so a pointer left behind there is history, not a break. Pointers inside fenced code blocks
are skipped, as check 2 skips fenced headings; a pointer in an inline code span is not, which
is why the placeholder below has to be excepted by name.

Why check 2's scope is check 1's trees and not CLAUDE.md alone: a path that does not exist is
a defect wherever it is written, and the case that made it one is docs/reference/work-types/,
where the context label IS a directory name -- renaming a label moves the directory, and every
reference to it, in any file, breaks at once. Which trees are left out of that scope and why is
SNAPSHOT_TREES above; which reference shapes resolve, which are skipped and for what reason, is
resolve_references(). What check 2 cannot do is the other half of a rename: telling the label
`workflow` from the English word. That is judgment, and it stays the `workflow` checklist's.

The one literal exception, so it is a stated limit rather than a surprise: the pointer form is
documented as `` `CLAUDE.md`'s **Topic** `` in the authoring reference and the workflow
checklist, and that placeholder is skipped by name in check 1.

Which profile keys check 5 scans for is chosen, not derived: repo.owner, repo.name,
board.name, board.project_id, every field id and option id under board.fields, and the status
option names. Walking every scalar in the profile would flag label names, colours and
descriptions that method files legitimately spell. A new top-level profile key is therefore
not scanned until it is added here -- the check's one hand-kept list.

How status names are matched in check 5, and why: single words such as `Done` and `Ready` are
ordinary English (`Definition of Done`), so a status name counts as a profile value only in
the form a command would use it -- inside backticks -- or, for a multi-word name such as
`In progress`, as the exact capitalised phrase. A single-word status name written bare is not
this check's business.

Usage:  check-method.py [--root DIR] [--warn]
        --root   the repository to check; default: the git top level, else the cwd
        --warn   report findings but exit 0 -- the pre-commit hook's mode, so a `workflow`
                 change mid-rename can still be committed

Exit 0 clean, 1 findings found (0 with --warn), 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - reported as an environment error below
    yaml = None

LAYERS = {"method", "project", "stack"}
# The project's prose profile; its `## Flow` section is the deviation contract check 3 reads.
PROFILE_DOC = "docs/reference/profile.md"
FLOW_SECTION = "Flow"
# The commit-prefix table check 3 reads: the topic whose routing entry names the document, and
# the section whose first table is keyed by context label. The document itself is never named
# here -- it is whatever that topic's routing-table entry currently links to.
DOD_TOPIC = "Definition of Done"
COMMIT_SECTION = "Commit message conventions"
WORK_TYPES = "docs/reference/work-types"
OVERLAYS_DIR = "overlays"
# The overlay slot a core role file carries, and the rule a work file carries.
OVERLAYS_SECTION = "Overlays"
SKILLS_RULE = "Skills"
ROLE_FILES = ("implement.md", "done.md", "review.md")
# The dependency group whose skills are stack, not method; every other group is method-side.
STACK_GROUP = "stack"
POINTER_PLACEHOLDER = "Topic"
POINTER_TREES = (".claude", "docs", ".github/workflows")
FROZEN_TREES = ("docs/postmortems", "docs/archive")
# Check 2 resolves its targets over the trees check 1 walks, minus these. A dated record is a
# snapshot of what was true when it was written: docs/adl/** states a decision at a date and
# docs/plans/** a plan or design of one build slice, so a path in one is a record of where the
# file was, not a claim about the tree today -- rewriting it to resolve would falsify the
# record. The two frozen trees are excluded for the reason check 1 excludes them. Every other
# tree check 1 walks is live prose that has to resolve.
#
# Check 1 keeps walking docs/adl and docs/plans, and the difference is not an inconsistency:
# the two checks ask different questions of the same file. A pointer is about the method's
# headings as they stand today, which a dated document is as wrong about as any other; a path
# is about the tree the document was describing when it was written.
#
# A vendored dependency skill under .claude/skills/ IS in scope here, deliberately, although
# check 5 never scans one: a repo-rooted path that does not exist is broken for a reader of
# this repository whoever wrote the file, and some of them name one today (`tests/` and
# `tests/test_dashboard.py`). The residual risk is stated rather than designed around -- an
# upstream refresh could add a path this tree does not hold, and the answer then is a fix
# upstream or an exclusion decided on that case, not a silent skip now.
#
# docs/plans is a RETIRED tree (ADR-0044) that is not yet empty: the plans of shipped slices are
# deleted, and the pair of an open slice stays until its epic closes. Its entry here expires with
# the last file, and five other sites expire with it -- the comment above, the fixture in
# .github/test-check-method.sh that needs a docs/plans file to exercise this exclusion, the two
# method documents that describe this tuple, docs/reference/method/ci-pipeline.md and
# docs/reference/method/ai-authoring.md, and the cleanup skill's transition-period paragraph,
# which is also the deletion trigger and says it goes when the tree is empty.
SNAPSHOT_TREES = FROZEN_TREES + ("docs/adl", "docs/plans")
# A topic may wrap onto one following line and no more, so a stray `CLAUDE.md's` with no bold
# nearby cannot swallow a paragraph as its "topic".
POINTER_RE = re.compile(r"`?CLAUDE\.md`?['’]s\s+\*\*([^*\n]+(?:\n[^*\n]+)?)\*\*")
# A markdown link. Its text may wrap onto one following line and no more -- the same bound
# POINTER_RE takes, and for the same reason: prose here wraps at ~100 columns, so a wrapped
# link is ordinary (46 of them sit in the trees check 2 walks), while an unbounded `[` could
# swallow paragraphs and invent a link that was never written. The destination itself never
# wraps.
LINK_RE = re.compile(r"\[[^\]\n]*(?:\n[^\]\n]*)?\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
# A backticked repo path: a file with an extension, or a directory written with its trailing
# slash -- `docs/reference/work-types/workflow/` is the shape a label rename moves, and the
# reason the directory form is matched at all.
BACKTICK_PATH_RE = re.compile(r"`((?:\.?[A-Za-z0-9_-]+/)+(?:[A-Za-z0-9_.-]+\.[A-Za-z0-9]+)?)`")
# Anything with a scheme -- http:, https:, mailto: -- is not a path in this tree.
URL_RE = re.compile(r"[a-z][a-z0-9+.-]*:")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
TABLE_ROW_RE = re.compile(r"^\|(.*)\|\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


class Findings:
    def __init__(self) -> None:
        self.items: list[tuple[int, str, str]] = []

    def add(self, check: int, where: str, message: str) -> None:
        self.items.append((check, where, message))


# --- markdown helpers ---------------------------------------------------------------------


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_fences(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line outside a fenced code block."""
    out = []
    fence = None
    for number, line in enumerate(text.splitlines(), start=1):
        m = FENCE_RE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:
                fence = None
            continue
        if fence is None:
            out.append((number, line))
    return out


def headings(text: str) -> list[tuple[int, int, str]]:
    """(level, line number, heading text) for every ATX heading outside code fences."""
    out = []
    for number, line in strip_fences(text):
        m = HEADING_RE.match(line)
        if m:
            out.append((len(m.group(1)), number, m.group(2)))
    return out


def slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, drop punctuation, spaces to hyphens."""
    text = heading.lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def section(text: str, heading: str) -> str:
    """The lines of one `##` section, from its heading to the next `##` or `#`."""
    lines = strip_fences(text)
    start = None
    for i, (_, line) in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 2 and m.group(2).strip() == heading:
            start = i
            break
    if start is None:
        return ""
    body = []
    for _, line in lines[start + 1 :]:
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= 2:
            break
        body.append(line)
    return "\n".join(body)


def table_rows(text: str) -> list[list[str]]:
    """Cells of the body rows of the FIRST table in `text` (header and separator dropped).

    Only the first: a second table in the same section (a legend, an example) must not feed
    its rows into the one being parsed.
    """
    rows = []
    for line in text.splitlines():
        m = TABLE_ROW_RE.match(line)
        if not m:
            if rows:
                break
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def frontmatter(text: str) -> dict | None:
    """The YAML frontmatter as a dict; None when the file carries none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError:
                return {}
            return data if isinstance(data, dict) else {}
    return None


def normalise(topic: str) -> str:
    return re.sub(r"\s+", " ", topic).strip()


def walk(root: Path, tree: str, suffixes: tuple[str, ...]) -> list[Path]:
    base = root / tree
    if not base.exists():
        return []
    if base.is_file():
        return [base] if base.suffix in suffixes else []
    return sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in suffixes)


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# --- CLAUDE.md structure ---------------------------------------------------------------------


class Guide:
    """What the check reads out of CLAUDE.md: headings, routing topics, the selection table."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.headings = headings(text)
        self.h2 = [h for level, _, h in self.headings if level == 2]
        routing = section(text, "Routing table")
        self.topics: list[tuple[str, str]] = []  # (topic, owner cell)
        for cells in table_rows(routing):
            if len(cells) >= 2:
                m = re.fullmatch(r"\*\*(.+)\*\*", cells[0])
                if m:
                    self.topics.append((normalise(m.group(1)), cells[1]))
        self.selection = section(text, "Model selection")
        self.rows: dict[str, list[str]] = {}
        for cells in table_rows(self.selection):
            if len(cells) >= 4:
                m = re.fullmatch(r"`([^`]+)`", cells[0])
                if m:
                    self.rows[m.group(1)] = cells

    def targets(self) -> list[str]:
        return self.h2 + [t for t, _ in self.topics]

    def resolves(self, topic: str) -> bool:
        return any(target.startswith(topic) for target in self.targets())


# --- the five checks -------------------------------------------------------------------------


def check_outward(root: Path, guide: Guide, findings: Findings) -> None:
    for tree in POINTER_TREES:
        for path in walk(root, tree, (".md", ".yml", ".yaml")):
            if any(rel(root, path).startswith(frozen + "/") for frozen in FROZEN_TREES):
                continue
            raw = read_text(path)
            # Fenced blocks are blanked rather than removed so line numbers stay true.
            kept = {number for number, _ in strip_fences(raw)}
            text = "\n".join(
                line if number in kept else "" for number, line in enumerate(raw.splitlines(), 1)
            )
            for m in POINTER_RE.finditer(text):
                topic = normalise(m.group(1))
                if topic == POINTER_PLACEHOLDER or guide.resolves(topic):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                findings.add(
                    1,
                    f"{rel(root, path)}:{line}",
                    f"pointer `CLAUDE.md`'s **{topic}** matches no `##` heading of CLAUDE.md "
                    "and no routing-table topic (prefix match)",
                )


def top_level(root: Path) -> set[str]:
    """The names directly under the repository root: what a bare path may be rooted at."""
    return {entry.name for entry in root.iterdir()}


def resolve_references(root: Path, path: Path, top: set[str], findings: Findings) -> None:
    """Check 2's target resolution for one file: its links and its backticked repo paths.

    A markdown link is resolved the way a renderer resolves it -- against the directory of the
    file it is written in -- and its #fragment against the headings of a markdown target. So a
    link written repo-rooted from a nested file is a finding, because that is what it is: a
    link that does not render.

    A backticked path has no such base. The repo root is the only anchor it can have, so it is
    resolved there, and only when its first segment names something at the root. A first
    segment that names nothing there -- `engines/soc_target.py`, a path inside the product
    package, or `uc/done.md`, a path inside the work-type tree -- is a partial path whose base
    this check cannot know, and is skipped. What that costs: a reference whose own first
    segment has gone stale reads as a partial path and is skipped with it. The alternative,
    guessing a base, turns every partial path in the repository into a finding.

    An absolute URL is skipped whatever it names, the `github.com/<owner>/<repo>/blob/<ref>/`
    form included. It names a path on a published ref of some repository, which may
    deliberately differ from this working tree, and choosing the ref to resolve it against is
    a different question from whether this tree holds the file. The one such reference in this
    repository sits in .github/ISSUE_TEMPLATE/, a tree neither check walks.

    The narrower skips, so this docstring is the whole list the module header promises it is:
    a link target containing `*` is a pattern and not a path; a link that is an in-page anchor
    alone (`#section`) points at no file; a #fragment is resolved only into a markdown file,
    because a directory and a non-markdown file have no headings to resolve it against; a
    backticked directory counts only with its trailing slash, because `work-types/uc` without
    one cannot be told from an extensionless file or a fragment of prose, and the slash is what
    states the intent; and a backticked path with no `/` at all -- a root-level file such as
    `skills-lock.json` -- is not matched, since one bare word in backticks is far more often a
    name than a path. A backticked path needs no glob guard: BACKTICK_PATH_RE cannot capture a
    `*` in the first place.

    Every skip named here, and the snapshot trees above, has a fixture that pins it, and, where
    a covered spelling of the same defect exists, one that fails on it. The known limit that is
    NOT a skip: a link whose text wraps over more than two lines is not matched at all.
    """
    where = rel(root, path)
    seen: set[str] = set()
    # Matched over the whole file rather than line by line, because a link's text wraps: a
    # per-line scan silently skipped every wrapped link, which is the commonest link shape in
    # this repository's prose. Fenced lines are blanked rather than dropped, as check 1 blanks
    # them, so an offset still gives the true line -- and a finding points at the line the link
    # STARTS on, computed from the match offset, not from any loop index.
    raw = read_text(path)
    kept = {number for number, _ in strip_fences(raw)}
    text = "\n".join(
        line if number in kept else "" for number, line in enumerate(raw.splitlines(), 1)
    )

    def line_of(offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    for m in LINK_RE.finditer(text):
        target = m.group(1)
        if target.startswith("#") or URL_RE.match(target) or "*" in target:
            continue
        if target in seen:
            continue
        seen.add(target)
        file_part, _, fragment = target.partition("#")
        if not file_part:
            continue
        number = line_of(m.start())
        resolved = path.parent / file_part
        if not resolved.exists():
            findings.add(2, f"{where}:{number}", f"link target {file_part} does not exist")
            continue
        if fragment and resolved.is_file() and resolved.suffix == ".md":
            if fragment not in {slug(h) for _, _, h in headings(read_text(resolved))}:
                findings.add(
                    2,
                    f"{where}:{number}",
                    f"link {target}: no heading in {file_part} has that anchor",
                )
    for m in BACKTICK_PATH_RE.finditer(text):
        target = m.group(1)
        if target in seen:
            continue
        seen.add(target)
        if target.split("/")[0] not in top:
            continue
        if not (root / target).exists():
            findings.add(
                2, f"{where}:{line_of(m.start())}", f"names {target}, which does not exist"
            )


def check_inward(root: Path, guide: Guide, findings: Findings) -> None:
    for topic, owner in guide.topics:
        if not LINK_RE.search(owner):
            findings.add(2, "CLAUDE.md", f"routing-table entry **{topic}** links to no document")
    top = top_level(root)
    files = [root / "CLAUDE.md"]
    for tree in POINTER_TREES:
        for path in walk(root, tree, (".md", ".yml", ".yaml")):
            if any(rel(root, path).startswith(snapshot + "/") for snapshot in SNAPSHOT_TREES):
                continue
            files.append(path)
    for path in files:
        resolve_references(root, path, top, findings)
    docs = [root / "CLAUDE.md"] + walk(root, "docs/reference", (".md",))
    for path in docs:
        under_h2 = False
        for level, number, heading in headings(read_text(path)):
            if level == 2:
                under_h2 = True
            elif level == 3 and not under_h2:
                findings.add(
                    2, f"{rel(root, path)}:{number}", f"`### {heading}` sits under no `##`"
                )


def check_profile_agreement(root: Path, guide: Guide, profile: dict, findings: Findings) -> None:
    enabled = list((profile.get("work_types") or {}).get("enabled") or [])
    rows = set(guide.rows)
    for label in sorted(set(enabled) - rows):
        findings.add(
            3,
            "CLAUDE.md",
            f"work type `{label}` is enabled in profile.yml but has no Model selection row",
        )
    for label in sorted(rows - set(enabled)):
        findings.add(
            3,
            "CLAUDE.md",
            f"Model selection row `{label}` is not an enabled work type in profile.yml",
        )
    context = [entry.get("name") for entry in ((profile.get("labels") or {}).get("context") or [])]
    if sorted(context) != sorted(enabled):
        findings.add(
            3,
            ".claude/profile.yml",
            f"labels.context {sorted(context)} and work_types.enabled {sorted(enabled)} "
            "name different sets",
        )
    # The watched-path set -- `review.path_map` and the three enumerations that consume it --
    # is deliberately not this check's. It belongs to .github/check-path-map.py, whole: one set
    # with one owner, rather than this check holding two of the four copies to each other and
    # something else holding the rest. That script's header states the split from its side.
    check_flow_deviations(root, enabled, findings)
    check_commit_prefixes(root, guide, enabled, findings)


def check_commit_prefixes(root: Path, guide: Guide, enabled: list[str], findings: Findings) -> None:
    """Every enabled context label is keyed by the commit-prefix table.

    The table claims a prefix per context label, so a label enabled without a row leaves its
    author in the fall-through row and pointed at the wrong prefix -- the drift this check
    exists to refuse. Both ends are re-derived: the labels from the profile, the document from
    whatever the **Definition of Done** topic links to, so moving the file moves the check with
    it. Two stated limits. One direction only: a row for a label the profile no longer declares
    is indistinguishable from the fall-through row's own backticked labels -- the key set below
    absorbs every backticked span in a row's first cell, `bug` and `enhancement` included -- so a
    retired label's row is the reviewer's to catch, not this check's. And the
    topic's owner cell is read for its FIRST link: the cell this one carries holds exactly one,
    where other routing-table cells hold two, so a cell that ever leads with another document
    would need the first link that resolves instead.
    """
    owner = next((cell for topic, cell in guide.topics if topic.startswith(DOD_TOPIC)), None)
    if owner is None:
        return  # check 1 already reports a routing table with no such topic
    link = LINK_RE.search(owner)
    if link is None:
        return  # check 2 already reports a topic that links to no document
    doc = link.group(1).partition("#")[0]
    path = root / doc
    if not path.is_file():
        return  # check 2 already reports a link target that does not exist
    text = read_text(path)
    prefixes = section(text, COMMIT_SECTION)
    if not prefixes:
        findings.add(3, doc, f"`## {COMMIT_SECTION}` is absent or empty")
        return
    where = f"{doc}:{next(n for _, n, h in headings(text) if h == COMMIT_SECTION)}"
    keyed: set[str] = set()
    for cells in table_rows(prefixes):
        if cells:
            keyed.update(re.findall(r"`([^`]+)`", cells[0]))
    if not keyed:
        findings.add(3, where, f"`## {COMMIT_SECTION}` has no table keyed by context label")
        return
    for label in sorted(set(enabled) - keyed):
        findings.add(3, where, f"context label `{label}` has no commit-prefix row")


def check_flow_deviations(root: Path, enabled: list[str], findings: Findings) -> None:
    """The profile document has a `## Flow`, and every `###` under it names enabled work types.

    The section's shape is the flow document's contract: no `###` means the default flow, and
    each `###` is one deviation whose heading names, in backticks, the work type of the stage
    it changes -- every backticked span in the heading is read as one. A deviation naming no
    work type cannot be placed against a stage; one naming a work type the project does not
    enable describes a stage the flow already skips. A profile document with no `## Flow` at
    all has stated neither shape, so it is a finding too -- and so is no profile document at
    all: it is the profile's prose half, the standing `layer: project` case, and the only
    place the contract can be stated.
    """
    path = root / PROFILE_DOC
    if not path.is_file():
        findings.add(
            3, PROFILE_DOC, "the profile document is absent (it carries the flow contract)"
        )
        return
    lines = strip_fences(read_text(path))
    start = None
    for i, (_, line) in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 2 and m.group(2).strip() == FLOW_SECTION:
            start = i
            break
    if start is None:
        findings.add(3, PROFILE_DOC, f"has no `## {FLOW_SECTION}` section (the flow contract)")
        return
    for number, line in lines[start + 1 :]:
        m = HEADING_RE.match(line)
        if not m:
            continue
        if len(m.group(1)) <= 2:
            break
        if len(m.group(1)) != 3:
            continue
        where = f"{PROFILE_DOC}:{number}"
        names = re.findall(r"`([^`]+)`", m.group(2))
        if not names:
            findings.add(
                3, where, f"flow deviation `### {m.group(2)}` names no work type in backticks"
            )
        for name in names:
            if name not in enabled:
                findings.add(
                    3,
                    where,
                    f"flow deviation names `{name}`, which is not an enabled work type",
                )


def declared_dependencies(profile: dict) -> dict[str, dict]:
    """{name: entry} for every declared dependency; each entry gains its group under `_group`."""
    deps = profile.get("dependencies") or {}
    out: dict[str, dict] = {}
    for group, entries in deps.items() if isinstance(deps, dict) else []:
        for entry in entries or []:
            if isinstance(entry, dict) and entry.get("name"):
                out[str(entry["name"])] = {**entry, "_group": str(group)}
    return out


def stack_dependencies(deps: dict[str, dict]) -> dict[str, dict]:
    return {name: e for name, e in deps.items() if e.get("_group") == STACK_GROUP}


def declared_stacks(profile: dict) -> dict[str, list[str]]:
    """{stack: tokens} for every stack the profile declares under `stacks`."""
    out: dict[str, list[str]] = {}
    stacks = profile.get("stacks") or {}
    for name, spec in stacks.items() if isinstance(stacks, dict) else []:
        tokens = (spec or {}).get("tokens") or [] if isinstance(spec, dict) else []
        out[str(name)] = [str(t) for t in tokens if str(t).strip()]
    return out


def is_overlay(root: Path, path: Path) -> bool:
    """docs/reference/work-types/<label>/overlays/<stack>.md -- stack by position."""
    parts = Path(rel(root, path)).parts
    prefix = Path(WORK_TYPES).parts
    return (
        len(parts) == len(prefix) + 3
        and parts[: len(prefix)] == prefix
        and parts[-2] == OVERLAYS_DIR
        and path.suffix == ".md"
    )


def has_heading(text: str, level: int, title: str) -> bool:
    return any(lv == level and h.strip() == title for lv, _, h in headings(text))


def rule_body(text: str, title: str) -> str:
    """The lines of one `###` rule, from its heading to the next heading of level 3 or above."""
    lines = strip_fences(text)
    start = None
    for i, (_, line) in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 3 and m.group(2).strip() == title:
            start = i
            break
    if start is None:
        return ""
    body = []
    for _, line in lines[start + 1 :]:
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) <= 3:
            break
        body.append(line)
    return "\n".join(body)


def check_work_type_shape(
    root: Path, guide: Guide, profile: dict, deps: dict[str, dict], findings: Findings
) -> None:
    """The Skills rule in every work file; the overlay slot and the files that fill it."""
    enabled = list((profile.get("work_types") or {}).get("enabled") or [])
    stacks = declared_stacks(profile)
    stack_deps = stack_dependencies(deps)
    for name, entry in sorted(stack_deps.items()):
        stack = entry.get("stack")
        if stack is not None and str(stack) not in stacks:
            findings.add(
                4,
                ".claude/profile.yml",
                f"dependency `{name}` declares stack `{stack}`, which has no `stacks` entry",
            )
    method_skills = {name for name, e in deps.items() if e.get("_group") != STACK_GROUP}
    skills_dir = root / ".claude/skills"
    if skills_dir.is_dir():
        method_skills |= {
            p.name for p in skills_dir.iterdir() if p.is_dir() and p.name not in stack_deps
        }
    for label in enabled:
        directory = root / WORK_TYPES / label
        row = guide.rows.get(label)
        review_only = bool(row) and row[1].lower().startswith("none")
        work_file = directory / "implement.md"
        if not review_only and work_file.is_file():
            text = read_text(work_file)
            where = f"{WORK_TYPES}/{label}/implement.md"
            if not has_heading(text, 3, SKILLS_RULE):
                findings.add(4, where, f"work file has no `### {SKILLS_RULE}` rule")
            else:
                for skill in re.findall(r"`([^`]+)`", rule_body(text, SKILLS_RULE)):
                    if skill not in method_skills:
                        findings.add(
                            4,
                            where,
                            f"`### {SKILLS_RULE}` names `{skill}`, which is not a method skill "
                            "or a declared method dependency",
                        )
        slot = any(
            (directory / role).is_file()
            and has_heading(read_text(directory / role), 2, OVERLAYS_SECTION)
            for role in ROLE_FILES
        )
        overlays = directory / OVERLAYS_DIR
        present = (
            {p.stem for p in overlays.iterdir() if p.is_file() and p.suffix == ".md"}
            if overlays.is_dir()
            else set()
        )
        where = f"{WORK_TYPES}/{label}/{OVERLAYS_DIR}/"
        if slot:
            for stack in sorted(set(stacks) - present):
                findings.add(
                    4,
                    where,
                    f"work type `{label}` has an overlay slot but no {stack}.md for declared "
                    f"stack `{stack}` (a file reading `none` states that the stack adds nothing)",
                )
        elif overlays.is_dir():
            findings.add(
                4,
                where,
                f"work type `{label}` has an {OVERLAYS_DIR}/ directory but no `## "
                f"{OVERLAYS_SECTION}` slot in any of its role files",
            )
        for stack in sorted(present - set(stacks)):
            findings.add(
                4, f"{where}{stack}.md", f"overlay for `{stack}`, which is not a declared stack"
            )
    # Overlay directories the loop above cannot see: under a label that is not enabled, and
    # under a branch directory -- an overlay sits at the label's own level, never deeper.
    tree = root / WORK_TYPES
    if tree.is_dir():
        for label_dir in sorted(p for p in tree.iterdir() if p.is_dir()):
            if label_dir.name not in enabled and (label_dir / OVERLAYS_DIR).is_dir():
                findings.add(
                    4,
                    f"{WORK_TYPES}/{label_dir.name}/{OVERLAYS_DIR}/",
                    f"{OVERLAYS_DIR}/ under `{label_dir.name}`, which is not an enabled work type",
                )
            for branch in sorted(p for p in label_dir.iterdir() if p.is_dir()):
                if branch.name != OVERLAYS_DIR and (branch / OVERLAYS_DIR).is_dir():
                    findings.add(
                        4,
                        f"{rel(root, branch)}/{OVERLAYS_DIR}/",
                        f"{OVERLAYS_DIR}/ under a branch directory; an overlay sits at the "
                        "label's own level",
                    )


def resolve_layer(
    root: Path, path: Path, default: str, findings: Findings, layers: dict[str, str]
) -> None:
    """Record the file's layer: the tree's default, unless `layer:` frontmatter overrides it."""
    where = rel(root, path)
    data = frontmatter(read_text(path))
    value = None if data is None else data.get("layer")
    if value is None:
        layers[where] = default
    elif str(value) not in LAYERS:
        findings.add(4, where, f"`layer: {value}` is not one of {sorted(LAYERS)}")
    else:
        layers[where] = str(value)


def check_completeness(
    root: Path, guide: Guide, profile: dict, findings: Findings
) -> dict[str, str]:
    """Returns {path: layer} for every file the layer rule places -- check 5's input."""
    layers: dict[str, str] = {}
    enabled = list((profile.get("work_types") or {}).get("enabled") or [])
    for label in enabled:
        directory = root / "docs/reference/work-types" / label
        row = guide.rows.get(label)
        review_only = bool(row) and row[1].lower().startswith("none")
        required = ["review.md"] if review_only else ["implement.md", "done.md", "review.md"]
        for name in required:
            if not (directory / name).is_file():
                findings.add(
                    4,
                    f"docs/reference/work-types/{label}/",
                    f"enabled work type `{label}` has no {name}",
                )
    deps = declared_dependencies(profile)
    for name, entry in sorted(deps.items()):
        if (
            entry.get("installed") == "repo"
            and not (root / ".claude/skills" / name / "SKILL.md").is_file()
        ):
            findings.add(
                4,
                f".claude/skills/{name}/",
                f"declared dependency `{name}` is installed: repo but absent",
            )
    skills = root / ".claude/skills"
    if skills.is_dir():
        for directory in sorted(p for p in skills.iterdir() if p.is_dir()):
            skill = directory / "SKILL.md"
            if not skill.is_file():
                findings.add(4, rel(root, directory) + "/", "skill directory has no SKILL.md")
            elif directory.name not in deps:
                for path in walk(root, rel(root, directory), (".md",)):
                    resolve_layer(root, path, "method", findings, layers)
    for path in walk(root, ".claude/agents", (".md",)):
        resolve_layer(root, path, "method", findings, layers)
    for path in walk(root, "docs/reference", (".md",)):
        default = "stack" if is_overlay(root, path) else "method"
        resolve_layer(root, path, default, findings, layers)
    check_work_type_shape(root, guide, profile, deps, findings)
    return layers


def profile_values(profile: dict) -> list[tuple[str, re.Pattern[str]]]:
    """(label, pattern) for every value the method must not spell."""
    values: list[tuple[str, re.Pattern[str]]] = []

    def token(label: str, value) -> None:
        if value is None or str(value).strip() == "":
            return
        values.append((label, re.compile(r"(?<![\w-])" + re.escape(str(value)) + r"(?![\w-])")))

    repo = profile.get("repo") or {}
    token("repo.owner", repo.get("owner"))
    token("repo.name", repo.get("name"))
    board = profile.get("board") or {}
    token("board.name", board.get("name"))
    token("board.project_id", board.get("project_id"))
    for field, spec in (board.get("fields") or {}).items():
        token(f"board.fields.{field}.id", (spec or {}).get("id"))
        for option, option_id in ((spec or {}).get("options") or {}).items():
            token(f"board.fields.{field}.options.{option}", option_id)
    status = ((board.get("fields") or {}).get("status") or {}).get("options") or {}
    for name in status:
        name = str(name)
        escaped = re.escape(name)
        pattern = f"`{escaped}`"
        if " " in name:
            pattern += r"|(?<!\w)" + escaped + r"(?!\w)"
        values.append((f"status `{name}`", re.compile(pattern)))
    return values


def stack_tokens(profile: dict) -> list[tuple[str, re.Pattern[str]]]:
    """(label, pattern) for every stack token and stack skill name a core file must not spell.

    Whole words, any case; a multi-word token matches across any whitespace, a line wrap
    included, which is why check 5 runs these over the file's text rather than line by line.
    """
    out: list[tuple[str, re.Pattern[str]]] = []
    for stack, tokens in declared_stacks(profile).items():
        for token in tokens:
            words = [re.escape(w) for w in token.split()]
            pattern = r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)"
            out.append((f"stack token `{token}` ({stack})", re.compile(pattern, re.IGNORECASE)))
    for name in sorted(stack_dependencies(declared_dependencies(profile))):
        out.append(
            (f"stack skill `{name}`", re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])"))
        )
    return out


def check_profile_values(
    root: Path, profile: dict, layers: dict[str, str], findings: Findings
) -> None:
    values = profile_values(profile)
    tokens = stack_tokens(profile)
    for where, layer in sorted(layers.items()):
        if layer != "method":
            continue
        text = read_text(root / where)
        for number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in values:
                if pattern.search(line):
                    findings.add(
                        5, f"{where}:{number}", f"method file spells profile value {label}"
                    )
        if not where.startswith(WORK_TYPES + "/"):
            continue
        for label, pattern in tokens:
            for m in pattern.finditer(text):
                number = text.count("\n", 0, m.start()) + 1
                findings.add(5, f"{where}:{number}", f"core work-type file spells {label}")


# --- entry point ----------------------------------------------------------------------------


def default_root() -> Path:
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if top:
            return Path(top)
    except (OSError, subprocess.CalledProcessError):
        pass
    return Path.cwd()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="The method check.")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--warn", action="store_true")
    args = parser.parse_args(argv)
    root = (args.root or default_root()).resolve()

    if yaml is None:
        print("check-method: PyYAML is not importable in this Python", file=sys.stderr)
        return 2
    guide_path = root / "CLAUDE.md"
    profile_path = root / ".claude/profile.yml"
    for required in (guide_path, profile_path):
        if not required.is_file():
            print(f"check-method: cannot read {required}", file=sys.stderr)
            return 2
    try:
        profile = yaml.safe_load(read_text(profile_path)) or {}
    except yaml.YAMLError as exc:
        print(f"check-method: {profile_path} is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(profile, dict):
        print(f"check-method: {profile_path} is not a mapping", file=sys.stderr)
        return 2

    guide = Guide(read_text(guide_path))
    findings = Findings()
    check_outward(root, guide, findings)
    check_inward(root, guide, findings)
    check_profile_agreement(root, guide, profile, findings)
    layers = check_completeness(root, guide, profile, findings)
    check_profile_values(root, profile, layers, findings)

    names = {
        1: "anchors, outward",
        2: "anchors, inward",
        3: "profile agreement",
        4: "work-type completeness",
        5: "no profile or stack values in method files",
    }
    if not findings.items:
        print(
            "check-method: clean "
            f"({sum(1 for v in layers.values() if v == 'method')} method files, "
            f"{len(guide.rows)} work-type rows)"
        )
        return 0
    prefix = "warning" if args.warn else "error"
    for check, where, message in sorted(findings.items):
        print(f"{prefix}: [{check} {names[check]}] {where}: {message}")
    print(f"check-method: {len(findings.items)} finding(s)")
    return 0 if args.warn else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
