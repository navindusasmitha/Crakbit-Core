#!/usr/bin/env bash
set -euo pipefail

# Install a built Crakbit Testnet v0.1 node on Ubuntu/Debian.
# Run from the repository root after scripts/build-testnet.sh has completed.
# Only P2P TCP/29111 should be exposed publicly. RPC remains loopback-only.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${CRAKBIT_DIST:-$ROOT/build/dist}"
PREFIX="${CRAKBIT_PREFIX:-/opt/crakbit-testnet}"
DATA_DIR="${CRAKBIT_DATA_DIR:-/var/lib/crakbit-testnet}"
CONF_DIR="${CRAKBIT_CONF_DIR:-/etc/crakbit}"
SERVICE="crakbit-testnet"
USER_NAME="${CRAKBIT_USER:-crakbit}"
ADDNODE="${CRAKBIT_ADDNODE:-}"

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)." >&2; exit 1; }
for f in crakbitd crakbitd-bin crakbit-cli crakbit-cli-bin; do
  [ -x "$DIST/$f" ] || { echo "Missing $DIST/$f; build the testnet first." >&2; exit 1; }
done

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --create-home --shell /usr/sbin/nologin "$USER_NAME"
fi

install -d -m 0755 "$PREFIX/bin" "$CONF_DIR"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$DATA_DIR"
for f in crakbitd crakbitd-bin crakbit-cli crakbit-cli-bin crakbit-wallet crakbit-tx crakbit-util; do
  [ -f "$DIST/$f" ] && install -m 0755 "$DIST/$f" "$PREFIX/bin/$f"
done
[ -f "$DIST/SHA256SUMS" ] && install -m 0644 "$DIST/SHA256SUMS" "$PREFIX/SHA256SUMS"

RPC_USER="crakbitrpc"
RPC_PASS="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(36))
PY
)"

cat > "$CONF_DIR/testnet.conf" <<EOF
# Crakbit Testnet v0.1
# Testnet only. Testnet CBIT has no monetary value.
server=1
listen=1
port=29111
rpcport=29110
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
rpcuser=$RPC_USER
rpcpassword=$RPC_PASS

# Keep RPC private and make the node useful for explorer/testing.
txindex=1

# Discovery is intentionally explicit during early testnet.
dnsseed=0
EOF

if [ -n "$ADDNODE" ]; then
  printf 'addnode=%s\n' "$ADDNODE" >> "$CONF_DIR/testnet.conf"
fi

chown root:"$USER_NAME" "$CONF_DIR/testnet.conf"
chmod 0640 "$CONF_DIR/testnet.conf"

cat > "/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=Crakbit Testnet v0.1 node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
ExecStart=$PREFIX/bin/crakbitd -datadir=$DATA_DIR -conf=$CONF_DIR/testnet.conf -printtoconsole
ExecStop=$PREFIX/bin/crakbit-cli -datadir=$DATA_DIR -conf=$CONF_DIR/testnet.conf stop
Restart=on-failure
RestartSec=5
TimeoutStopSec=120
LimitNOFILE=65536
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$DATA_DIR
LockPersonality=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE.service"
systemctl restart "$SERVICE.service"

sleep 2
systemctl --no-pager --full status "$SERVICE.service" || true

echo
echo "Crakbit Testnet node installed."
echo "P2P port : TCP 29111 (public if this is a seed/public node)"
echo "RPC port : TCP 29110 (loopback only; do NOT expose it)"
echo "Config   : $CONF_DIR/testnet.conf"
echo "Data     : $DATA_DIR"
echo "Logs     : journalctl -u $SERVICE -f"
echo "Status   : sudo -u $USER_NAME $PREFIX/bin/crakbit-cli -datadir=$DATA_DIR -conf=$CONF_DIR/testnet.conf getblockchaininfo"
