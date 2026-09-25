#!/usr/bin/env python3
"""The word-budget check: did this change grow a process file past what it may hold?

`.claude/profile.yml`'s `word_budgets` gives each class of file a glob and a cap in words. A
file the change touches may hold at most the larger of its cap and its size on the merge base:
under the cap it may grow to the cap, over it it may only shrink. A class marked `added_only`
is scored only on files the change adds -- an existing ADR is immutable, so its size is not the
change's. A word is a whitespace-separated token; the whole file counts, frontmatter included.

  Usage: check-word-budget.py BASE [--root DIR]

  BASE    the commit the change is measured against; its merge base with HEAD is used
  --root  repository root (default: the script's parent directory)

  Exit 0  every touched file is within its budget
       1  at least one is not; each finding names the file, its size, what it may hold, and
          how many words it has to lose
       2  usage or environment error: no `word_budgets` in the profile, or git failing
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

import yaml


def glob_re(glob: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(out + r"\Z")


def git(root: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", root, *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def words(text: str) -> int:
    return len(text.split())


def score(root: str, merge_base: str, classes: list, line: str) -> str | None:
    status, *paths = line.split("\t")
    old, new = paths[0], paths[-1]
    match = next((c for c in classes if c[0].match(new)), None)
    if status.startswith("D") or match is None:
        return None
    _, cap, added_only = match
    added = status.startswith("A")
    if added_only and not added:
        return None
    size = words(git(root, "show", f"HEAD:{new}"))
    base_size = 0 if added else words(git(root, "show", f"{merge_base}:{old}"))
    allowed = max(cap, base_size)
    if size <= allowed:
        return None
    if base_size <= cap:
        why = f"cap {cap}"
    else:
        why = f"over its cap of {cap}, it may not grow past {base_size}"
    return f"{new}: {size} words ({why}); cut {size - allowed}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()

    with open(os.path.join(args.root, ".claude", "profile.yml"), encoding="utf-8") as f:
        profile = yaml.safe_load(f)
    budgets = (profile or {}).get("word_budgets")
    if not budgets:
        print("check-word-budget: .claude/profile.yml has no word_budgets", file=sys.stderr)
        return 2
    classes = [(glob_re(b["glob"]), b["cap"], b.get("added_only", False)) for b in budgets]

    try:
        merge_base = git(args.root, "merge-base", args.base, "HEAD").strip()
        changes = git(args.root, "diff", "--name-status", "-M", merge_base, "HEAD").splitlines()
        findings = [f for line in changes if (f := score(args.root, merge_base, classes, line))]
    except subprocess.CalledProcessError as e:
        print(f"check-word-budget: git failed: {e.stderr.strip()}", file=sys.stderr)
        return 2

    for finding in findings:
        print(f"check-word-budget: {finding}")
    if findings:
        return 1
    print(f"check-word-budget: clean ({len(changes)} changed files, {len(classes)} classes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
