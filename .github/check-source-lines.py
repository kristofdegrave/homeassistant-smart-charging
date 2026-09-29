#!/usr/bin/env python3
"""The `Source:` line check: does every `Source:` line in an issue body point at something real?

A child issue cut by a decomposition carries `Source:` lines naming the documents it was cut
from, and those lines replace the worker's own search for sources -- so a pointer that resolves
to nothing yields an implementation that is silently under-informed. The convention (who
carries the lines, what they stand in for, how finely they are anchored) is the document
`CLAUDE.md`'s **Source lines** topic routes to; this script checks only the form and that each
target exists. It does not judge granularity, which no check can.

A `Source:` line is any line of the body, outside a fenced code block, that begins `Source:`.
Each one must be exactly `Source: <path>` or `Source: <path>#<anchor>` -- one token after the
prefix, trailing whitespace ignored -- where:

  - <path> is repo-relative, under one of the trees `.claude/profile.yml`'s
    `source_lines.trees` lists, with no `..` segment, and names a file that exists;
  - <anchor>, where present, is the GitHub heading anchor of a heading in that file, a
    repeated heading's `-1`, `-2` suffix included.

Anchors are computed with the method check's own heading and slug functions
(.github/check-method.py), so the two checks cannot disagree about what an anchor is.

  Usage: check-source-lines.py (--body FILE | --issue N) [--root DIR] [--ref REF]

  --body   read the issue body from FILE (`-` for stdin)
  --issue  fetch the body of issue N of the profile's repository, through `gh api`
  --root   repository root (default: the script's parent directory)
  --ref    resolve targets against this git ref (e.g. origin/main) rather than the working
           tree; CI checks out the base branch and passes none

  CHECK_SOURCE_LINES_GH, where set, is the command run in place of `gh` -- the tests' fake.

  Exit 0  every `Source:` line resolves, or the body carries none
       1  at least one does not; each finding names the line number, the line and why
       2  usage or environment error: unreadable profile, no `source_lines.trees`, git failing
       3  the body could not be fetched (--issue only). Not a verdict: the caller must not
          read it as a failure of the issue, and CI passes the run with a warning
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("check_method", HERE / "check-method.py")
check_method = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_method)

PREFIX = "Source:"
LINE_RE = re.compile(r"^Source: (\S+)$")


class LookupFailed(Exception):
    """The issue body could not be fetched."""


class EnvError(Exception):
    """The check cannot run: profile or git."""


def load_trees(root: Path) -> list[str]:
    try:
        profile = yaml.safe_load((root / ".claude" / "profile.yml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EnvError(f"cannot read .claude/profile.yml: {exc}") from exc
    trees = ((profile or {}).get("source_lines") or {}).get("trees")
    if not trees:
        raise EnvError("no `source_lines.trees` in .claude/profile.yml")
    return [t if t.endswith("/") else t + "/" for t in trees]


def fetch_body(root: Path, number: str) -> str:
    try:
        profile = yaml.safe_load((root / ".claude" / "profile.yml").read_text(encoding="utf-8"))
        repo = f"{profile['repo']['owner']}/{profile['repo']['name']}"
    except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        raise EnvError(f"cannot read `repo` from .claude/profile.yml: {exc}") from exc
    try:
        out = subprocess.run(
            [
                *shlex.split(os.environ.get("CHECK_SOURCE_LINES_GH", "gh")),
                "api",
                f"repos/{repo}/issues/{number}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise LookupFailed(f"cannot run gh: {exc}") from exc
    if out.returncode != 0:
        raise LookupFailed(f"gh api exited {out.returncode}: {out.stderr.strip()}")
    try:
        return json.loads(out.stdout).get("body") or ""
    except (ValueError, AttributeError) as exc:
        raise LookupFailed(f"gh api returned no issue: {exc}") from exc


class Tree:
    """Read-only view of the repository at the working tree or at a git ref."""

    def __init__(self, root: Path, ref: str | None):
        self.root = root
        self.ref = ref
        if ref is not None:
            self._git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        out = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if out.returncode != 0 and args[0] == "rev-parse":
            raise EnvError(f"git cannot resolve ref {self.ref!r}")
        return out

    def is_file(self, path: str) -> bool:
        if self.ref is None:
            return (self.root / path).is_file()
        out = self._git("cat-file", "-t", f"{self.ref}:{path}")
        return out.returncode == 0 and out.stdout.strip() == "blob"

    def read(self, path: str) -> str:
        if self.ref is None:
            return (self.root / path).read_text(encoding="utf-8")
        return self._git("show", f"{self.ref}:{path}").stdout


def anchors(text: str) -> set[str]:
    """Every GitHub heading anchor in a markdown file, repeated headings suffixed."""
    seen: dict[str, int] = {}
    out = set()
    for _, _, heading in check_method.headings(text):
        base = check_method.slug(heading)
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.add(base if count == 0 else f"{base}-{count}")
    return out


def source_lines(body: str) -> list[tuple[int, str]]:
    return [
        (number, line.rstrip())
        for number, line in check_method.strip_fences(body)
        if line.startswith(PREFIX)
    ]


def problem(target: str, trees: list[str], tree: Tree) -> str | None:
    path, _, anchor = target.partition("#")
    if path.startswith("/") or "\\" in path or ".." in path.split("/"):
        return "the path must be repo-relative, with forward slashes and no `..`"
    if not any(path.startswith(t) for t in trees):
        return "the path is outside every tree `source_lines.trees` allows: " + ", ".join(trees)
    if not tree.is_file(path):
        return "no such file" + (f" at {tree.ref}" if tree.ref else "")
    if "#" in target:
        if not anchor:
            return "an empty anchor"
        if not path.endswith(".md"):
            return "an anchor on a file that is not markdown"
        if anchor not in anchors(tree.read(path)):
            return f"no heading in {path} has the anchor #{anchor}"
    return None


def check(body: str, trees: list[str], tree: Tree) -> list[str]:
    findings = []
    for number, line in source_lines(body):
        m = LINE_RE.match(line)
        if not m:
            why = "not `Source: <path>` or `Source: <path>#<anchor>` with nothing else on the line"
        else:
            why = problem(m.group(1), trees, tree)
        if why:
            findings.append(f"line {number}: {line}\n    {why}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--body")
    src.add_argument("--issue")
    parser.add_argument("--root", default=str(HERE.parent))
    parser.add_argument("--ref")
    args = parser.parse_args()
    root = Path(args.root)
    try:
        trees = load_trees(root)
        tree = Tree(root, args.ref)
        if args.issue is not None:
            body = fetch_body(root, args.issue)
        elif args.body == "-":
            body = sys.stdin.read()
        else:
            body = Path(args.body).read_text(encoding="utf-8")
    except LookupFailed as exc:
        print(f"check-source-lines: lookup failed, no verdict: {exc}", file=sys.stderr)
        return 3
    except (EnvError, OSError) as exc:
        print(f"check-source-lines: {exc}", file=sys.stderr)
        return 2
    findings = check(body.replace("\r\n", "\n"), trees, tree)
    count = len(source_lines(body.replace("\r\n", "\n")))
    if findings:
        print(f"{len(findings)} of {count} `Source:` line(s) do not resolve:")
        for f in findings:
            print(f)
        return 1
    print(f"{count} `Source:` line(s), every one resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
