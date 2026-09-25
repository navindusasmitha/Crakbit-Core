#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/.work/crakbit-source"
LOCK="$ROOT/SOURCE_LOCK.json"

[[ -d "$SOURCE" ]] || {
  echo "missing $SOURCE; run ./scripts/bootstrap.sh and the CRAK source patches first" >&2
  exit 1
}
[[ -f "$SOURCE/.crakbit-economics" ]] || {
  echo "CRAK-001/002 must be applied before materialization" >&2
  exit 1
}
[[ -f "$SOURCE/.crakbit-monetary" ]] || {
  echo "CRAK-003 must be applied before materialization" >&2
  exit 1
}

readarray -t CORE_LOCK < <(python3 - "$LOCK" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))['upstreams']['bitcoin_core']
print(p['tag'])
print(p['commit_sha'])
PY
)
CORE_TAG="${CORE_LOCK[0]}"
CORE_SHA="${CORE_LOCK[1]}"

# The historical base's materializer is the authoritative transformation from
# stock Bitcoin Core into its final build tree. We run it first, then CRAK-004+
# patches that disposable final tree. This keeps Crakbit's consensus migration
# separate from the inherited patch generator and makes anchor failures loud.
(
  cd "$SOURCE"
  UPSTREAM_TAG="$CORE_TAG" ./scripts/fetch-upstream.sh
)

CORE="$SOURCE/build/wam-core"
[[ -d "$CORE/.git" ]] || {
  echo "base materializer did not produce $CORE" >&2
  exit 1
}

got="$(git -C "$CORE" rev-parse HEAD)"
if [[ "$got" != "$CORE_SHA" ]]; then
  echo "Bitcoin Core pin mismatch: expected $CORE_SHA got $got" >&2
  exit 1
fi

printf '%s\n' "$CORE" > "$ROOT/.work/MATERIALIZED_CORE"
printf '%s\n' "$got" > "$ROOT/.work/BITCOIN_CORE_RESOLVED_SHA"

echo "Crakbit materialized Core tree:"
echo "  tag:    $CORE_TAG"
echo "  commit: $got"
echo "  tree:   $CORE"
