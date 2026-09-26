#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YESPOWER="$ROOT/.work/yespower"
OUT="${1:-$ROOT/.work/crakbit-build/bin/crakminer-scan}"
CC_BIN="${CC:-cc}"
CXX_BIN="${CXX:-c++}"

if [[ ! -f "$YESPOWER/yespower-opt.c" || ! -f "$YESPOWER/sha256.c" || ! -f "$YESPOWER/yespower.h" ]]; then
  echo "missing pinned yespower checkout; run scripts/bootstrap.sh first" >&2
  exit 1
fi

for cmd in "$CC_BIN" "$CXX_BIN"; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing compiler: $cmd" >&2; exit 1; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

COMMON_CFLAGS=(-O3 -fomit-frame-pointer -I"$YESPOWER")
"$CC_BIN" "${COMMON_CFLAGS[@]}" -std=c99 -c "$YESPOWER/yespower-opt.c" -o "$TMP/yespower-opt.o"
"$CC_BIN" "${COMMON_CFLAGS[@]}" -std=c99 -c "$YESPOWER/sha256.c" -o "$TMP/sha256.o"

mkdir -p "$(dirname "$OUT")"
"$CXX_BIN" -O3 -std=c++20 -pthread -I"$YESPOWER" \
  "$ROOT/src/miner/crakminer_scan.cpp" \
  "$TMP/yespower-opt.o" "$TMP/sha256.o" \
  -o "$OUT"

"$OUT" --help >/dev/null
printf '%s\n' "$OUT"
