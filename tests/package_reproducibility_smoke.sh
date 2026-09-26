#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${1:-$ROOT/.work/crakbit-build}"
TMP="$(mktemp -d)"
OUT_A="$TMP/a"
OUT_B="$TMP/b"
EXTRACT="$TMP/extract"
VERSION="ci-repro"
SOURCE_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
EPOCH="1700000000"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

mkdir -p "$OUT_A" "$OUT_B" "$EXTRACT"

for out in "$OUT_A" "$OUT_B"; do
  CRAKBIT_VERSION="$VERSION" \
  CRAKBIT_SOURCE_COMMIT="$SOURCE_COMMIT" \
  SOURCE_DATE_EPOCH="$EPOCH" \
    bash "$ROOT/scripts/package-linux.sh" "$BUILD_DIR" "$out" >/dev/null
done

ARCHIVE_A="$(find "$OUT_A" -maxdepth 1 -type f -name 'crakbit-core-ci-repro-linux-*.tar.gz' -print -quit)"
ARCHIVE_B="$(find "$OUT_B" -maxdepth 1 -type f -name 'crakbit-core-ci-repro-linux-*.tar.gz' -print -quit)"

[[ -n "$ARCHIVE_A" && -n "$ARCHIVE_B" ]] || {
  echo "CRAK-022: reproducibility archives were not produced" >&2
  exit 1
}

if ! cmp -s "$ARCHIVE_A" "$ARCHIVE_B"; then
  echo "CRAK-022: identical inputs produced different package bytes" >&2
  sha256sum "$ARCHIVE_A" "$ARCHIVE_B" >&2
  exit 1
fi

if ! cmp -s "$ARCHIVE_A.sha256" "$ARCHIVE_B.sha256"; then
  echo "CRAK-022: identical inputs produced different SHA256 sidecars" >&2
  cat "$ARCHIVE_A.sha256" "$ARCHIVE_B.sha256" >&2
  exit 1
fi

(
  cd "$OUT_A"
  sha256sum -c "$(basename "$ARCHIVE_A").sha256"
)

tar -C "$EXTRACT" -xzf "$ARCHIVE_A"
PKGDIR="$(find "$EXTRACT" -mindepth 1 -maxdepth 1 -type d -name 'crakbit-core-ci-repro-linux-*' -print -quit)"
[[ -n "$PKGDIR" ]] || { echo "CRAK-022: extracted package directory not found" >&2; exit 1; }

(
  cd "$PKGDIR"
  sha256sum -c SHA256SUMS
)

python3 - "$ARCHIVE_A" "$PKGDIR/share/doc/crakbit-core/BUILD-MANIFEST.json" "$ROOT/SOURCE_LOCK.json" "$SOURCE_COMMIT" "$EPOCH" "$VERSION" <<'PY'
import gzip
import json
import sys
import tarfile
from pathlib import Path

archive_path, manifest_path, lock_path, source_commit, epoch_s, version = sys.argv[1:]
epoch = int(epoch_s)
raw = Path(archive_path).read_bytes()
assert raw[:2] == b"\x1f\x8b", "not a gzip stream"
assert int.from_bytes(raw[4:8], "little") == 0, "gzip header timestamp is not zero"

with tarfile.open(archive_path, "r:gz") as tf:
    members = tf.getmembers()
    names = [m.name for m in members]
    assert names == sorted(names), "tar entries are not lexically ordered"
    for member in members:
        assert member.uid == 0, (member.name, member.uid)
        assert member.gid == 0, (member.name, member.gid)
        assert member.mtime == epoch, (member.name, member.mtime, epoch)

manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
assert manifest["schema"] == 1, manifest
assert manifest["project"] == "Crakbit Core", manifest
assert manifest["package_version"] == version, manifest
assert manifest["platform"] == "linux", manifest
assert manifest["arch"] in {"x86_64", "arm64"}, manifest
assert manifest["source_commit"] == source_commit.lower(), manifest
assert manifest["source_date_epoch"] == epoch, manifest
assert manifest["mainnet_enabled"] is False, manifest
assert manifest["upstreams"]["bitcoin_core_commit"] == lock["upstreams"]["bitcoin_core"]["commit_sha"], manifest
assert manifest["upstreams"]["yespower_commit"] == lock["upstreams"]["yespower"]["commit_sha"], manifest
assert manifest["pow"] == lock["pow"], manifest
repro = manifest["archive_reproducibility"]
assert repro == {
    "gid": 0,
    "gzip_timestamp": False,
    "normalized_mtime": True,
    "sorted_entries": True,
    "uid": 0,
}, repro
PY

HASH="$(sha256sum "$ARCHIVE_A" | awk '{print $1}')"
echo "CRAK-022 reproducible Linux package smoke: OK sha256=$HASH source=$SOURCE_COMMIT epoch=$EPOCH"
