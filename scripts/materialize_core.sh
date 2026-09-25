#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$ROOT/.work/base-upstream"
LOCK="$ROOT/SOURCE_LOCK.json"

[[ -d "$BASE/.git" ]] || {
  echo "missing clean pinned base at $BASE; run bash scripts/bootstrap.sh first" >&2
  exit 1
}

readarray -t LOCKS < <(python3 - "$LOCK" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
b=p['upstreams']['base_source']
c=p['upstreams']['bitcoin_core']
print(b.get('commit_sha') or '')
print(c['tag'])
print(c['commit_sha'])
PY
)
BASE_SHA="${LOCKS[0]}"
CORE_TAG="${LOCKS[1]}"
CORE_SHA="${LOCKS[2]}"

# The historical WAM materializer must run from the pristine pinned WAM tree,
# never from .work/crakbit-source. CRAK-001/002/003 deliberately mutate that
# second tree for migration audits; feeding those mutations back into WAM's
# anchored patch generator causes anchor drift and can produce a half-patched
# consensus tree.
got_base="$(git -C "$BASE" rev-parse HEAD)"
if [[ -n "$BASE_SHA" && "$got_base" != "$BASE_SHA" ]]; then
  echo "base-source pin mismatch: expected $BASE_SHA got $got_base" >&2
  exit 1
fi

# Always discard the generated Core/RandomX outputs before materializing. The
# base source is immutable; build/ is disposable. This prevents a previous WAM
# patch run from being re-applied at a different migration state.
rm -rf "$BASE/build"
(
  cd "$BASE"
  UPSTREAM_TAG="$CORE_TAG" bash ./scripts/fetch-upstream.sh
)

CORE="$BASE/build/wam-core"
[[ -d "$CORE/.git" ]] || {
  echo "base materializer did not produce $CORE" >&2
  exit 1
}

got_core="$(git -C "$CORE" rev-parse HEAD)"
if [[ "$got_core" != "$CORE_SHA" ]]; then
  echo "Bitcoin Core pin mismatch: expected $CORE_SHA got $got_core" >&2
  exit 1
fi

# CRAK economics/monetary changes belong on the final materialized Core tree.
# The same strict patchers are also exercised earlier against crakbit-source as
# migration-unit tests, but only this invocation changes the node we will build.
python3 "$ROOT/scripts/apply_economics_patch.py" --tree "$CORE"
python3 "$ROOT/scripts/apply_monetary_patch.py" --tree "$CORE"

# Crakbit-owned constants live beside, not inside, inherited WAM source. Later
# CRAK-004/005 patches include this header from the final Core tree.
rm -rf "$CORE/src/crakbit"
mkdir -p "$CORE/src/crakbit"
cp -a "$ROOT/src/crakbit/." "$CORE/src/crakbit/"

printf '%s\n' "$CORE" > "$ROOT/.work/MATERIALIZED_CORE"
printf '%s\n' "$got_core" > "$ROOT/.work/BITCOIN_CORE_RESOLVED_SHA"

echo "Crakbit materialized Core tree:"
echo "  base:    $got_base"
echo "  tag:     $CORE_TAG"
echo "  commit:  $got_core"
echo "  tree:    $CORE"
echo "  CRAK-001/002/003 applied to final tree"
