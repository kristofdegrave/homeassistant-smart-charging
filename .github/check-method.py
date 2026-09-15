#!/usr/bin/env python3
"""The method check: does the method package still hold together as one structure?

Five repo-wide checks, each a structural agreement between files that are edited separately
and drift silently when one moves without the other. Every check is stated as a rule the
script re-derives from the files on each run -- nothing here is a hand-maintained list.

  1  anchors, outward   every `CLAUDE.md`'s **Topic** pointer under .claude/**,
                        docs/reference/** and .github/workflows/** resolves, by prefix, to a
                        `##` heading of CLAUDE.md or to a **Topic** row of its routing table
  2  anchors, inward    every link in CLAUDE.md resolves to an existing file and, where it
                        carries a #fragment, to a heading of that file; every repo path
                        CLAUDE.md names in backticks exists; no `###` heading in CLAUDE.md or
                        docs/reference/** appears before its `##`
  3  profile agreement  CLAUDE.md's Model selection table has exactly one row per
                        work_types.enabled in .claude/profile.yml; labels.context names the
                        same set; the table's changed-path map equals review.path_map
  4  work-type          every enabled work type has review.md, and implement.md and done.md
     completeness       unless its row says its work is `none`; every declared dependency
                        installed in the repo is present; every skill present is either a
                        declared dependency or carries `layer:`; every agent and every
                        docs/reference/** document carries `layer:`
  5  no profile values  no value from profile.yml (owner, repository name, board name, node
     in method files    ids, status column names) appears in a `layer: method` file

Why the scope of check 1 is wider than the rule that created it: a CI worker prompt is not
bound by the routing rule, but three of them do point at a CLAUDE.md section, so a heading
rename would break the pipeline exactly as it would break a skill.

The one literal exception, so it is a stated limit rather than a surprise: the pointer form is
documented as `` `CLAUDE.md`'s **Topic** `` in the authoring reference and the workflow
checklist, and that placeholder is skipped by name in check 1.

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
POINTER_PLACEHOLDER = "Topic"
POINTER_TREES = (".claude", "docs/reference", ".github/workflows")
POINTER_RE = re.compile(r"`?CLAUDE\.md`?['’]s\s+\*\*([^*]+?)\*\*", re.S)
LINK_RE = re.compile(r"\[[^\]]*\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
BACKTICK_PATH_RE = re.compile(r"`((?:\.?[A-Za-z0-9_-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+)`")
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
    """Cells of every table body row (header and separator rows dropped)."""
    rows = []
    for line in text.splitlines():
        m = TABLE_ROW_RE.match(line)
        if not m:
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
    """What the check reads out of CLAUDE.md: headings, routing topics, the table, the map."""

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

    def path_map(self) -> set[tuple[str, str]]:
        """(path, work type) pairs from the 'routes by changed path' paragraph."""
        marker = "**The no-label row routes by changed path**"
        start = self.selection.find(marker)
        if start < 0:
            return set()
        paragraph = self.selection[start + len(marker) :]
        end = paragraph.find("\n\n")
        paragraph = paragraph if end < 0 else paragraph[:end]
        pairs: set[tuple[str, str]] = set()
        cursor = 0
        for m in re.finditer(r"→\s*`docs/reference/work-types/([^/`]+)/review\.md`", paragraph):
            for path in re.findall(r"`([^`]+)`", paragraph[cursor : m.start()]):
                pairs.add((path, m.group(1)))
            cursor = m.end()
        return pairs


# --- the five checks -------------------------------------------------------------------------


def check_outward(root: Path, guide: Guide, findings: Findings) -> None:
    for tree in POINTER_TREES:
        for path in walk(root, tree, (".md", ".yml", ".yaml")):
            text = read_text(path)
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


def check_inward(root: Path, guide: Guide, findings: Findings) -> None:
    text = guide.text
    for topic, owner in guide.topics:
        if not LINK_RE.search(owner):
            findings.add(2, "CLAUDE.md", f"routing-table entry **{topic}** links to no document")
    seen: set[str] = set()
    for _, line in strip_fences(text):
        for m in LINK_RE.finditer(line):
            target = m.group(1)
            if re.match(r"[a-z]+:", target) or target in seen:
                continue
            seen.add(target)
            file_part, _, fragment = target.partition("#")
            if not file_part:
                continue
            path = root / file_part
            if not path.is_file():
                findings.add(2, "CLAUDE.md", f"link target {file_part} does not exist")
                continue
            if fragment and fragment not in {slug(h) for _, _, h in headings(read_text(path))}:
                findings.add(
                    2, "CLAUDE.md", f"link {target}: no heading in {file_part} has that anchor"
                )
    for _, line in strip_fences(text):
        for m in BACKTICK_PATH_RE.finditer(line):
            path = m.group(1)
            if "*" in path or path in seen:
                continue
            seen.add(path)
            if not (root / path).exists():
                findings.add(2, "CLAUDE.md", f"names {path}, which does not exist")
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


def check_profile_agreement(guide: Guide, profile: dict, findings: Findings) -> None:
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
    in_guide = guide.path_map()
    in_profile: set[tuple[str, str]] = set()
    for entry in (profile.get("review") or {}).get("path_map") or []:
        for path in entry.get("paths") or []:
            in_profile.add((path, entry.get("work_type")))
    if not in_guide:
        findings.add(3, "CLAUDE.md", "no changed-path map found under Model selection")
    for path, work_type in sorted(in_guide - in_profile):
        findings.add(
            3,
            "CLAUDE.md",
            f"path map has `{path}` -> {work_type}; profile.yml review.path_map does not",
        )
    for path, work_type in sorted(in_profile - in_guide):
        findings.add(
            3,
            ".claude/profile.yml",
            f"review.path_map has `{path}` -> {work_type}; CLAUDE.md's path map does not",
        )
    for _, work_type in sorted(in_profile):
        if work_type not in enabled:
            findings.add(
                3,
                ".claude/profile.yml",
                f"review.path_map routes to `{work_type}`, which is not enabled",
            )


def declared_dependencies(profile: dict) -> dict[str, dict]:
    deps = profile.get("dependencies") or {}
    out: dict[str, dict] = {}
    for group in deps.values() if isinstance(deps, dict) else []:
        for entry in group or []:
            if isinstance(entry, dict) and entry.get("name"):
                out[str(entry["name"])] = entry
    return out


def layer_of(path: Path) -> str | None:
    """The `layer:` value, '' when the frontmatter has none, None when there is no frontmatter."""
    data = frontmatter(read_text(path))
    if data is None:
        return None
    value = data.get("layer")
    return str(value) if value is not None else ""


def require_layer(root: Path, path: Path, findings: Findings, layers: dict[str, str]) -> None:
    layer = layer_of(path)
    where = rel(root, path)
    if not layer:
        findings.add(4, where, "carries no `layer:` frontmatter (method, project or stack)")
    elif layer not in LAYERS:
        findings.add(4, where, f"`layer: {layer}` is not one of {sorted(LAYERS)}")
    else:
        layers[where] = layer


def check_completeness(
    root: Path, guide: Guide, profile: dict, findings: Findings
) -> dict[str, str]:
    """Returns {path: layer} for every file that carries a valid layer -- check 5's input."""
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
                require_layer(root, skill, findings, layers)
    for path in walk(root, ".claude/agents", (".md",)):
        require_layer(root, path, findings, layers)
    for path in walk(root, "docs/reference", (".md",)):
        require_layer(root, path, findings, layers)
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


def check_profile_values(
    root: Path, profile: dict, layers: dict[str, str], findings: Findings
) -> None:
    values = profile_values(profile)
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
    check_profile_agreement(guide, profile, findings)
    layers = check_completeness(root, guide, profile, findings)
    check_profile_values(root, profile, layers, findings)

    names = {
        1: "anchors, outward",
        2: "anchors, inward",
        3: "profile agreement",
        4: "work-type completeness",
        5: "no profile values in method files",
    }
    if not findings.items:
        print(
            f"check-method: clean ({len(layers)} layered files, {len(guide.rows)} work-type rows)"
        )
        return 0
    prefix = "warning" if args.warn else "error"
    for check, where, message in sorted(findings.items):
        print(f"{prefix}: [{check} {names[check]}] {where}: {message}")
    print(f"check-method: {len(findings.items)} finding(s)")
    return 0 if args.warn else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
