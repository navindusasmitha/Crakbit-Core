#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
OUT_DIR="${2:-$ROOT/dist}"
VERSION="${CRAKBIT_VERSION:-0.1.0-testnet}"
umask 022

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "package-linux.sh currently supports Linux only" >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64|amd64) ARCH="x86_64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "unsupported Linux architecture: $(uname -m)" >&2; exit 1 ;;
esac

for cmd in git python3 tar gzip sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing required command: $cmd" >&2; exit 1; }
done

SOURCE_COMMIT="${CRAKBIT_SOURCE_COMMIT:-}"
if [[ -z "$SOURCE_COMMIT" ]]; then
  SOURCE_COMMIT="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
fi
if [[ ! "$SOURCE_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "unable to determine a 40-hex source commit; set CRAKBIT_SOURCE_COMMIT" >&2
  exit 1
fi
SOURCE_COMMIT="${SOURCE_COMMIT,,}"

RELEASE_EPOCH="${SOURCE_DATE_EPOCH:-}"
if [[ -z "$RELEASE_EPOCH" ]]; then
  RELEASE_EPOCH="$(git -C "$ROOT" show -s --format=%ct "$SOURCE_COMMIT" 2>/dev/null || true)"
fi
if [[ ! "$RELEASE_EPOCH" =~ ^[0-9]+$ ]]; then
  echo "unable to determine SOURCE_DATE_EPOCH; set SOURCE_DATE_EPOCH explicitly" >&2
  exit 1
fi

for bin in crakbitd crakbit-cli; do
  [[ -x "$BUILD_DIR/bin/$bin" ]] || { echo "missing executable: $BUILD_DIR/bin/$bin" >&2; exit 1; }
done

for helper in crakbit-start crakbit-mine crakminer crakminer-native.py crakpool.py crakpool-accounting.py crakpool-stats.py crakpool-payout.py crakpool-paytx.py crakpool-payguard.py crakpool-payops.py crakminer-stratum.py build-native-miner.sh install-package.sh; do
  [[ -f "$ROOT/scripts/$helper" ]] || { echo "missing helper: scripts/$helper" >&2; exit 1; }
done

for doc in README.md docs/BUILD.md docs/CONSENSUS.md docs/POOL.md docs/CRAK-018.md docs/CRAK-019.md docs/CRAK-020.md docs/CRAK-021.md docs/CRAK-022.md docs/CRAK-023.md docs/PROJECT_STATE.md; do
  [[ -f "$ROOT/$doc" ]] || { echo "missing package documentation: $doc" >&2; exit 1; }
done

if [[ ! -d "$ROOT/.work/crakbit/src/crypto/yespower" ]]; then
  echo "materialized yespower source not found; run scripts/bootstrap.sh and scripts/materialize-locked.sh first" >&2
  exit 1
fi

bash "$ROOT/scripts/build-native-miner.sh" "$BUILD_DIR/bin/crakminer-scan" >/dev/null

PKG="crakbit-core-${VERSION}-linux-${ARCH}"
STAGE_PARENT="$OUT_DIR/.stage-$PKG"
STAGE="$STAGE_PARENT/$PKG"
ARCHIVE="$OUT_DIR/$PKG.tar.gz"

rm -rf "$STAGE_PARENT"
mkdir -p "$STAGE/bin" "$STAGE/share/doc/crakbit-core" "$STAGE/share/licenses/crakbit-core" "$STAGE/share/licenses/bitcoin-core" "$STAGE/share/licenses/yespower"

install -m 0755 "$BUILD_DIR/bin/crakbitd" "$STAGE/bin/crakbitd"
install -m 0755 "$BUILD_DIR/bin/crakbit-cli" "$STAGE/bin/crakbit-cli"
install -m 0755 "$BUILD_DIR/bin/crakminer-scan" "$STAGE/bin/crakminer-scan"
install -m 0755 "$ROOT/scripts/crakbit-start" "$STAGE/bin/crakbit-start"
install -m 0755 "$ROOT/scripts/crakbit-mine" "$STAGE/bin/crakbit-mine"
install -m 0755 "$ROOT/scripts/crakminer" "$STAGE/bin/crakminer"
install -m 0755 "$ROOT/scripts/crakminer-native.py" "$STAGE/bin/crakminer-native"
install -m 0644 "$ROOT/scripts/crakpool.py" "$STAGE/bin/crakpool-base.py"
install -m 0755 "$ROOT/scripts/crakpool-accounting.py" "$STAGE/bin/crakpool"
install -m 0755 "$ROOT/scripts/crakpool-stats.py" "$STAGE/bin/crakpool-stats"
install -m 0755 "$ROOT/scripts/crakpool-payout.py" "$STAGE/bin/crakpool-payout"
install -m 0755 "$ROOT/scripts/crakpool-paytx.py" "$STAGE/bin/crakpool-paytx"
install -m 0755 "$ROOT/scripts/crakpool-payguard.py" "$STAGE/bin/crakpool-payguard"
install -m 0755 "$ROOT/scripts/crakpool-payops.py" "$STAGE/bin/crakpool-payops"
install -m 0755 "$ROOT/scripts/crakminer-stratum.py" "$STAGE/bin/crakminer-stratum"
install -m 0755 "$ROOT/scripts/install-package.sh" "$STAGE/install.sh"

cp "$ROOT/README.md" "$STAGE/share/doc/crakbit-core/README.md"
cp "$ROOT/docs/BUILD.md" "$STAGE/share/doc/crakbit-core/BUILD.md"
cp "$ROOT/docs/CONSENSUS.md" "$STAGE/share/doc/crakbit-core/CONSENSUS.md"
cp "$ROOT/docs/POOL.md" "$STAGE/share/doc/crakbit-core/POOL.md"
cp "$ROOT/docs/CRAK-018.md" "$STAGE/share/doc/crakbit-core/CRAK-018.md"
cp "$ROOT/docs/CRAK-019.md" "$STAGE/share/doc/crakbit-core/CRAK-019.md"
cp "$ROOT/docs/CRAK-020.md" "$STAGE/share/doc/crakbit-core/CRAK-020.md"
cp "$ROOT/docs/CRAK-021.md" "$STAGE/share/doc/crakbit-core/CRAK-021.md"
cp "$ROOT/docs/CRAK-022.md" "$STAGE/share/doc/crakbit-core/CRAK-022.md"
cp "$ROOT/docs/CRAK-023.md" "$STAGE/share/doc/crakbit-core/CRAK-023.md"
cp "$ROOT/docs/PROJECT_STATE.md" "$STAGE/share/doc/crakbit-core/PROJECT_STATE.md"
cp "$ROOT/LICENSE" "$STAGE/share/licenses/crakbit-core/LICENSE"
[[ -f "$ROOT/.work/crakbit/COPYING" ]] && cp "$ROOT/.work/crakbit/COPYING" "$STAGE/share/licenses/bitcoin-core/COPYING"

for file in yespower-opt.c yespower-platform.c yespower.h sha256.c sha256.h sysendian.h insecure_memzero.h README; do
  cp "$ROOT/.work/crakbit/src/crypto/yespower/$file" "$STAGE/share/licenses/yespower/$file"
done

python3 - "$ROOT/SOURCE_LOCK.json" "$STAGE/share/doc/crakbit-core/BUILD-MANIFEST.json" "$VERSION" "$ARCH" "$SOURCE_COMMIT" "$RELEASE_EPOCH" <<'PY'
import json
import sys
from pathlib import Path

lock_path, out_path, version, arch, source_commit, epoch = sys.argv[1:]
lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
manifest = {
    "schema": 1,
    "project": "Crakbit Core",
    "package_version": version,
    "platform": "linux",
    "arch": arch,
    "source_commit": source_commit,
    "source_date_epoch": int(epoch),
    "mainnet_enabled": bool(lock.get("mainnet_enabled", False)),
    "upstreams": {
        "bitcoin_core_commit": lock["upstreams"]["bitcoin_core"]["commit_sha"],
        "yespower_commit": lock["upstreams"]["yespower"]["commit_sha"],
    },
    "pow": lock["pow"],
    "archive_reproducibility": {
        "sorted_entries": True,
        "normalized_mtime": True,
        "uid": 0,
        "gid": 0,
        "gzip_timestamp": False,
    },
}
Path(out_path).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY

# Normalize permissions that could otherwise vary with the caller's umask or
# source checkout. Executable modes under bin/ were installed explicitly above.
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE/share" -type f -exec chmod 0644 {} +

(
  cd "$STAGE"
  LC_ALL=C find bin share -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS
)
chmod 0644 "$STAGE/SHA256SUMS"

mkdir -p "$OUT_DIR"
rm -f "$ARCHIVE" "$ARCHIVE.sha256"

# CRAK-022 deterministic archive contract:
# - lexical entry order
# - one source-derived mtime for every archive entry
# - numeric root ownership independent of the builder account
# - gzip header without original name/timestamp
LC_ALL=C tar \
  --sort=name \
  --format=gnu \
  --mtime="@$RELEASE_EPOCH" \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  -C "$STAGE_PARENT" \
  -cf - "$PKG" | gzip -n -9 > "$ARCHIVE"

(
  cd "$OUT_DIR"
  sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256"
)
rm -rf "$STAGE_PARENT"
printf '%s\n' "$ARCHIVE"
printf '%s\n' "$ARCHIVE.sha256"
