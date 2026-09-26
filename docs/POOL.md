# Crakbit Pool — CRAK-014 / CRAK-015 / CRAK-016

The Crakbit pool stack is an external mining layer. It does not change chain consensus, block validation, monetary policy, or the yespower proof-of-work rules enforced by `crakbitd`.

## Architecture

```text
crakbitd
   │ localhost RPC
   ▼
crakpool                         CRAK-014 protocol + CRAK-015 accounting
   │ Stratum TCP
   ├──────── crakminer-stratum
   ├──────── crakminer-stratum
   └──────── ...
   │
   ▼
SQLite ledger                    shares / blocks / worker credits / vardiff
   │
   ▼
crakpool-payout                  CRAK-016 reconciliation + payout planning
   │
   └──────── NO signing / NO transaction broadcast in CRAK-016
```

`crakpool` obtains `getblocktemplate` from the node, constructs the BIP34 coinbase split, distributes a unique `extranonce1` to each connection, and accepts miner-controlled `extranonce2` values. Workers build the transaction merkle root, scan the canonical 80-byte header with native yespower, and submit shares back to the pool. The pool independently verifies each share with the same pinned yespower scanner used by CRAK-013. Network-target shares are rebuilt into complete blocks and sent to `crakbitd` with `submitblock`.

The node remains the final consensus authority.

## Stratum surface

The current JSON-lines Stratum subset implements:

- `mining.subscribe`
- `mining.authorize`
- `mining.set_difficulty`
- `mining.notify`
- `mining.submit`

`mining.extranonce.subscribe` and `mining.suggest_difficulty` are acknowledged for basic client tolerance. CRAK-015 adds server-controlled per-worker vardiff. A submitted worker name must match the worker authorized on that connection before a share can be credited.

The implementation is CI-tested with `crakminer-stratum`. Compatibility with unrelated Stratum software is not yet guaranteed.

## Start an accounting pool

The pool defaults to `127.0.0.1:3333` so an accidental install does not immediately expose a mining service.

Example testnet pool using PPLNS accounting:

```bash
crakpool \
  --network testnet4 \
  --wallet pool \
  --listen 127.0.0.1 \
  --port 3333 \
  --share-difficulty 0.0001 \
  --payout-mode pplns \
  --pplns-shares 1000 \
  --pool-fee-bps 0
```

The block coinbase pays the pool address selected through `--wallet` or a fixed `--address`. Worker rewards are separate SQLite accounting credits; CRAK-015 does not send those credits on-chain.

Default ledger location:

```text
~/.crakbit/crakpool-testnet4.sqlite3
```

A custom path can be supplied with `--db`.

## Connect a worker

```bash
crakminer-stratum \
  --pool 127.0.0.1:3333 \
  --worker desktop-01 \
  --threads 2 \
  --cpu-limit 50
```

Useful worker controls include `--threads`, `--cpu-limit`, `--batch-hashes`, `--shares`, and `--blocks`. `--cpu-limit` is an approximate native-worker duty cycle rather than an operating-system enforced CPU quota.

## CRAK-015 accounting

The SQLite WAL ledger persists:

- worker identity and current share difficulty;
- accepted/rejected share counters;
- accepted share difficulty and timestamps;
- found blocks;
- proportional or difficulty-weighted PPLNS reward allocation;
- accounting-only pool fees;
- per-worker pending credits.

Reward splitting uses deterministic integer-satoshi allocation and conserves every distributable satoshi. Vardiff is bounded by configured minimum/maximum values and by a maximum 4x increase or 0.25x decrease per retarget.

Inspect the ledger with:

```bash
crakpool-stats --db ~/.crakbit/crakpool-testnet4.sqlite3 --json
```

## CRAK-016 payout-address registration

A worker must have a payout address before mature credits can enter a payout plan. Registration validates the address using the selected Crakbit node/network.

```bash
crakpool-payout \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  register \
  --network testnet4 \
  --worker desktop-01 \
  --address <CRAK_ADDRESS>
```

Changing a registered address affects future plans only. Existing stored plans keep the exact address that was frozen into that batch.

## CRAK-016 chain reconciliation

Before planning a payout, CRAK-016 compares every pool-found block with the canonical block hash at the recorded height:

```bash
crakpool-payout \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  reconcile \
  --network testnet4
```

Credits are eligible only when their source block is still canonical. If a reorg removes a credited block:

1. the block is marked non-canonical;
2. its credits become `orphaned`;
3. any unbroadcast `planned` batch linked to those credits becomes `invalidated`.

If that block later becomes canonical again, its orphaned credits may return to `pending`, but an invalidated old payout batch is never silently reactivated.

## CRAK-016 coinbase maturity and payout planning

The default maturity gate is 100 confirmations, matching the current Crakbit coinbase-maturity consensus setting. The planner uses a fresh canonical-chain snapshot and only consumes credits whose source block satisfies the configured maturity.

Example:

```bash
crakpool-payout \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  plan \
  --network testnet4 \
  --wallet pool \
  --maturity 100 \
  --minimum-sats 100000 \
  --max-outputs 100
```

With `--wallet`, the planner also reads `getbalances().mine.trusted` and refuses a plan when trusted funds are below the selected worker total plus `--fee-reserve-sats`. Without `--wallet`, planning can still be used for reconciliation/audit, but wallet funding is not asserted.

A plan freezes:

- canonical tip height and hash;
- maturity threshold;
- worker payout address;
- exact worker amount in satoshis;
- the exact underlying credit rows.

Selected credits move from `pending` to `planned`, preventing them from being included in another concurrent plan. A still-unbroadcast plan can be explicitly cancelled, which returns canonical credits to `pending`.

Useful commands:

```bash
crakpool-payout --db <DB> status
crakpool-payout --db <DB> show --batch <BATCH_ID>
crakpool-payout --db <DB> cancel --batch <BATCH_ID>
```

## Payment safety boundary

**CRAK-016 never creates, signs, or broadcasts a payout transaction.** Its output is an auditable payout plan only. This is intentional: wallet transaction construction, fee selection, signing, broadcast, txid persistence, restart recovery, replacement/conflict handling, and paid-credit finalization require a separate reviewed milestone.

Do not treat a CRAK-016 `planned` batch as proof that an on-chain payment happened.

## Deployment boundary

On a pool host, keep Crakbit RPC bound to localhost. Expose only the Stratum port to intended miners and protect it with network/firewall controls.

Current engineering limitations before public-value deployment include:

- worker passwords are not strong authentication;
- no TLS in the built-in Stratum listener;
- no production-grade rate limiting / bounded verification queue yet;
- duplicate-share persistence across reconnects still needs hardening;
- automatic payouts are intentionally disabled;
- broader third-party miner interoperability needs testing;
- public monitoring, backup/recovery procedures, and security review remain gates.

## CI coverage

- `tests/stratum_protocol_unit.py`: protocol math and coinbase/merkle primitives.
- `tests/stratum_pool_smoke.sh`: two real worker sessions against a Crakbit regtest node.
- `tests/pool_accounting_unit.py`: satoshi allocation, proportional/PPLNS accounting, vardiff, restart persistence.
- `tests/accounting_pool_smoke.sh`: real CRAK-015 SQLite accounting across a pool restart.
- `tests/payout_planner_unit.py`: maturity, deterministic planning, cancellation, reorg invalidation and recovery state transitions.
- `tests/payout_planner_smoke.sh`: real node address validation, 100-confirmation maturity, payout planning, and `invalidateblock` reorg fail-closed behavior.
- `tests/package_smoke.sh`: extracted/installed Linux package mining, pool accounting, and CRAK-016 payout-tool availability.
