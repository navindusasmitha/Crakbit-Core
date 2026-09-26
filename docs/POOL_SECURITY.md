# Crakbit public pool security runbook

This runbook is the operator-facing CRAK-028 deployment procedure.

## Topology

Use separate trust surfaces even when they are on one host:

- `crakpool` accounting service: loopback only;
- `crakpool-edge`: public TLS Stratum boundary;
- `crakbitd` RPC: loopback/private only.

Recommended flow:

`Internet miner -> TCP/TLS 3443 -> crakpool-edge -> 127.0.0.1:3333 -> crakpool`

Never expose the node RPC port through the pool firewall.

## 1. Create the credential store

```bash
install -d -m 0700 /etc/crakbit
crakpool-edge credential \
  --file /etc/crakbit/pool-workers.json \
  --worker rig1
```

Use a different high-entropy secret for each worker. Rotate a compromised
worker by running the same command for that worker again. Do not pass worker
secrets as command-line arguments and do not commit the credential file to Git.

## 2. Keep the internal pool private

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 127.0.0.1 \
  --port 3333 \
  --payout-mode pplns
```

Firewall policy must not expose `3333` or the node RPC port publicly.

## 3. Provision TLS

Use a certificate whose hostname matches the public pool DNS name. Restrict
the private key to the service account. CRAK-028 refuses a key that is
group/world readable on POSIX systems. The edge enforces TLS 1.2 as the minimum.

## 4. Run the configuration preflight

```bash
crakpool-edge check \
  --listen 0.0.0.0 --port 3443 \
  --upstream-host 127.0.0.1 --upstream-port 3333 \
  --auth-file /etc/crakbit/pool-workers.json \
  --tls-cert /etc/crakbit/tls/fullchain.pem \
  --tls-key /etc/crakbit/tls/privkey.pem
```

Do not continue if this command fails.

## 5. Start the edge

```bash
crakpool-edge serve \
  --listen 0.0.0.0 --port 3443 \
  --upstream-host 127.0.0.1 --upstream-port 3333 \
  --auth-file /etc/crakbit/pool-workers.json \
  --tls-cert /etc/crakbit/tls/fullchain.pem \
  --tls-key /etc/crakbit/tls/privkey.pem \
  --security-log /var/log/crakbit/pool-security.jsonl
```

The JSONL security log records connection opens/closes, authentication
failures, temporary bans, protocol violations, identity mismatches, rate
limits, timeouts and upstream failures. It does not log worker passwords.

## 6. Miner configuration

Use the public TLS endpoint and the exact credential pair assigned to that
worker. Store the worker secret in a private file instead of argv:

```bash
install -m 0600 /dev/null "$HOME/.crakbit/rig1.secret"
printf '%s\n' '<WORKER_SECRET>' > "$HOME/.crakbit/rig1.secret"
crakminer-stratum \
  --pool pool.example.org:3443 \
  --worker rig1 \
  --password-file "$HOME/.crakbit/rig1.secret" \
  --tls \
  --tls-server-name pool.example.org \
  --threads 1 --cpu-limit 50
```

The official worker verifies the certificate chain and hostname by default and
requires TLS 1.2 or newer. Use `--tls-ca-file` only when an explicit private or
test CA must be trusted. There is no insecure certificate-bypass switch in the
maintained CRAK-028 path.

A connection must subscribe before authorizing. The worker value in every
`mining.submit` must match the authenticated worker identity.

## 7. Incident response

Repeated `auth_failure` or `ip_banned`: rotate a suspected leaked worker
secret, retain the JSONL evidence, and consider an upstream firewall/DDoS block
for persistent abuse.

Repeated `submit_rate_limit`: inspect the miner or flood source; do not weaken
the repository policy just to silence abusive traffic.

`upstream_connect_failure`: verify the internal pool on loopback; never move
the edge upstream to a public address.

TLS failures: verify certificate expiry, hostname, chain and key permissions;
do not fall back to public plaintext Stratum.

## 8. Launch evidence

CRAK-028 CI proves the edge controls and TLS/auth regression path. A public
launch still requires real CRAK-026 bootstrap nodes, CRAK-027 soak evidence,
host/firewall configuration and later independent security review.
