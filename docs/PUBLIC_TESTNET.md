# Crakbit public testnet deployment runbook

This runbook is for Crakbit `testnet4`. It is not a mainnet deployment guide.

## 1. Provision independent bootstrap nodes

Provision at least two always-on Linux hosts in different provider/region failure domains. Each host should have:

- a stable public IPv4 and/or IPv6 address or stable DNS name;
- inbound Crakbit P2P access on the chosen listener port;
- outbound internet access for peer connectivity and updates;
- node RPC bound only to loopback or a separately protected private network;
- a non-wallet bootstrap role unless an operational reason requires otherwise;
- host firewalling, automatic security updates appropriate to the operator, clock synchronization and log rotation.

Do not expose wallet RPC or pool RPC to the public internet.

## 2. Install the trusted testnet package

Use a release produced from `main` that passed CRAK-022/024/025 verification. Verify the archive checksum, embedded `BUILD-MANIFEST.json`, `RELEASE-MANIFEST.json` and GitHub/Sigstore provenance before deployment.

## 3. Configure each node

Example baseline:

```text
testnet4=1
server=1
listen=1
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
```

Use a dedicated datadir and operating-system service account. Avoid putting RPC credentials in world-readable files. Bootstrap nodes should not depend on one another exclusively; each should also be able to discover/retain ordinary testnet peers once the network grows.

## 4. Update the bootstrap manifest

Replace the disabled `.invalid` entries in `network/TESTNET_BOOTSTRAP.json` with the real endpoints, provider and region. Enable only nodes that are intended to serve as public bootstrap endpoints.

Then require the strict gate:

```bash
python3 scripts/crakbit-bootstrap.py validate --require-public-ready
```

Render the client-side bootstrap snippet:

```bash
python3 scripts/crakbit-bootstrap.py render-conf --require-public-ready
```

## 5. Verify public P2P reachability

From a machine outside the bootstrap hosts' networks:

```bash
python3 scripts/crakbit-bootstrap.py health \
  --require-public-ready \
  --minimum-reachable 2 \
  --timeout 3
```

The health command is intentionally P2P TCP-only; it does not query RPC.

## 6. Recovery procedure

If one bootstrap node fails:

1. keep the failed node disabled in the manifest until it is actually reachable and synchronized again;
2. ensure at least one independent bootstrap endpoint remains available to new peers;
3. rebuild/reinstall only from a verified release artifact;
4. restore configuration, not wallet/private-key state, unless that host intentionally has a wallet role;
5. sync from the live Crakbit testnet and compare tip/hash with other independent nodes through private operator RPC;
6. re-enable the endpoint only after external P2P health succeeds.

If all bootstrap nodes fail, existing peers may continue to communicate using their known peer database, but new clean nodes can lose the bootstrap path. Restore at least one independently verified node first, then restore the remaining failure domains.

## 7. Reorg and chain-disagreement response

Do not introduce `assumevalid`, minimum-chain-work or checkpoints merely to hide a disagreement. Compare independent node tips, peer sets and logs; identify whether the event is a normal higher-work reorg, a connectivity partition, invalid-block rejection or a software defect. Preserve logs and data directories before destructive recovery.

Checkpoint/minimum-work policy may be introduced only from observed stable Crakbit testnet history in a separately reviewed milestone.

## 8. CRAK-027 handoff

After real public bootstrap endpoints are healthy, CRAK-027 records sustained operation: uptime, continuous mining, multi-node tip agreement, natural/forced reorg behavior, restart/recovery evidence and monitoring. Public bootstrap reachability alone is not sufficient for a mainnet-readiness claim.
