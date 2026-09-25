#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/SOURCE_LOCK.json"
WORK="$ROOT/.work"

for cmd in git python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing required command: $cmd" >&2; exit 1; }
done

readarray -t CFG < <(python3 - "$LOCK" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
b=p['upstreams']['base_source']
y=p['upstreams']['yespower']
print(b['repository'])
print(b['ref'])
print(b.get('commit_sha') or '')
print(y['repository'])
print(y['commit_sha'])
PY
)

BASE_REPO="${CFG[0]}"
BASE_REF="${CFG[1]}"
BASE_SHA="${CFG[2]}"
YES_REPO="${CFG[3]}"
YES_SHA="${CFG[4]}"

mkdir -p "$WORK"

checkout_ref() {
  local repo="$1" ref="$2" expected_sha="$3" dir="$4"
  if [[ ! -d "$dir/.git" ]]; then
    git clone --no-checkout "$repo" "$dir"
  fi
  git -C "$dir" fetch --force --tags origin "$ref"
  git -C "$dir" checkout --detach --force FETCH_HEAD
  local got
  got="$(git -C "$dir" rev-parse HEAD)"
  if [[ -n "$expected_sha" && "$got" != "$expected_sha" ]]; then
    echo "source lock mismatch for $repo: expected $expected_sha got $got" >&2
    exit 1
  fi
  printf '%s\n' "$got"
}

BASE_GOT="$(checkout_ref "$BASE_REPO" "$BASE_REF" "$BASE_SHA" "$WORK/base-upstream")"
YES_GOT="$(checkout_ref "$YES_REPO" "$YES_SHA" "$YES_SHA" "$WORK/yespower")"

for required in README.md COPYING scripts src genesis pool explorer; do
  [[ -e "$WORK/base-upstream/$required" ]] || {
    echo "unexpected base-source layout: missing $required" >&2
    exit 1
  }
done

rm -rf "$WORK/crakbit-source"
cp -a "$WORK/base-upstream" "$WORK/crakbit-source"
printf '%s\n' "$BASE_GOT" > "$WORK/BASE_RESOLVED_SHA"
printf 'Crakbit working tree prepared from pinned base source %s (%s)\n' "$BASE_REF" "$BASE_GOT" > "$WORK/crakbit-source/.crakbit-origin"

python3 "$ROOT/scripts/verify-lock.py"
python3 "$ROOT/scripts/verify-address-prefixes.py"

echo "Crakbit working tree prepared:"
echo "  base:     $BASE_GOT"
echo "  yespower: $YES_GOT"
echo "  tree:     $WORK/crakbit-source"
