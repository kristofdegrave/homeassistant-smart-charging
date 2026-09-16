#!/usr/bin/env python3
"""The upstream-pin drift check: has anything the project vendors moved since it was pinned?

Every skill this project did not write itself is declared in .claude/profile.yml's
`dependencies` -- the provenance manifest -- with a `pin` recording the upstream state it was
last reconciled with. Nothing fails when upstream moves on: the copy here keeps working and
the pin keeps claiming a reconciliation that is no longer true. This script is what notices.

It reads the manifest, asks GitHub what each pinned path looks like upstream today, and writes
a Markdown report of everything that no longer matches. It never edits a skill and never edits
the manifest: several of these copies are adaptations rather than copies, so an upstream change
is a question for a human, not a patch to apply. Acting on the answer -- adopt the change, or
decide it does not apply -- bumps the pin in the PR that records the decision, which is what
stops the report reappearing.

  Usage: check-upstream-drift.py [--root DIR] [--out FILE] [--responses FILE]
                                 [--validate] [--markers]

  --root       repository root (default: the script's parent directory)
  --out        write the Markdown report here (default: stdout)
  --responses  read upstream answers from a JSON file instead of the network, so the
               self-test never depends on api.github.com or on rate limits. Shape:
               {"<source>|<path>": {"sha": "...", "date": "..."}}, or {"error": "..."} to
               simulate a failed lookup, or {} for a path no commit touches.
  --validate   parse the manifest and check every pin's scheme, then stop. No network, so a
               PR that edits the manifest can run it as an ordinary check -- which is where a
               malformed row has to fail, rather than a week later in the scheduled job.
  --markers    print the two markers delimiting the generated report, then stop. The workflow
               reads them from here rather than keeping its own copy.

  Exit 0  every pin still matches upstream; no report is written
       1  at least one row needs a human -- the report says which and why
       2  usage or environment error, or a lookup that did not answer

One verdict per row, and the difference between them matters:

  current       the pinned commit is still the newest commit touching the path upstream
  drifted       upstream moved; the report links the compare view between the two commits
  unresolvable  the pin is a `sha256:` content hash of SKILL.md recorded by the marketplace
                installer, and the installer's hash function is not reproducible here -- a
                locally computed sha256 of the same bytes does not match a lockfile hash even
                for a copy that never diverged. So these rows can be neither confirmed nor
                refuted, and reporting them as "drifted" would be a claim this script cannot
                make. They are reported once, as needing reconciliation to a `commit:` pin.
  missing       no commit upstream touches the path at all: renamed, deleted, or the whole
                repository moved. Reported, not silently passed -- it is the loudest kind of
                drift, and the one a naive "compare the shas" check reads as "no change".

A lookup that errors is not a verdict: it exits 2 and writes nothing, so a flaky API minute
fails the run visibly instead of producing a report that quietly omits rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

try:
    import yaml
except ImportError:  # pragma: no cover - the wrapper reports this before we are reached
    print("check-upstream-drift: PyYAML is required", file=sys.stderr)
    raise SystemExit(2) from None

API = "https://api.github.com"
# The report is delimited rather than merely tagged, so the workflow can replace exactly what
# this script generated and leave anything a human wrote around it alone. Both are printed by
# --markers: the workflow reads them from here rather than keeping a second copy that could
# drift into matching nothing.
MARKER = "<!-- ai-upstream-drift-report -->"
MARKER_END = "<!-- /ai-upstream-drift-report -->"


class UpstreamLookupFailed(Exception):
    """An upstream lookup that did not answer -- never a drift verdict."""


def manifest_rows(profile: dict) -> list[dict]:
    """Flatten `dependencies` into one row per declared dependency, in declaration order.

    The group (`method`, `stack`, or any later one) is carried through rather than enumerated:
    a group added to the profile is checked without this script changing.
    """
    deps = profile.get("dependencies")
    if deps is None:
        return []
    if not isinstance(deps, dict):
        raise ValueError("dependencies is not a mapping")
    rows = []
    for group, entries in deps.items():
        for entry in entries or []:
            missing = [k for k in ("name", "source", "path", "pin") if not entry.get(k)]
            if missing:
                raise ValueError(
                    f"dependency {entry.get('name', '<unnamed>')!r} in group {group!r} "
                    f"is missing {', '.join(missing)}"
                )
            rows.append({"group": group, **entry})
    return rows


def latest_commit(source: str, path: str, token: str | None) -> dict | None:
    """The newest commit touching `path` in `source`, or None if no commit does."""
    query = urllib.parse.urlencode({"path": path, "per_page": "1"})
    url = f"{API}/repos/{source}/commits?{query}"
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "upstream-drift-check")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise UpstreamLookupFailed(f"{source}/{path}: HTTP {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpstreamLookupFailed(f"{source}/{path}: {exc}") from exc
    if not isinstance(payload, list):
        raise UpstreamLookupFailed(f"{source}/{path}: unexpected response shape")
    if not payload:
        return None
    head = payload[0]
    return {
        "sha": head.get("sha", ""),
        "date": ((head.get("commit") or {}).get("committer") or {}).get("date", ""),
    }


def fixture_lookup(responses: dict):
    """Answer from a recorded JSON file instead of the network."""

    def lookup(source: str, path: str, token: str | None) -> dict | None:
        key = f"{source}|{path}"
        if key not in responses:
            raise UpstreamLookupFailed(f"{key}: no recorded response")
        answer = responses[key]
        if "error" in answer:
            raise UpstreamLookupFailed(f"{key}: {answer['error']}")
        return answer or None

    return lookup


def classify(row: dict, lookup, token: str | None) -> dict:
    """One verdict for one manifest row."""
    pin = str(row["pin"])
    kind, _, value = pin.partition(":")
    if kind == "sha256":
        return {
            **row,
            "verdict": "unresolvable",
            "reason": "pin is an installer content hash, which cannot be recomputed here",
        }
    if kind != "commit" or not value:
        raise ValueError(f"dependency {row['name']!r} has an unrecognised pin {pin!r}")
    head = lookup(row["source"], row["path"], token)
    if head is None:
        return {
            **row,
            "verdict": "missing",
            "reason": "no commit upstream touches this path - renamed, deleted or moved",
        }
    if head["sha"].startswith(value):
        return {**row, "verdict": "current", "head": head}
    return {**row, "verdict": "drifted", "head": head}


def pin_label(pin: str) -> str:
    """The pin, short enough for a table cell: its scheme plus the first 12 of its value."""
    kind, _, value = pin.partition(":")
    return f"{kind}:{value[:12]}"


def compare_url(row: dict) -> str:
    pinned = row["pin"].partition(":")[2]
    return f"https://github.com/{row['source']}/compare/{pinned}...{row['head']['sha']}"


def report(rows: list[dict], now: str) -> str:
    """The Markdown body of the drift issue. Empty string when nothing needs a human."""
    drifted = [r for r in rows if r["verdict"] == "drifted"]
    gone = [r for r in rows if r["verdict"] == "missing"]
    unchecked = [r for r in rows if r["verdict"] == "unresolvable"]
    if not drifted and not gone and not unchecked:
        return ""

    out = [
        MARKER,
        "",
        "One or more entries of `.claude/profile.yml`'s `dependencies` no longer match the "
        "upstream state they are pinned to. This issue is opened once and updated in place - "
        "never a new issue per run.",
        "",
        "**Nothing here is a patch to apply.** These copies are adaptations, not mirrors: "
        "several deliberately drop or invert upstream behaviour. Read the compare link, decide "
        "whether the change applies, and bump the pin in the PR that records the decision - "
        "whichever way it went. That is what closes this and stops it reappearing.",
        "",
        "Notes belong in a comment, not in this body: everything between the two markers is "
        "rewritten whenever the rows change, and anything written inside them is lost.",
        "",
    ]
    if drifted:
        out += [
            "## Upstream moved",
            "",
            "| Dependency | Source | Path | Pinned | Upstream HEAD | Dated | Compare |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in drifted:
            out.append(
                f"| `{row['name']}` | `{row['source']}` | `{row['path']}` | "
                f"`{row['pin'].partition(':')[2][:12]}` | `{row['head']['sha'][:12]}` | "
                f"{row['head']['date'][:10]} | [compare]({compare_url(row)}) |"
            )
        out.append("")
    # Its own section, never folded into the one below: a path that no upstream commit touches
    # any more is the loudest kind of drift, and burying it under a heading that also holds the
    # permanently-unresolvable rows is how it would get skimmed past.
    if gone:
        out += [
            "## Gone from upstream",
            "",
            "No commit in the source repository touches these paths any more - renamed, "
            "deleted, or the repository itself moved. Find where the skill went, or record "
            "that it is no longer maintained, and repin or remove the row.",
            "",
            "| Dependency | Source | Path | Pinned |",
            "|---|---|---|---|",
        ]
        for row in gone:
            out.append(
                f"| `{row['name']}` | `{row['source']}` | `{row['path']}` | "
                f"`{pin_label(row['pin'])}` |"
            )
        out.append("")
    if unchecked:
        out += [
            "## Cannot be checked",
            "",
            "| Dependency | Source | Path | Pin | Why |",
            "|---|---|---|---|---|",
        ]
        for row in unchecked:
            out.append(
                f"| `{row['name']}` | `{row['source']}` | `{row['path']}` | "
                f"`{pin_label(row['pin'])}` | {row['reason']} |"
            )
        out += [
            "",
            "A `sha256:` row is reconciled by reading the upstream file, deciding what the "
            "local copy should be, and replacing the pin with the `commit:` sha that decision "
            "was made against. Until then it is reported every run.",
            "",
        ]
    out += [
        "---",
        "",
        f"Generated by `.github/workflows/upstream-drift.yml`, {now}.",
        "",
        MARKER_END,
    ]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--root", default=os.path.dirname(here))
    parser.add_argument("--out")
    parser.add_argument("--responses")
    parser.add_argument("--markers", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)

    if args.markers:
        print(MARKER)
        print(MARKER_END)
        return 0

    profile_path = os.path.join(args.root, ".claude", "profile.yml")
    try:
        with open(profile_path, encoding="utf-8") as handle:
            profile = yaml.safe_load(handle)
    except OSError as exc:
        print(f"check-upstream-drift: cannot read {profile_path}: {exc}", file=sys.stderr)
        return 2
    except yaml.YAMLError as exc:
        print(f"check-upstream-drift: {profile_path} is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(profile, dict):
        print(f"check-upstream-drift: {profile_path} is not a mapping", file=sys.stderr)
        return 2

    # Parse-only: every row readable, every pin a scheme this script understands. It touches no
    # network, so the PR that edits the manifest can run it as an ordinary check -- which is the
    # point. Without it a malformed row ships green and surfaces only as a red scheduled run,
    # and because one bad row aborts the whole comparison below, that row would take every
    # other row's verdict down with it.
    if args.validate:
        try:
            rows = manifest_rows(profile)
            for row in rows:
                scheme = str(row["pin"]).partition(":")[0]
                if scheme not in ("commit", "sha256"):
                    raise ValueError(
                        f"dependency {row['name']!r} has an unrecognised pin {row['pin']!r}"
                    )
        except ValueError as exc:
            print(f"check-upstream-drift: {exc}", file=sys.stderr)
            return 2
        print(f"check-upstream-drift: manifest valid ({len(rows)} dependencies)", file=sys.stderr)
        return 0

    lookup = latest_commit
    if args.responses:
        try:
            with open(args.responses, encoding="utf-8") as handle:
                lookup = fixture_lookup(json.load(handle))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"check-upstream-drift: cannot read {args.responses}: {exc}", file=sys.stderr)
            return 2

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        rows = [classify(row, lookup, token) for row in manifest_rows(profile)]
    except ValueError as exc:
        print(f"check-upstream-drift: {exc}", file=sys.stderr)
        return 2
    except UpstreamLookupFailed as exc:
        print(f"check-upstream-drift: upstream lookup failed: {exc}", file=sys.stderr)
        return 2

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    summary = ", ".join(f"{n} {verdict}" for verdict, n in sorted(counts.items()))
    print(f"check-upstream-drift: {len(rows)} dependencies - {summary}", file=sys.stderr)

    body = report(rows, datetime.now(UTC).strftime("%Y-%m-%d"))
    if not body:
        return 0
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    else:
        sys.stdout.write(body)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
