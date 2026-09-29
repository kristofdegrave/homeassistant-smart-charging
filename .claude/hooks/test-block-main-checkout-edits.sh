#!/bin/sh
# Table-driven test for block-main-checkout-edits.sh: feeds it real PreToolUse payloads and
# asserts the deny/allow decision. Run from anywhere:
#
#   sh .claude/hooks/test-block-main-checkout-edits.sh
#
# It never looks at this repository's own state. It builds a throwaway repository on main with
# a linked worktree, a second repository on another branch, a --separate-git-dir checkout and a
# directory in no repository, all under one temp dir that GIT_CEILING_DIRECTORIES fences off,
# so a temp dir that happens to sit inside some git tree cannot change an answer. Add a case
# here before changing the rule.

HOOK=$(dirname "$0")/block-main-checkout-edits.sh
[ -f "$HOOK" ] || { echo "cannot find $HOOK" >&2; exit 1; }

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
GIT_CEILING_DIRECTORIES=$T
export GIT_CEILING_DIRECTORIES
fail=0

g() { git -c user.name=t -c user.email=t@example.invalid -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

# Mixed-case names, so the letter-case cases below have a case to change.
MAIN=$T/Main            # the main worktree, on main
LINKED=$T/Linked        # a linked worktree of it, on branch task
OTHER=$T/other          # a main worktree on another branch
OTHERMAIN=$T/other-main # a linked worktree of $OTHER, on main
SEP=$T/Sep              # a --separate-git-dir checkout on main: its .git is a file
SEP2=$T/Sep2            # ... whose git dir sits under a directory named worktrees
OUTSIDE=$T/outside      # in no repository
mkdir -p "$MAIN" "$OTHER" "$OUTSIDE" "$T/worktrees"
g -C "$MAIN" init -b main && echo a > "$MAIN/a.txt" && g -C "$MAIN" add a.txt &&
  g -C "$MAIN" commit -m init && g -C "$MAIN" worktree add -b task "$LINKED" &&
  g -C "$OTHER" init -b main && echo a > "$OTHER/a.txt" && g -C "$OTHER" add a.txt &&
  g -C "$OTHER" commit -m init && g -C "$OTHER" checkout -b feature &&
  g -C "$OTHER" worktree add "$OTHERMAIN" main &&
  g init -b main --separate-git-dir "$T/sep.git" "$SEP" &&
  g init -b main --separate-git-dir "$T/worktrees/sep2.git" "$SEP2" ||
  { echo "could not build the throwaway repositories under $T" >&2; exit 1; }
# Existing subdirectories, so the directory walk and --show-toplevel are exercised from below
# the top level, not only at it.
mkdir -p "$MAIN/Docs/Deeper" "$LINKED/Docs/Deeper"

# The hook runs under $HOOK_PATH (default: this PATH), so a case can hand it a stub git or none;
# sh itself is found once, here. DECOY_FIRST=1 puts the decoy content before the path key, so
# "the first match wins" cannot be what keeps the escaped decoy key from matching. NOCWD=1
# leaves the payload's cwd out.
SH=$(command -v sh)
DECOY='"content":"the payload says \"file_path\":\"elsewhere\""'

run() { # run BLOCK|ALLOW|NOTE <tool> <path-key> <path> [cwd] -- NOTE: allowed, with a note carrying $WANT
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
  if [ "${DECOY_FIRST:-0}" = 1 ]; then input="$DECOY,$input"; else input="$input,$DECOY"; fi
  cwd_field="\"cwd\":\"$esc_dir\","
  [ "${NOCWD:-0}" = 1 ] && cwd_field=
  out=$(printf '{"session_id":"t",%s"hook_event_name":"PreToolUse","tool_name":"%s","tool_input":{%s}}' "$cwd_field" "$tool" "$input" |
    PATH=${HOOK_PATH:-$PATH} "$SH" "$HOOK" 2>&1)
  rc=$?
  case "$out" in *'"permissionDecision":"deny"'*) denied=1 ;; *) denied=0 ;; esac
  shown="$tool $key=$path${5:+  (cwd $5)}"
  case "$expect" in
    BLOCK) [ "$rc" = 2 ] && [ "$denied" = 1 ] ;;
    ALLOW) [ "$rc" = 0 ] && [ -z "$out" ] ;;
    NOTE) [ "$rc" = 0 ] && [ "$denied" = 0 ] &&
      case "$out" in *"$WANT"*"allowing the"*"call unchecked"*) true ;; *) false ;; esac ;;
  esac
  if [ $? = 0 ]; then
    printf 'ok   %-5s  %s\n' "$expect" "$shown"
  else
    printf 'FAIL expected %s, got rc=%s deny=%s  %s\n%s\n' "$expect" "$rc" "$denied" "$shown" "$out"
    fail=1
  fi
}

# stub <script body> -- the stub git first on HOOK_PATH; @GIT@ in the body is the real git.
REAL_GIT=$(command -v git)
STUB=$T/bin-stub
mkdir -p "$STUB"
stub() {
  printf '#!/bin/sh\n%s\n' "$1" | sed "s|@GIT@|$REAL_GIT|g" > "$STUB/git"
  chmod +x "$STUB/git"
  HOOK_PATH=$STUB:$PATH
}

# --- the main checkout on main: denied ---
run BLOCK Write file_path "$MAIN/a.txt"                   # an existing file
run BLOCK Edit file_path "$MAIN/new/deeper/b.txt"         # a file in directories not made yet
run BLOCK Edit file_path "$MAIN/Docs/Deeper/c.txt"        # a file in an existing subdirectory
run BLOCK NotebookEdit notebook_path "$MAIN/n.ipynb"      # NotebookEdit's own key
run BLOCK Write file_path "a.txt" "$MAIN"                 # a relative path, taken against cwd
run BLOCK Edit file_path "sub/b.txt" "$MAIN"              # ... into a directory not made yet
run BLOCK Edit file_path "Deeper/c.txt" "$MAIN/Docs"      # ... from a subdirectory cwd
run BLOCK Edit file_path "$SEP/a.txt"                     # a --separate-git-dir checkout on main
run BLOCK Edit file_path "$SEP2/a.txt"                    # ... its git dir under .../worktrees/

# --- everywhere else: allowed ---
run ALLOW Edit file_path "$LINKED/a.txt"                  # a linked worktree
run ALLOW Edit file_path "$LINKED/Docs/Deeper/c.txt"      # ... in an existing subdirectory
run ALLOW NotebookEdit notebook_path "$LINKED/n.ipynb"    # ... NotebookEdit there too
run ALLOW Write file_path "a.txt" "$LINKED"               # a relative path in a linked worktree
run ALLOW Write file_path "$OUTSIDE/x.txt"                # outside any git tree
run ALLOW Write file_path "$T/nowhere/at/all/x.txt"       # ... not even existing yet
run ALLOW Edit file_path "$OTHER/a.txt"                   # a main worktree on a non-main branch
run ALLOW Edit file_path "$OTHERMAIN/a.txt"               # a linked worktree that is on main
run ALLOW Edit file_path "$MAIN/.git/COMMIT_EDITMSG"      # inside the .git directory
run ALLOW Read file_path "$MAIN/a.txt"                    # a tool the guard does not cover
WANT='could not read the path'
run NOTE NotebookEdit file_path "$MAIN/n.ipynb"           # NotebookEdit reads notebook_path only

# --- the decoy key first: an escaped "file_path" inside a string never matches ---
DECOY_FIRST=1
run BLOCK Edit file_path "$MAIN/a.txt"
run ALLOW Edit file_path "$LINKED/a.txt"
DECOY_FIRST=0

# --- what the guard cannot read or ask: open, but not silently ---
run NOTE Edit none ""                                     # no path at all
WANT='could not read tool_name'
run NOTE "" file_path "$MAIN/a.txt"                       # no tool name
WANT='could not read the cwd'
NOCWD=1
run NOTE Write file_path "a.txt"                          # a relative path and no cwd
NOCWD=0

# A PATH with every tool the hook runs but git, each a wrapper around the real one.
NOGIT=$T/bin-nogit
mkdir -p "$NOGIT"
for t in awk sed tr dirname cat mktemp rm cygpath; do
  real=$(command -v "$t") || continue
  printf '#!/bin/sh\nexec "%s" "$@"\n' "$real" > "$NOGIT/$t"
  chmod +x "$NOGIT/$t"
done
HOOK_PATH=$NOGIT
WANT='no git on PATH'
run NOTE Edit file_path "$MAIN/a.txt"                     # no git on PATH

# Stub gits: each answers one question the way a broken or unexpected git might, and passes
# the rest to the real one.
stub 'echo "fatal: detected dubious ownership in repository at x" >&2; exit 128'
WANT='dubious ownership'
run NOTE Edit file_path "$MAIN/a.txt"                     # git fails, not "not a repository"
stub 'case "$*" in *show-toplevel*) exit 128 ;; esac; exec @GIT@ "$@"'
WANT='git rev-parse --show-toplevel failed'
run NOTE Edit file_path "$MAIN/a.txt"                     # git names no top level
stub "case \"\$*\" in *show-toplevel*) echo \"$T/outside\" ;; *) exec @GIT@ \"\$@\" ;; esac"
WANT='has no .git'
run NOTE Edit file_path "$MAIN/a.txt"                     # ... or one with no .git
printf 'not a gitdir line\n' > "$T/outside/.git"
WANT='names no gitdir'
run NOTE Edit file_path "$MAIN/a.txt"                     # ... or one whose .git file is junk
rm -f "$T/outside/.git"
stub 'case "$*" in *symbolic-ref*) echo "fatal: bad HEAD" >&2; exit 128 ;; esac; exec @GIT@ "$@"'
WANT='git symbolic-ref failed'
run NOTE Edit file_path "$MAIN/a.txt"                     # git cannot read the branch
# An --is-inside-work-tree answer that is neither true nor false is trusted neither way: a
# main checkout on main is still refused, and an allow says why it was not sure.
stub 'case "$*" in *is-inside-work-tree*) echo ;; *) exec @GIT@ "$@" ;; esac'
run BLOCK Edit file_path "$MAIN/a.txt"                    # blank answer, main on main
WANT='answered'
run NOTE Edit file_path "$LINKED/a.txt"                   # blank answer, linked worktree
stub 'case "$*" in *is-inside-work-tree*) echo ;; *) echo "fatal: not a git repository" >&2; exit 128 ;; esac'
run NOTE Edit file_path "$MAIN/a.txt"                     # blank answer, then "not a git repository"
HOOK_PATH=

# --- Windows spellings of the same paths (need cygpath, i.e. Git Bash / MSYS) ---
if command -v cygpath >/dev/null 2>&1; then
  WMAIN=$(cygpath -w "$MAIN")  # D:\...\Main
  MMAIN=$(cygpath -m "$MAIN")  # D:/.../Main
  WLINKED=$(cygpath -w "$LINKED")
  MLINKED=$(cygpath -m "$LINKED")
  run BLOCK Edit file_path "$WMAIN\\a.txt"                # D:\ backslashes
  run BLOCK Edit file_path "$MMAIN/a.txt"                 # D:/ forward slashes
  run BLOCK NotebookEdit notebook_path "$WMAIN\\new\\n.ipynb"
  run BLOCK Write file_path "sub\\b.txt" "$WMAIN"         # a relative path against a D:\ cwd
  run ALLOW Edit file_path "$WLINKED\\a.txt"
  run ALLOW Edit file_path "$MLINKED/a.txt"
  run ALLOW Write file_path "sub/b.txt" "$MLINKED"

  # Another letter case, in a subdirectory, against the long-name spelling: Windows paths are
  # case-insensitive, and MSYS keeps the case it was given where no 8.3 component makes it
  # look the name up (mktemp's %TEMP% is often one, which the long form removes).
  LT=$(cygpath -m -l "$T")         # C:/Users/<long name>/.../tmp.X
  WLT=$(cygpath -w -l "$T")        # C:\Users\<long name>\...\tmp.X
  lc_drive=$(printf '%s' "$LT" | cut -c1 | tr 'A-Z' 'a-z')$(printf '%s' "$LT" | cut -c2-)
  run BLOCK Edit file_path "$LT/main/docs/deeper/c.txt"   # the directories in lower case
  run BLOCK Edit file_path "$LT/MAIN/Docs/c.txt"          # ... in upper case
  run BLOCK Edit file_path "$WLT\\main\\DOCS\\c.txt"      # ... with backslashes
  run BLOCK Edit file_path "$lc_drive/main/Docs/c.txt"    # ... and a lower-case drive letter
  run BLOCK Edit file_path "Deeper/c.txt" "$WLT\\main\\docs"  # ... as a relative path's cwd
  run ALLOW Edit file_path "$LT/linked/docs/deeper/c.txt" # a linked worktree, any case
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
