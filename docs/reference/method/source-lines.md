# Source lines: what a decomposition-cut child was cut from

A child issue cut by a decomposition carries `Source:` lines naming the documents it was cut
from, and those lines replace the worker's own search for sources (ADR-0044). This document owns
the convention: who carries them, their form, how finely they point, and what they do not stand
in for. How the decomposer picks an entry's sources is the closing step of the flow
`CLAUDE.md`'s **Idea-to-product flow** topic routes to; the check that every line resolves is
[ci-pipeline.md](ci-pipeline.md)'s **The `Source:` line check**.

## Who carries them

- **Every child filed by a decomposition** — the closing step's step 4, one line per source
  its task entry's **Sources** key names, so two sections of one document are two lines.
- **No issue filed outside one.** Nobody determined its sources in advance, so its work file's
  instruction to go and find them is the right one, and a `Source:` line there would claim a
  provenance nobody established. The prefix is reserved: provenance on such an issue is written
  in prose, never on a line beginning `Source:`. That is a filing rule the check cannot
  enforce — it fails only a line that does not resolve, and cannot tell who cut the issue.

## The form

- `Source: <path>` or `Source: <path>#<anchor>` — at the start of the line, one per line,
  nothing else on it, so a script finds and resolves it without reading prose.
- `<path>` is repo-relative and lies under a tree the profile's `source_lines.trees` allows —
  documents only. An edge to another issue is a native sub-issue or blocked-by edge, never a
  `Source:` line; a code path is what the task changes, not what it was cut from.
- `<anchor>` is the heading anchor GitHub renders for a heading of that file.

## How finely

The smallest self-contained unit the task turns on: a section where it turns on one, the whole
file where the document is argued as a whole. The anchor is optional, and a bare path is a
legitimate answer rather than a lazy one. The profile's `source_lines.whole_file` names the
classes of document this project argues as wholes, where a bare path is the default and an
anchor into one needs a reason. The lines are one provenance pointer set, not a relevance
survey: the documents the entry was cut from, not every document the task might touch.

## What they stand in for, and what not

- **For the worker they are the sources.** The work file of a row a decomposition cuts reads
  what the lines name and stops there. Where that does not answer what the task requires, the
  worker finds the rest and states in the PR description — or where its work file reports, for
  a row that opens none — that it had to and what it read. That report is the only signal a
  decomposer's miss ever produces, so omitting it is a defect in the PR, not a courtesy
  skipped.
- **They are provenance, never a discovery result.** They never satisfy a search a work file or
  template requires to be run from scratch, and a `Source:` line is never a hit of one — an
  ADR's Blast radius is the standing case.
