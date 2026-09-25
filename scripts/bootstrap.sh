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
w=p['upstreams']['wam_coin']
y=p['upstreams']['yespower']
print(w['repository'])
print(w['ref'])
print(w.get('commit_sha') or '')
print(y['repository'])
print(y['commit_sha'])
PY
)

WAM_REPO="${CFG[0]}"
WAM_REF="${CFG[1]}"
WAM_SHA="${CFG[2]}"
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

WAM_GOT="$(checkout_ref "$WAM_REPO" "$WAM_REF" "$WAM_SHA" "$WORK/wam-upstream")"
YES_GOT="$(checkout_ref "$YES_REPO" "$YES_SHA" "$YES_SHA" "$WORK/yespower")"

for required in README.md COPYING scripts/patch_upstream.py src/wam; do
  [[ -e "$WORK/wam-upstream/$required" ]] || {
    echo "unexpected WAM source layout: missing $required" >&2
    exit 1
  }
done

rm -rf "$WORK/crakbit-source"
cp -a "$WORK/wam-upstream" "$WORK/crakbit-source"
printf '%s\n' "$WAM_GOT" > "$WORK/WAM_RESOLVED_SHA"
printf 'Crakbit derived working tree prepared from WAM %s (%s)\n' "$WAM_REF" "$WAM_GOT" > "$WORK/crakbit-source/.crakbit-derived"

python3 "$ROOT/scripts/verify-lock.py"
python3 "$ROOT/scripts/verify-address-prefixes.py"

echo "WAM-derived Crakbit working tree prepared:"
echo "  WAM:      $WAM_GOT"
echo "  yespower: $YES_GOT"
echo "  tree:     $WORK/crakbit-source"
if [[ -z "$WAM_SHA" ]]; then
  echo "IMPORTANT: SOURCE_LOCK.json still needs wam_coin.commit_sha=$WAM_GOT before a release/testnet build is considered reproducible."
fi
