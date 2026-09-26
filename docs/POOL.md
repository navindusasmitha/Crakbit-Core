# Crakbit Pool — CRAK-014 / CRAK-015 / CRAK-016 / CRAK-017

The Crakbit pool stack is an external mining/payment layer. It does not change chain consensus, block validation, monetary policy, or the yespower proof-of-work rules enforced by `crakbitd`.

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
   │ frozen reviewed batch
   ▼
crakpool-pay                     CRAK-017 signed transaction pipeline
   │ prepare: no broadcast
   │ explicit broadcast
   ▼
crakbitd mempool / chain
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

The block coinbase pays the pool address selected through `--wallet` or a fixed `--address`. Worker rewards are separate SQLite accounting credits; no worker payment is implicit merely because a block was found.

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
- accounting pool fees;
- per-worker reward credits.

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

Changing a registered address affects future plans only. Existing stored plans keep the exact address frozen into that batch.

## CRAK-016 chain reconciliation

Before planning a payout, CRAK-016 compares every pool-found block with the canonical block hash at its recorded height:

```bash
crakpool-payout \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  reconcile \
  --network testnet4
```

Credits are plan-eligible only when their source block is canonical. An unbroadcast plan linked to a source block that disappears in a reorg is invalidated. If the block later becomes canonical again, its orphaned credits may return to `pending`, but an invalidated old batch is never silently reactivated.

## CRAK-016 coinbase maturity and payout planning

The default maturity gate is 100 confirmations, matching the current Crakbit coinbase-maturity consensus setting. The planner uses a fresh canonical-chain snapshot and only consumes credits whose source block satisfies the configured maturity.

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

With `--wallet`, the planner reads `getbalances().mine.trusted` and refuses a plan when trusted funds are below the selected worker total plus `--fee-reserve-sats`. Without `--wallet`, planning remains useful for reconciliation/audit, but wallet funding is not asserted.

A plan freezes:

- canonical tip height and hash;
- maturity threshold;
- worker payout address;
- exact worker amount in satoshis;
- exact underlying credit rows.

Selected credits move from `pending` to `planned`, preventing them from being included in another active plan. A still-unbroadcast CRAK-016 plan can be explicitly cancelled, which returns canonical credits to `pending`.

Useful commands:

```bash
crakpool-payout --db <DB> status
crakpool-payout --db <DB> show --batch <BATCH_ID>
crakpool-payout --db <DB> cancel --batch <BATCH_ID>
```

## CRAK-017 transaction preparation

`crakpool-pay prepare` is the first operation that handles a signed spend. It still does **not** broadcast.

```bash
crakpool-pay \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  prepare \
  --network testnet4 \
  --batch <BATCH_ID> \
  --wallet pool \
  --fee-rate 1.0 \
  --max-fee-sats 1000000 \
  --confirmations 6
```

Before a transaction is persisted, CRAK-017:

1. takes a fresh canonical-chain snapshot and reconciles the credited source blocks;
2. requires every linked source credit to remain canonical and mature;
3. revalidates every worker payout address on the selected network;
4. aggregates workers that intentionally use the same payout address while preserving per-worker ledger detail;
5. funds a PSBT from confirmed, non-unsafe wallet inputs;
6. locks selected wallet inputs and disables opt-in RBF for the initial payout;
7. verifies the funded non-change outputs exactly match the frozen batch amounts;
8. signs with the named pool wallet and finalizes the PSBT;
9. enforces `--max-fee-sats`;
10. requires `testmempoolaccept` to accept the signed raw transaction;
11. persists the txid, signed raw transaction, selected inputs, fee and confirmation policy in SQLite.

Linked credits atomically move from `planned` to `paying`, and the batch becomes `prepared`. Worker credit values are **not** reduced for the transaction fee; the pool wallet pays the fee from its own selected inputs/change.

## CRAK-017 explicit broadcast

Broadcast is a separate operator action:

```bash
crakpool-pay \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  broadcast \
  --network testnet4 \
  --batch <BATCH_ID>
```

Immediately before sending, CRAK-017 reconciles the source credits again. A prepared transaction whose source credit loses canonical maturity is invalidated rather than broadcast. A still-healthy transaction must pass `testmempoolaccept` again before `sendrawtransaction` is called, and the returned txid must match the persisted txid.

The command is restart-aware: if the node/wallet already knows the persisted txid because a process crashed after broadcast but before the database update, CRAK-017 records the transaction as broadcast instead of creating or sending a replacement payment.

## CRAK-017 recovery and paid finalization

Use `sync` after restarts and as the confirmation/recovery loop:

```bash
crakpool-pay \
  --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  sync \
  --network testnet4
```

For a `prepared` transaction that is not yet broadcast, sync checks the persisted signed raw transaction and attempts to restore its input locks after a node restart. For an already-broadcast transaction, sync observes wallet/mempool state and confirmation count. `--rebroadcast` can resend the exact persisted raw transaction; it does not build a new payment.

When confirmations reach the threshold frozen during `prepare`, the linked credits atomically move from `paying` to `paid` and the batch becomes `paid`.

If the wallet reports a negative confirmation count/conflict after broadcast, CRAK-017 enters `payment_conflict`/`conflicted`. Credits remain `paying` and reserved for manual review; they are not automatically returned to `pending`, which prevents a second automatic payout while the original spend may still be recoverable or replaced elsewhere.

Payment state summary:

```text
credit: pending -> planned -> paying -> paid
batch:  planned -> prepared -> broadcast -> paid
                         \-> invalidated  (pre-broadcast source failure)
                                   broadcast -> payment_conflict (manual review)
```

## Payment security boundary

CRAK-017 can move CRAK when the operator explicitly invokes `broadcast`. Keep these boundaries intact:

- keep Crakbit RPC bound to localhost/private interfaces;
- do not expose wallet RPC through the public Stratum listener;
- restrict filesystem access to the SQLite ledger;
- remember that a `prepared`/`broadcast` ledger can contain a **fully signed raw transaction** that is itself broadcast-capable;
- control ledger backups as payment-sensitive data;
- use a dedicated pool wallet rather than unrelated personal funds;
- review batch total, worker outputs, fee and txid before explicit broadcast;
- treat `payment_conflict` as manual review, not a reason to create a replacement worker payment automatically.

The current pipeline is testnet engineering infrastructure, not a claim of production-grade custody safety.

## Deployment boundary

On a pool host, keep Crakbit RPC bound to localhost. Expose only the Stratum port to intended miners and protect it with network/firewall controls.

Current engineering limitations before public-value deployment include:

- worker passwords are not strong authentication;
- no TLS in the built-in Stratum listener;
- no production-grade rate limiting / bounded verification queue yet;
- duplicate-share persistence across reconnects still needs hardening;
- broader third-party miner interoperability needs testing;
- payment conflict/replacement operating procedures need extended adversarial testing;
- public monitoring, backup/recovery procedures, and external security review remain gates.

## CI coverage

- `tests/stratum_protocol_unit.py`: protocol math and coinbase/merkle primitives.
- `tests/stratum_pool_smoke.sh`: two real worker sessions against a Crakbit regtest node.
- `tests/pool_accounting_unit.py`: satoshi allocation, proportional/PPLNS accounting, vardiff, restart persistence.
- `tests/accounting_pool_smoke.sh`: real CRAK-015 SQLite accounting across a pool restart.
- `tests/payout_planner_unit.py`: maturity, deterministic planning, cancellation, reorg invalidation and recovery transitions.
- `tests/payout_planner_smoke.sh`: real node address validation, 100-confirmation maturity, payout planning, and `invalidateblock` reorg fail-closed behavior.
- `tests/payment_pipeline_unit.py`: CRAK-017 prepared/broadcast/paid/conflict state-machine invariants and same-address output aggregation.
- `tests/payment_pipeline_smoke.sh`: real signed PSBT preparation, node restart recovery, explicit broadcast, mining confirmation, paid-credit transition and exact worker receipt on regtest.
- `tests/package_smoke.sh`: extracted/installed Linux package mining, accounting and payout/payment command availability.
