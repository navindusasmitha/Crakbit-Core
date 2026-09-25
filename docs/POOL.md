# CRAK-014 Stratum Pool

CRAK-014 adds the first external mining-pool layer for Crakbit Core without changing chain consensus.

## Architecture

```text
crakbitd
   │ localhost RPC
   ▼
crakpool
   │ Stratum TCP
   ├──────── crakminer-stratum (PC / VPS / ARM64 later)
   ├──────── crakminer-stratum (PC / VPS)
   └──────── crakminer-stratum (...)
```

`crakpool` obtains `getblocktemplate` from the node, constructs the BIP34 coinbase split, distributes a unique `extranonce1` to each connection and accepts miner-controlled `extranonce2` values. Workers build the transaction merkle root, scan the canonical 80-byte header with native yespower, and submit shares back to the pool. The pool independently verifies each share with the same pinned yespower scanner used by CRAK-013. Network-target shares are rebuilt into complete blocks and sent to `crakbitd` with `submitblock`.

The node remains the final consensus authority.

## Supported CRAK-014 methods

The current JSON-lines Stratum surface implements:

- `mining.subscribe`
- `mining.authorize`
- `mining.set_difficulty`
- `mining.notify`
- `mining.submit`

`mining.extranonce.subscribe` and `mining.suggest_difficulty` are acknowledged for basic client tolerance, but CRAK-014 does not dynamically change extranonces or apply per-worker suggested difficulty.

The implementation is designed and CI-tested with `crakminer-stratum`. Compatibility with unrelated Stratum software is not yet guaranteed.

## Start a pool

The pool defaults to `127.0.0.1:3333` so an accidental install does not immediately expose a mining service.

Example testnet pool:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.0001
```

The wallet is used at startup to obtain one payout address. You can instead use a fixed address:

```bash
crakpool \
  --network testnet4 \
  --address tcrak... \
  --listen 127.0.0.1 \
  --port 3333
```

## Connect a worker

```bash
crakminer-stratum \
  --pool 127.0.0.1:3333 \
  --worker desktop-01 \
  --threads 2 \
  --cpu-limit 50
```

Useful worker controls:

```text
--threads N
--cpu-limit 1..100
--batch-hashes N
--shares N
--blocks N
```

`--cpu-limit` is an approximate native-worker duty cycle rather than an operating-system enforced CPU quota.

## Private LAN / testnet deployment

On the pool host, keep Crakbit RPC bound to localhost. Expose only the Stratum port to trusted miners.

Example:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 0.0.0.0 \
  --port 3333
```

Then on another machine:

```bash
crakminer-stratum \
  --pool SERVER_IP:3333 \
  --worker laptop-01 \
  --threads 1 \
  --cpu-limit 30
```

Use firewall rules so only intended test miners can reach the Stratum port. Do not expose `crakbitd` RPC to the public Internet.

## Share difficulty

CRAK-014 uses the conventional Bitcoin difficulty-1 target as the Stratum share-difficulty reference. Share difficulty controls how often workers submit proof to the pool; it does not change Crakbit network consensus difficulty.

A lower share difficulty produces more frequent pool shares and more verification overhead. A higher share difficulty produces fewer shares. The default is intended as a starting testnet value, not a production tuning recommendation.

## Payout model in CRAK-014

There is intentionally no automated pool reward distribution yet.

The complete block coinbase currently pays the single address configured by `--wallet` or `--address`. Worker names are accounting labels only and passwords are not used as strong authentication credentials.

Before a public-value pool is appropriate, a later milestone should add at least:

- persistent accepted/rejected share database;
- per-worker hashrate and difficulty accounting;
- vardiff;
- defined payout policy such as proportional or PPLNS;
- payout maturity handling and transaction batching;
- duplicate/replay/rate-limit hardening;
- bounded share-verification workers;
- TLS or a protected deployment layer;
- monitoring and restart recovery;
- third-party miner interoperability tests;
- security review.

## CI coverage

`tests/stratum_protocol_unit.py` freezes protocol math for BIP34 height encoding, share targets, compact target decoding and coinbase merkle branches.

`tests/stratum_pool_smoke.sh` starts a real Crakbit regtest node and pool, connects two separate worker sessions, proves distinct `extranonce1` values, mines blocks through both workers and verifies the active chain advances.

`tests/package_smoke.sh` repeats the pool path using the extracted/installed Linux package.
