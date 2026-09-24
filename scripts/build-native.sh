#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="${CRAKBIT_JOBS:-$(nproc 2>/dev/null || echo 2)}"

cmake -S "$ROOT" -B "$ROOT/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/build" --parallel "$JOBS"

"$ROOT/build/crakbitd" --datadir "$ROOT/build/native-smoke" init
"$ROOT/build/crakbitd" --datadir "$ROOT/build/native-smoke" status

echo "Crakbit native build OK: $ROOT/build/crakbitd"
