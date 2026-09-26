# CRAK-026 — Public testnet bootstrap control plane

CRAK-026 prepares Crakbit testnet4 for an internet-facing bootstrap deployment without pretending that public nodes already exist.

## What this milestone adds

- `network/TESTNET_BOOTSTRAP.json` as the reviewed bootstrap-node inventory.
- `scripts/crakbit-bootstrap.py` for manifest validation, deterministic `addnode=` config rendering and TCP P2P reachability checks.
- a strict `--require-public-ready` gate that rejects placeholder/local/private endpoints, insufficient node count and insufficient provider/region failure-domain diversity.
- explicit RPC perimeter rules: bootstrap RPC must remain loopback-only and must never be declared public in the manifest.
- `tests/bootstrap_unit.py` covering config rendering, local multi-node health checks, duplicate endpoints, unsafe RPC policy and failure-domain rules.
- a dedicated `Verify Crakbit Public Testnet Bootstrap` workflow.
- `docs/PUBLIC_TESTNET.md` deployment/recovery runbook.

## Public-ready contract

A manifest is considered eligible for public bootstrap deployment only when all of the following are true:

1. the network is `testnet4`;
2. at least `minimum_public_nodes` nodes are enabled, with a floor of two;
3. at least `minimum_failure_domains` distinct `(provider, region)` pairs exist, with a floor of two;
4. every enabled endpoint is a syntactically valid `host:port` or `[ipv6]:port` endpoint;
5. enabled endpoints are not obvious localhost, private-address or placeholder endpoints;
6. P2P is explicitly public while RPC is explicitly non-public and loopback-bound.

The validator intentionally does not claim that a DNS hostname is reachable merely because it is syntactically public-looking. Reachability is a separate `health` check.

## Commands

Validate the repository template:

```bash
python3 scripts/crakbit-bootstrap.py validate
```

The checked-in template is expected to pass ordinary validation and fail public-ready validation until operators replace the `.invalid` placeholders with real independent public nodes:

```bash
python3 scripts/crakbit-bootstrap.py validate --require-public-ready
```

Render a node configuration snippet from enabled bootstrap nodes:

```bash
python3 scripts/crakbit-bootstrap.py render-conf --require-public-ready > crakbit-bootstrap.conf
```

Probe enabled P2P endpoints without touching RPC:

```bash
python3 scripts/crakbit-bootstrap.py health \
  --require-public-ready \
  --minimum-reachable 2 \
  --timeout 3
```

## Security boundary

The health probe performs a TCP connect only. It does not authenticate to, query or expose node RPC. Public operators should expose only the Crakbit P2P listener required for peer bootstrap; wallet RPC, pool RPC and administrative interfaces stay private.

CRAK-026 does not add DNS seeds to consensus/network source, hard-code third-party IP addresses, enable mainnet, create checkpoints, or claim sustained network operation. Those decisions require observed public-testnet history and later milestones.

## Exit condition

The code milestone is complete when the bootstrap control plane, policy, package wiring and CI are green. The *deployment* gate is satisfied only after operators provision real nodes in at least two failure domains, replace the placeholder manifest entries, pass `--require-public-ready`, and record a healthy public reachability check. Sustained multi-node soak is CRAK-027.
