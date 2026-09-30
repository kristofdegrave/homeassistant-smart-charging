#!/usr/bin/env bash
# Tests for .github/gh-as-bot.sh. Never reaches GitHub: a stub `gh` on PATH logs each call with
# the GH_TOKEN it ran under and answers from canned facts, against a throwaway profile naming
# repository o/r and bot b. Run from anywhere:
#
#   bash .github/test-gh-as-bot.sh

set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
WRAP="$HERE/gh-as-bot.sh"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
fail=0

cat > "$T/profile.yml" <<'EOF'
repo: {owner: o, name: r}
identity: {bot_login: b}
board:
  number: 1
  project_id: P
  fields:
    size: {id: S, options: {M: m}}
    estimate: {id: E}
    status: {id: T, options: {Done: d}}
EOF
sed '/^identity:/d' "$T/profile.yml" > "$T/nobot.yml"

mkdir "$T/bin"
cat > "$T/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s|%s\n' "${GH_TOKEN:-}" "$*" >> "$LOG"
case "$*" in
  "auth token --user b") [ "${NO_TOKEN:-0}" = 1 ] && exit 1; echo tok-b ;;
  "api repos/o/r/pulls/7 --jq .number") echo 7 ;;
  "api repos/o/r/pulls/8 --jq .number") exit 1 ;;
  *"id=PRRT_ok"*"query(\$id"*) echo "o/r 7" ;;
  *"id=PRRT_other"*"query(\$id"*) echo "o/r 9" ;;
  *"resolveReviewThread"*) echo true ;;
  "api -X POST repos/o/r/pulls -f title="*) echo https://example.invalid/pull/1 ;;
  "api -X POST repos/o/r/pulls/7/comments/5/replies "*) echo 11 ;;
  "api -X POST repos/o/r/issues/7/comments "*) echo 22 ;;
  *) exit 3 ;;
esac
EOF
chmod +x "$T/bin/gh"
printf 'body\n' > "$T/body.md"
export PATH="$T/bin:$PATH" LOG="$T/log" PROFILE="$T/profile.yml"

# check <name> <want-exit> <want-stdout> <want-log-pattern> -- <args...>
check() {
  name=$1 want_rc=$2 want_out=$3 want_log=$4
  shift 5
  : > "$LOG"
  out=$(bash "$WRAP" "$@" 2>"$T/err")
  rc=$?
  log=$(cat "$LOG")
  if [ "$rc" = "$want_rc" ] && [ "$out" = "$want_out" ] && [[ $log =~ $want_log ]]; then
    echo "ok   $name"
  else
    printf 'FAIL %s: rc=%s out=%s\n  log: %s\n  err: %s\n' "$name" "$rc" "$out" "$log" "$(cat "$T/err")"
    fail=1
  fi
}
B="$T/body.md"
NOCALL='^$'

check "pr-create opens the pull request as the bot" 0 https://example.invalid/pull/1 \
  'tok-b\|api -X POST repos/o/r/pulls -f title=t -f head=workflow/1 -f base=main -F body=@' -- pr-create workflow/1 t "$B"
check "reply posts as the bot" 0 11 'tok-b\|api -X POST repos/o/r/pulls/7/comments/5/replies -F body=@' -- reply 7 5 "$B"
check "comment reads the pull request, then posts as the bot" 0 22 \
  'tok-b\|api repos/o/r/pulls/7 --jq .number.*tok-b\|api -X POST repos/o/r/issues/7/comments' -- comment 7 "$B"
check "resolve checks the thread's pull request, then resolves as the bot" 0 true \
  'tok-b\|.*PRRT_ok.*tok-b\|.*resolveReviewThread' -- resolve 7 PRRT_ok

check "an issue number is not commented on" 2 '' 'pulls/8' -- comment 8 "$B"
check "... and nothing is posted" 2 '' '^[^P]*pulls/8[^P]*$' -- comment 8 "$B"
check "another pull request's thread is not resolved" 2 '' 'PRRT_other' -- resolve 7 PRRT_other

check "an unknown subcommand refuses before a token is read" 2 '' "$NOCALL" -- merge 7
check "a review is not the bot's" 2 '' "$NOCALL" -- review 7 "$B"
check "no subcommand" 2 '' "$NOCALL" --
check "a pull request that is not a number" 2 '' "$NOCALL" -- comment 7x "$B"
check "a zero pull request" 2 '' "$NOCALL" -- reply 0 5 "$B"
check "a comment id that is not a number" 2 '' "$NOCALL" -- reply 7 5a "$B"
check "a head that reads as a flag" 2 '' "$NOCALL" -- pr-create --force t "$B"
check "a head with a space" 2 '' "$NOCALL" -- pr-create "a b" t "$B"
check "an empty title" 2 '' "$NOCALL" -- pr-create workflow/1 "" "$B"
check "a missing body file" 2 '' "$NOCALL" -- comment 7 "$T/missing.md"
check "a body from stdin" 2 '' "$NOCALL" -- comment 7 -
check "a thread id that is not a node id" 2 '' "$NOCALL" -- resolve 7 'x"){}'
check "too many arguments" 2 '' "$NOCALL" -- comment 7 "$B" extra

NO_TOKEN=1 check "no stored login for the bot refuses" 2 '' 'auth token --user b$' -- comment 7 "$B"
PROFILE="$T/nobot.yml" check "a profile naming no bot refuses" 2 '' "$NOCALL" -- comment 7 "$B"

echo
[ "$fail" = 0 ] && echo "ALL CASES PASSED" || echo "SOME CASES FAILED"
exit $fail
