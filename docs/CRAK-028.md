# CRAK-028 — Internet-facing pool security hardening

CRAK-028 adds a dedicated security edge in front of the existing Crakbit
Stratum/accounting pool. The accounting pool remains a loopback-only trusted
service. Internet clients connect to `crakpool-edge`, which is the only
component intended to bind a public Stratum socket.

## Security boundary

The supported deployment is:

`miner -> TLS crakpool-edge -> loopback crakpool -> loopback crakbit RPC`

The edge does not hold wallet keys and does not expose node RPC. It forwards a
small Stratum V1 subset to the existing pool only after enforcing the security
policy in `network/POOL_SECURITY.json`.

A direct public bind of the internal `crakpool`/`crakpool-accounting` service
is outside the CRAK-028 supported public deployment.

## Controls

CRAK-028 implements:

- TLS 1.2 or newer for every non-loopback edge bind;
- PBKDF2-HMAC-SHA256 worker secrets with per-record random salts;
- no plaintext worker secrets in the credential file;
- constant-time credential comparison;
- strict worker-name syntax and maximum length;
- subscribe-before-authorize sequencing;
- one worker identity bound to each authenticated connection;
- rejection of `mining.submit` when its worker differs from the authenticated worker;
- a small allowlist of Stratum methods;
- maximum JSON-line size;
- authentication and idle timeouts;
- global and per-IP connection limits;
- per-session message and submit token buckets;
- a global submit token bucket to prevent aggregate scanner/RPC pressure;
- temporary IP bans after repeated authentication failures;
- loopback-only upstream enforcement;
- structured security events that never contain passwords;
- private-file permission checks for the worker credential file and TLS key;
- official `crakminer-stratum` verified-TLS transport plus non-argv worker secret input (`--password-file` / `--password-stdin`).

The edge replaces the worker password with the literal `edge-authenticated`
before forwarding `mining.authorize` to the trusted loopback pool. The real
worker secret is therefore not forwarded into the pool process.

## Credential format

The credential database is JSON with schema 1 and contains salted PBKDF2
digests, never plaintext worker passwords. Create or rotate a worker without
putting the secret on the command line:

```bash
python3 scripts/crakpool-edge.py credential \
  --file /etc/crakbit/pool-workers.json \
  --worker rig1
```

For automation, `--secret-stdin` reads exactly one line from standard input.
The credential file is written atomically and mode `0600` on POSIX systems.

## Public deployment gate

The following must all be true before the edge may bind a non-loopback address:

1. a valid worker credential file is configured;
2. the upstream host is loopback;
3. both a TLS certificate and a private key are configured;
4. the TLS key and credential file are not group/world readable;
5. policy validation passes.

Example preflight:

```bash
python3 scripts/crakpool-edge.py check \
  --listen 0.0.0.0 --port 3443 \
  --upstream-host 127.0.0.1 --upstream-port 3333 \
  --auth-file /etc/crakbit/pool-workers.json \
  --tls-cert /etc/crakbit/tls/fullchain.pem \
  --tls-key /etc/crakbit/tls/privkey.pem
```

Then run:

```bash
python3 scripts/crakpool-edge.py serve \
  --listen 0.0.0.0 --port 3443 \
  --upstream-host 127.0.0.1 --upstream-port 3333 \
  --auth-file /etc/crakbit/pool-workers.json \
  --tls-cert /etc/crakbit/tls/fullchain.pem \
  --tls-key /etc/crakbit/tls/privkey.pem \
  --security-log /var/log/crakbit/pool-security.jsonl
```

The internal pool must remain on `127.0.0.1:3333`. The maintained worker can
connect to the edge without exposing its secret in argv:

```bash
crakminer-stratum --pool pool.example.org:3443 --worker rig1 \
  --password-file "$HOME/.crakbit/rig1.secret" --tls \
  --tls-server-name pool.example.org --threads 1 --cpu-limit 50
```

Certificate verification and hostname checking are enabled by default;
`--tls-ca-file` is available for an explicit private/test CA.

## What CRAK-028 does not claim

CRAK-028 is the repository/runtime security gate for an internet-facing pool
edge. It does not claim that a production public pool has already been deployed
or externally penetration-tested. Firewalling, host patching, certificate
lifecycle, log retention, DDoS upstream protection, real public testnet soak
evidence, and independent security review remain operational responsibilities
or later launch gates.

No mainnet activation or payout-custody change is included.
