#!/bin/sh
# Table-driven test for block-main-checkout-edits.sh: feeds it real PreToolUse payloads and
# asserts the deny/allow decision. Run from anywhere:
#
#   sh .claude/hooks/test-block-main-checkout-edits.sh
#
# It never looks at this repository's own state. It builds a throwaway repository on main with
# a linked worktree, a second repository on another branch, and a directory in no repository,
# all under one temp dir that GIT_CEILING_DIRECTORIES fences off, so a temp dir that happens to
# sit inside some git tree cannot change an answer. Add a case here before changing the rule.

HOOK=$(dirname "$0")/block-main-checkout-edits.sh
[ -f "$HOOK" ] || { echo "cannot find $HOOK" >&2; exit 1; }

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
GIT_CEILING_DIRECTORIES=$T
export GIT_CEILING_DIRECTORIES
fail=0

g() { git -c user.name=t -c user.email=t@example.invalid -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

MAIN=$T/main       # the main worktree, on main
LINKED=$T/linked   # a linked worktree of it, on branch task
OTHER=$T/other     # a main worktree on another branch
OUTSIDE=$T/outside # in no repository
OTHERMAIN=$T/other-main # a linked worktree of $OTHER, on main
mkdir -p "$MAIN" "$OTHER" "$OUTSIDE"
g -C "$MAIN" init -b main && echo a > "$MAIN/a.txt" && g -C "$MAIN" add a.txt &&
  g -C "$MAIN" commit -m init && g -C "$MAIN" worktree add -b task "$LINKED" &&
  g -C "$OTHER" init -b main && echo a > "$OTHER/a.txt" && g -C "$OTHER" add a.txt &&
  g -C "$OTHER" commit -m init && g -C "$OTHER" checkout -b feature &&
  g -C "$OTHER" worktree add "$OTHERMAIN" main ||
  { echo "could not build the throwaway repositories under $T" >&2; exit 1; }

run() { # run BLOCK|ALLOW|NOTE <tool> <path-key> <path> [cwd] -- NOTE: allowed, with a stderr note
  expect=$1
  tool=$2
  key=$3
  path=$4
  dir=${5:-$OUTSIDE}
  # Backslashes are JSON-escaped, as a real payload carries a Windows path.
  esc_path=$(printf '%s' "$path" | sed 's/\\/\\\\/g')
  esc_dir=$(printf '%s' "$dir" | sed 's/\\/\\\\/g')
  input="\"$key\":\"$esc_path\""
  [ "$key" = none ] && input='"old_string":"x"'
  out=$(printf '{"session_id":"t","cwd":"%s","hook_event_name":"PreToolUse","tool_name":"%s","tool_input":{%s,"content":"the payload says \\"file_path\\":\\"elsewhere\\""}}' "$esc_dir" "$tool" "$input" |
    sh "$HOOK" 2>&1)
  rc=$?
  case "$out" in *'"permissionDecision":"deny"'*) denied=1 ;; *) denied=0 ;; esac
  shown="$tool $key=$path${5:+  (cwd $5)}"
  case "$expect" in
    BLOCK) [ "$rc" = 2 ] && [ "$denied" = 1 ] ;;
    ALLOW) [ "$rc" = 0 ] && [ -z "$out" ] ;;
    NOTE) [ "$rc" = 0 ] && [ "$denied" = 0 ] && [ -n "$out" ] ;;
  esac
  if [ $? = 0 ]; then
    printf 'ok   %-5s  %s\n' "$expect" "$shown"
  else
    printf 'FAIL expected %s, got rc=%s deny=%s  %s\n%s\n' "$expect" "$rc" "$denied" "$shown" "$out"
    fail=1
  fi
}

# --- the main checkout on main: denied ---
run BLOCK Write file_path "$MAIN/a.txt"                   # an existing file
run BLOCK Edit file_path "$MAIN/new/deeper/b.txt"         # a file in directories not made yet
run BLOCK NotebookEdit notebook_path "$MAIN/n.ipynb"      # NotebookEdit's own key
run BLOCK Write file_path "a.txt" "$MAIN"                 # a relative path, taken against cwd
run BLOCK Edit file_path "sub/b.txt" "$MAIN"              # ... into a directory not made yet

# --- everywhere else: allowed ---
run ALLOW Edit file_path "$LINKED/a.txt"                  # a linked worktree
run ALLOW NotebookEdit notebook_path "$LINKED/n.ipynb"    # ... NotebookEdit there too
run ALLOW Write file_path "a.txt" "$LINKED"               # a relative path in a linked worktree
run ALLOW Write file_path "$OUTSIDE/x.txt"                # outside any git tree
run ALLOW Write file_path "$T/nowhere/at/all/x.txt"       # ... not even existing yet
run ALLOW Edit file_path "$OTHER/a.txt"                   # a main worktree on a non-main branch
run ALLOW Edit file_path "$OTHERMAIN/a.txt"               # a linked worktree that is on main
run ALLOW Edit file_path "$MAIN/.git/COMMIT_EDITMSG"      # inside the .git directory
run ALLOW Read file_path "$MAIN/a.txt"                    # a tool the guard does not cover
run NOTE NotebookEdit file_path "$MAIN/n.ipynb"           # NotebookEdit reads notebook_path only

# --- the payload the guard cannot read: open, but not silently ---
run NOTE Edit none ""                                     # no path at all

# --- Windows spellings of the same paths (need cygpath, i.e. Git Bash / MSYS) ---
if command -v cygpath >/dev/null 2>&1; then
  WMAIN=$(cygpath -w "$MAIN")  # D:\...\main
  MMAIN=$(cygpath -m "$MAIN")  # D:/.../main
  WLINKED=$(cygpath -w "$LINKED")
  MLINKED=$(cygpath -m "$LINKED")
  run BLOCK Edit file_path "$WMAIN\\a.txt"                # D:\ backslashes
  run BLOCK Edit file_path "$MMAIN/a.txt"                 # D:/ forward slashes
  run BLOCK NotebookEdit notebook_path "$WMAIN\\new\\n.ipynb"
  run BLOCK Write file_path "sub\\b.txt" "$WMAIN"         # a relative path against a D:\ cwd
  run ALLOW Edit file_path "$WLINKED\\a.txt"
  run ALLOW Edit file_path "$MLINKED/a.txt"
  run ALLOW Write file_path "sub/b.txt" "$MLINKED"
else
  echo "note: no cygpath on PATH, so the Windows-path cases are skipped (they run under Git Bash)"
  run ALLOW Edit file_path 'D:\no\such\drive\a.txt'       # an unconverted drive path is in no tree
fi

# --- a detached HEAD in the main worktree is not main either ---
g -C "$MAIN" checkout --detach
run ALLOW Edit file_path "$MAIN/a.txt"
g -C "$MAIN" checkout main
run BLOCK Edit file_path "$MAIN/a.txt"                    # ... and back on main, denied again

echo
[ "$fail" = 0 ] && echo "ALL CASES PASSED" || echo "SOME CASES FAILED"
exit $fail
