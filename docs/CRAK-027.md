# CRAK-027 — Public testnet soak and monitoring

CRAK-027 defines the evidence contract for proving that an internet-facing Crakbit testnet remains healthy over time. It deliberately separates code/CI readiness from the later real-world soak run: repository CI can validate the monitoring machinery, but it cannot fabricate public uptime or reorg evidence.

## What this milestone adds

- `network/SOAK_POLICY.json` with explicit availability, convergence, peer, verification, restart, reorg and duration thresholds.
- `scripts/crakbit-soak.py collect` to append one local-RPC observation from a public node without exposing RPC to the internet.
- append-only JSONL observation history per node.
- explicit restart and reorg evidence events.
- `scripts/crakbit-soak.py evaluate` for multi-node qualification.
- three qualification levels:
  - `smoke`: control-plane/evaluator sanity with no minimum elapsed window;
  - `candidate`: at least 24 hours plus restart recovery on every enabled node;
  - `launch`: at least 72 hours plus restart recovery on every enabled node and at least one recovered reorg observation.
- regression tests for healthy launch evidence, split tips, insufficient duration, placeholder bootstrap hosts, excessive reorg depth and local CLI collection.
- a dedicated `Verify Crakbit Public Testnet Soak` workflow.

## Current launch policy

The checked-in CRAK-026 bootstrap manifest intentionally contains disabled `.invalid` placeholders. Therefore no repository commit or CI result may claim that the real public testnet has completed a soak yet.

A real `candidate` or `launch` qualification requires:

1. at least two enabled public nodes;
2. at least two independent provider/region failure domains;
3. loopback-only non-public RPC on every node;
4. per-node observation histories generated on the node itself with local `crakbit-cli`;
5. at least 99% successful observations;
6. no more than three consecutive failed observations;
7. final node tip-height spread no greater than two blocks;
8. identical hashes if final heights are equal;
9. header lag no greater than two blocks;
10. at least one peer connection and completed initial sync;
11. observed chain/mining progress during the window;
12. restart recovery evidence for every enabled node for `candidate` and `launch`;
13. at least one recovered reorg event with depth no greater than six for `launch`.

The thresholds are reviewable policy, not consensus rules.

## Local collection

On each public node, run the collector through the local CLI/RPC path only:

```bash
python3 scripts/crakbit-soak.py collect \
  --node seed-a \
  --datadir "$HOME/.crakbit" \
  --output evidence/seed-a.jsonl
```

A failed RPC sample is still appended as an unhealthy observation before the command exits non-zero. This keeps outages in the evidence instead of silently dropping them.

## Event evidence

Immediately before a planned restart drill:

```bash
python3 scripts/crakbit-soak.py event \
  --node seed-a \
  --event restart \
  --output evidence/events.jsonl \
  --note "planned service restart"
```

For an observed or deliberately rehearsed testnet reorg:

```bash
python3 scripts/crakbit-soak.py event \
  --node seed-a \
  --event reorg \
  --depth 2 \
  --output evidence/events.jsonl \
  --note "controlled reorg rehearsal"
```

The evaluator only counts restart/reorg evidence when a later healthy observation exists for that node.

## Evaluation

24-hour candidate gate:

```bash
python3 scripts/crakbit-soak.py evaluate \
  --bootstrap network/TESTNET_BOOTSTRAP.json \
  --policy network/SOAK_POLICY.json \
  --observations-dir evidence \
  --events evidence/events.jsonl \
  --qualification candidate \
  --output evidence/candidate-summary.json
```

72-hour launch gate:

```bash
python3 scripts/crakbit-soak.py evaluate \
  --bootstrap network/TESTNET_BOOTSTRAP.json \
  --policy network/SOAK_POLICY.json \
  --observations-dir evidence \
  --events evidence/events.jsonl \
  --qualification launch \
  --output evidence/launch-summary.json
```

## Security boundary

The collector never performs remote RPC discovery and never changes node configuration. Operators must keep RPC loopback-only or otherwise private according to CRAK-026. Public monitoring may probe the P2P endpoint separately, but chain state is collected locally and then copied to the evidence aggregation location.

Evidence files can contain operational metadata such as node names, timestamps and peer counts. Do not place credentials, RPC cookies, wallet material or private keys in soak evidence.

## Exit condition

The CRAK-027 **code milestone** is complete when policy, collector/evaluator, tests, documentation, integrity wiring and CI are green.

The **public-testnet soak gate** is not complete until real independently hosted CRAK-026 bootstrap nodes exist and an operator records a passing 72-hour `launch` evaluation. That real-world result is intentionally outside normal PR CI.
