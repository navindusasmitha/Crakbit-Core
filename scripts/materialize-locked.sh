#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 scripts/materialize.py
python3 scripts/finalize-genesis.py

printf '%s\n' 'Crakbit materialized source is consensus-locked for CRAK-006.'
