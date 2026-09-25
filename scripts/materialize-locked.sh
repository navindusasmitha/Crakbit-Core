#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 scripts/materialize.py
python3 scripts/finalize-genesis.py
python3 scripts/apply-asert.py
python3 scripts/apply-monetary.py

printf '%s\n' 'Crakbit materialized source is consensus-locked through CRAK-008 monetary rules.'
