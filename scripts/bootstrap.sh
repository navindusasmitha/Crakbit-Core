#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/SOURCE_LOCK.json"
WORK="$ROOT/.work"

for cmd in git python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing required command: $cmd" >&2; exit 1; }
done

readarray -t LOCKED < <(python3 - "$LOCK" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
print(p['upstreams']['bitcoin_core']['repository'])
print(p['upstreams']['bitcoin_core']['commit_sha'])
print(p['upstreams']['yespower']['repository'])
print(p['upstreams']['yespower']['commit_sha'])
PY
)

BTC_REPO="${LOCKED[0]}"
BTC_SHA="${LOCKED[1]}"
YES_REPO="${LOCKED[2]}"
YES_SHA="${LOCKED[3]}"

mkdir -p "$WORK"

checkout_exact() {
  local repo="$1" sha="$2" dir="$3"
  if [[ ! -d "$dir/.git" ]]; then
    git clone --filter=blob:none --no-checkout "$repo" "$dir"
  fi
  git -C "$dir" fetch --force --depth=1 origin "$sha"
  git -C "$dir" checkout --detach --force "$sha"
  local got
  got="$(git -C "$dir" rev-parse HEAD)"
  [[ "$got" == "$sha" ]] || { echo "source lock mismatch: expected $sha got $got" >&2; exit 1; }
}

checkout_exact "$BTC_REPO" "$BTC_SHA" "$WORK/bitcoin"
checkout_exact "$YES_REPO" "$YES_SHA" "$WORK/yespower"

python3 "$ROOT/scripts/verify-lock.py"

echo "Pinned upstreams are ready:"
echo "  Bitcoin Core: $BTC_SHA"
echo "  yespower:     $YES_SHA"
echo "Next stage: apply the reviewed Crakbit consensus patch series."
