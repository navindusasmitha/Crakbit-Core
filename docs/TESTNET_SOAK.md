# Public testnet soak operations runbook

This runbook is for the real CRAK-027 soak after CRAK-026 bootstrap nodes have been provisioned and `crakbit-bootstrap.py validate --require-public-ready` succeeds.

## 1. Preconditions

- At least two enabled public `testnet4` nodes are listed in `network/TESTNET_BOOTSTRAP.json`.
- The enabled nodes span at least two provider/region failure domains.
- Only P2P is internet-facing. Node RPC remains loopback-only/private.
- Every node is synced, not in initial block download, and has at least one peer.
- Continuous testnet mining is available so chain progress can be observed.
- All nodes run the same reviewed release or an explicitly documented compatibility matrix.

Do not start the launch qualification while the bootstrap manifest still contains only disabled placeholder nodes.

## 2. Evidence layout

Use one append-only observation file per node plus one shared event file:

```text
evidence/
  seed-a.jsonl
  seed-b.jsonl
  events.jsonl
```

Do not edit out failed observations. If an operational note is wrong, add a new explanatory event rather than rewriting historical samples.

## 3. Collection cadence

A normal production-style cadence is once per minute from a local timer/systemd unit or equivalent:

```bash
python3 scripts/crakbit-soak.py collect \
  --node seed-a \
  --datadir "$HOME/.crakbit" \
  --output "$HOME/crakbit-soak/seed-a.jsonl"
```

The tool records blocks, headers, best block hash, IBD state, verification progress, peer counts and node uptime. If local RPC is unavailable, it records an unhealthy sample and exits non-zero.

The repository does not install a remote management daemon and does not require public RPC.

## 4. Restart drill

For every enabled bootstrap node during candidate/launch qualification:

1. append a `restart` event immediately before the planned restart;
2. restart only that node;
3. confirm it reconnects to peers and resumes observations;
4. do not count the drill as recovered until a later healthy observation exists.

Stagger restart drills so the bootstrap network is not intentionally taken down at once.

## 5. Reorg drill

The 72-hour launch qualification requires at least one recovered reorg observation. Perform this only on testnet and only with a reviewed test plan. Record the observed depth:

```bash
python3 scripts/crakbit-soak.py event \
  --node seed-a \
  --event reorg \
  --depth 2 \
  --output evidence/events.jsonl \
  --note "controlled testnet reorg rehearsal"
```

A depth above the CRAK-027 policy maximum is a failed launch gate and requires review rather than evidence editing.

## 6. Candidate gate after 24 hours

```bash
python3 scripts/crakbit-soak.py evaluate \
  --observations-dir evidence \
  --events evidence/events.jsonl \
  --qualification candidate \
  --output evidence/candidate-summary.json
```

A candidate failure is actionable evidence. Fix the underlying node/network issue and start a fresh qualifying window when the failure invalidates the required duration or availability target.

## 7. Launch gate after 72 hours

```bash
python3 scripts/crakbit-soak.py evaluate \
  --observations-dir evidence \
  --events evidence/events.jsonl \
  --qualification launch \
  --output evidence/launch-summary.json
```

Keep the raw JSONL evidence and generated summary together. The summary alone is not a substitute for the underlying observations.

## 8. Failure handling

Treat these as hard investigation triggers:

- same-height nodes reporting different best-block hashes;
- tip spread above policy;
- repeated local RPC failures;
- node stuck in initial block download;
- no chain progress;
- peer count falling below policy;
- restart without later healthy recovery;
- reorg deeper than policy maximum;
- public RPC exposure or non-loopback RPC bind.

Do not hide a failure by deleting samples or lowering policy thresholds in the evidence branch. A threshold change is a separate reviewed repository change.

## 9. What passing CRAK-027 does not prove

A passing 72-hour soak is evidence for public-testnet operational stability under the tested conditions. It does not prove mainnet readiness, internet-facing pool security, arbitrary miner interoperability, absence of consensus bugs, or completion of external security review. Those remain later launch gates.
