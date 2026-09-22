#!/usr/bin/env python3
"""The watched-path check: do the three consumers still carry the set the profile declares?

One set of trees decides which files this project's AI review looks at, and it is written down
four times -- once as the source and once inside each consumer, in that consumer's own grammar.
Nothing in the tree failed when the four disagreed: a tree left out of one of them is invisible
in exactly the way a tree nobody thought about is, which is what makes the drift silent. This
script is what notices.

`.claude/profile.yml`'s `review.path_map` is the **source**. It is the only one of the four
that says what a tree is *for* -- the work type whose checklist judges it -- and the only one
in a form a script can read without parsing prose. Routing itself still resolves from
`CLAUDE.md`'s Model selection table, which is where the CI review worker reads it; this copy is
the source of the *set*, not of the routing. The other three are consumers:

  .github/workflows/ai-pipeline.yml   `on.pull_request.paths` -- GitHub's own path filter,
                                      which decides whether any job runs at all
  .github/workflows/_ai-review.yml    the `git diff ... -- <paths>` enumeration in the review
                                      worker's prompt, which decides what a checklist can see
  CLAUDE.md                           the no-label row's path map under **Model selection**,
                                      the human-readable authority and the one that also
                                      carries each tree's work type

Each consumer is **verified** against the source, not generated from it. Why per consumer --
and why the path filter could not be generated even if the others were -- is stated in the
document `CLAUDE.md`'s **Contribution workflow** topic routes to for CI, under the section
naming this check.

Each consumer spells the set in its own grammar, and the translation is this script's:

  path filter     verbatim -- an Actions path filter takes the same glob syntax the source does
  diff pathspec   a trailing `/**` dropped, because a git pathspec names the directory itself
                  (`docs/reference`); a file path and a `*` glob are unchanged
  CLAUDE.md       verbatim, and paired with the work type the source routes it to

  Usage: check-path-map.py [--root DIR] [--warn]

  --root  repository root (default: the script's parent directory)
  --warn  report findings and exit 0 -- for the local pre-commit hook, which must not block a
          commit made halfway through adding a tree

  Exit 0  every consumer carries exactly the source's set (with --warn: always, unless 2)
       1  at least one consumer disagrees; or the source lists a tree twice, or routes one to a
          work type that is not enabled. Every finding names the file, the enumeration inside
          it, and the tree -- "they disagree" is not something an author can act on
       2  usage or environment error: a file that cannot be read or parsed, or a consumer
          whose enumeration cannot be located at all. Located-or-fail rather than
          treated-as-empty on purpose: an enumeration this script cannot find is exactly when
          it knows least, and a check that passes because it looked at nothing is worse than
          no check.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - the wrapper reports this before we are reached
    print("check-path-map: PyYAML is required", file=sys.stderr)
    raise SystemExit(2) from None

SOURCE = ".claude/profile.yml"
PIPELINE = ".github/workflows/ai-pipeline.yml"
REVIEW = ".github/workflows/_ai-review.yml"
GUIDE = "CLAUDE.md"

# The paragraph CLAUDE.md's path map lives in, found by its opening sentence rather than by the
# heading above it: the section can gain paragraphs, and a heading can be renamed, but this
# sentence is the map's own first words.
GUIDE_MARKER = "**The no-label row routes by changed path**"
GUIDE_ARROW = re.compile(r"→\s*`docs/reference/work-types/([^/`]+)/review\.md`")
BACKTICKED = re.compile(r"`([^`]+)`")
# The prompt line, matched on the `git diff` and its `--` separator rather than on the
# surrounding prose, which is free to be reworded.
DIFF_ENUMERATION = re.compile(r"`git diff [^`]*?\s--\s+([^`\n]+)`")


class Unreadable(Exception):
    """A file or an enumeration this script cannot read -- never a disagreement."""


def read(root: str, name: str) -> str:
    try:
        with open(os.path.join(root, name), encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise Unreadable(f"cannot read {name}: {exc}") from exc


def profile_document(text: str) -> dict:
    try:
        profile = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise Unreadable(f"{SOURCE} is not valid YAML: {exc}") from exc
    if not isinstance(profile, dict):
        raise Unreadable(f"{SOURCE} is not a mapping")
    return profile


def source_map(profile: dict) -> list[tuple[str, str]]:
    """(tree, work type) pairs from `review.path_map`, in declaration order."""
    entries = ((profile.get("review") or {}).get("path_map")) or []
    pairs = []
    for entry in entries:
        work_type = (entry or {}).get("work_type")
        for path in (entry or {}).get("paths") or []:
            pairs.append((path, work_type))
    if not pairs:
        raise Unreadable(f"{SOURCE} declares no `review.path_map` entries")
    return pairs


def pipeline_paths(text: str) -> list[str]:
    """`on.pull_request.paths` from the pipeline router."""
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise Unreadable(f"{PIPELINE} is not valid YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise Unreadable(f"{PIPELINE} is not a mapping")
    # PyYAML resolves YAML 1.1 booleans, so the bare key `on:` arrives as True. Both spellings
    # are looked up: a file quoting the key ("on":) is equally valid YAML and would otherwise
    # read as a workflow with no triggers at all.
    trigger = document.get(True, document.get("on"))
    paths = ((trigger or {}).get("pull_request") or {}).get("paths")
    if not paths:
        raise Unreadable(f"{PIPELINE} has no `on.pull_request.paths` filter")
    return list(paths)


def review_pathspec(text: str) -> list[str]:
    """The pathspec of the `git diff ... -- <paths>` line in the review worker's prompt."""
    matches = DIFF_ENUMERATION.findall(text)
    if not matches:
        raise Unreadable(f"{REVIEW} has no `git diff ... -- <paths>` enumeration")
    if len(matches) > 1:
        # Two enumerations mean two answers to "what can a checklist see", and picking one
        # would make this check's verdict depend on which came first in the file.
        raise Unreadable(f"{REVIEW} has {len(matches)} `git diff ... -- <paths>` enumerations")
    # shlex, not split(): the two `*` globs are single-quoted in the prompt so the shell cannot
    # expand them against the runner's checkout, and the quotes are not part of the path.
    return shlex.split(matches[0])


def guide_pairs(text: str) -> list[str]:
    """`tree -> work type` from CLAUDE.md's no-label row, as rendered tokens."""
    start = text.find(GUIDE_MARKER)
    if start < 0:
        raise Unreadable(f"{GUIDE} has no `{GUIDE_MARKER}` paragraph")
    paragraph = text[start + len(GUIDE_MARKER) :]
    end = paragraph.find("\n\n")
    paragraph = paragraph if end < 0 else paragraph[:end]
    tokens: list[str] = []
    cursor = 0
    # Each arrow claims every backticked path since the previous one. Scanning forward rather
    # than globally is what keeps the prose *after* the last arrow -- which names the other
    # enumerations, and `docs/postmortems/**`, in backticks -- out of the map.
    for arrow in GUIDE_ARROW.finditer(paragraph):
        for path in BACKTICKED.findall(paragraph[cursor : arrow.start()]):
            tokens.append(token(path, arrow.group(1)))
        cursor = arrow.end()
    if not tokens:
        raise Unreadable(f"{GUIDE}'s no-label row routes no path to a checklist")
    return tokens


def token(path: str, work_type: str) -> str:
    return f"{path} -> {work_type}"


def as_pathspec(path: str) -> str:
    """A source glob as git spells it: a tree is the directory, everything else is itself."""
    return path[: -len("/**")] if path.endswith("/**") else path


# One entry per consumer: the file, what to call the enumeration inside it, how the source
# spells a tree there, the note a missing tree carries (which says where the tree came from,
# and for a consumer whose spelling differs, that the difference is the translation and not a
# second tree), and how to read the enumeration out of the file.
CONSUMERS = (
    (
        PIPELINE,
        "`on.pull_request.paths`",
        lambda path, work_type: path,
        lambda path, work_type: f"`review.path_map` routes it to `{work_type}`",
        pipeline_paths,
    ),
    (
        REVIEW,
        "the `git diff ... -- <paths>` enumeration",
        lambda path, work_type: as_pathspec(path),
        lambda path, work_type: (
            f"`review.path_map`'s `{path}` (-> `{work_type}`), as a git pathspec"
        ),
        review_pathspec,
    ),
    (
        GUIDE,
        "the no-label row's path map",
        token,
        lambda path, work_type: "`review.path_map` routes it there",
        guide_pairs,
    ),
)


def compare(source: list[tuple[str, str]], text: str, consumer) -> list[str]:
    """Findings for one consumer: what it is missing, what it carries extra, what it repeats."""
    name, what, spell, note, extract = consumer
    want = {spell(path, work_type): (path, work_type) for path, work_type in source}
    found = extract(text)
    findings = []
    for repeated in sorted({t for t in found if found.count(t) > 1}):
        findings.append(f"{name}: {what} lists `{repeated}` more than once")
    for expected in want:
        if expected not in found:
            findings.append(f"{name}: {what} is missing `{expected}` -- {note(*want[expected])}")
    for extra in sorted(set(found) - set(want)):
        findings.append(
            f"{name}: {what} carries `{extra}`, which `{SOURCE}`'s `review.path_map` does not"
        )
    return findings


def source_findings(profile: dict, source: list[tuple[str, str]]) -> list[str]:
    """Findings against the source itself: a repeated tree, or one routed to no enabled type.

    Checked here rather than beside the rest of the profile's self-agreement, because the
    consumers below are compared against whatever this says: a tree routed to a work type with
    no checklist behind it would otherwise be propagated into all three, agreeing perfectly and
    routing nothing. The duplicate rule is the same one `compare` applies to each consumer --
    the source needs it too, and needs it here, because the comparison below is set-based and
    would collapse a repeated tree without a word.
    """
    enabled = list((profile.get("work_types") or {}).get("enabled") or [])
    findings = []
    paths = [path for path, _ in source]
    for repeated in sorted({p for p in paths if paths.count(p) > 1}):
        findings.append(f"{SOURCE}: `review.path_map` lists `{repeated}` more than once")
    for path, work_type in source:
        if work_type not in enabled:
            findings.append(
                f"{SOURCE}: `review.path_map` routes `{path}` to `{work_type}`, "
                "which `work_types.enabled` does not name"
            )
    return findings


def default_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--root", default=default_root())
    parser.add_argument("--warn", action="store_true")
    args = parser.parse_args(argv)

    try:
        profile = profile_document(read(args.root, SOURCE))
        source = source_map(profile)
        findings: list[str] = source_findings(profile, source)
        for consumer in CONSUMERS:
            findings += compare(source, read(args.root, consumer[0]), consumer)
    except Unreadable as exc:
        print(f"check-path-map: {exc}", file=sys.stderr)
        return 2

    if not findings:
        print(
            f"check-path-map: clean ({len(source)} trees, {len(CONSUMERS)} consumers)",
            file=sys.stderr,
        )
        return 0
    prefix = "warning" if args.warn else "check-path-map"
    for finding in findings:
        print(f"{prefix}: {finding}", file=sys.stderr)
    print(
        f"check-path-map: {len(findings)} finding(s) -- "
        f"`{SOURCE}`'s `review.path_map` is the source; change it there and follow it out.",
        file=sys.stderr,
    )
    return 0 if args.warn else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
