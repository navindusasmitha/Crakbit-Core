#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Crakbit Core preflight installer

Usage:
  ./install.sh --prepare   Fetch pinned sources, run safe preflight checks,
                           validate the base tree, and stage src/crakbit.
  ./install.sh --check     Run local verification only; no network fetch.

A full daemon build is intentionally not exposed yet. It will be enabled only
when the anchored CRAK-001..CRAK-009 consensus transformations are implemented
and covered by tests.
EOF
}

run_checks() {
  python3 "$ROOT/scripts/verify-lock.py"
  python3 "$ROOT/scripts/verify-address-prefixes.py"
  python3 "$ROOT/scripts/verify_supply.py"
  python3 "$ROOT/genesis/test_serialization.py"
  python3 "$ROOT/scripts/patch_upstream.py" --list
  echo "Crakbit preflight checks: PASS"
}

case "${1:---prepare}" in
  --prepare)
    "$ROOT/scripts/bootstrap.sh"
    run_checks
    python3 "$ROOT/scripts/patch_upstream.py" --check-tree
    python3 "$ROOT/scripts/patch_upstream.py" --stage-overlay
    echo
    echo "Pinned base source and yespower are prepared in .work/."
    echo "The Crakbit overlay is staged. Full consensus patch/build remains gated."
    ;;
  --check)
    run_checks
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
