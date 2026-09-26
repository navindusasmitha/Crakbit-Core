# CRAK-018 payout preflight and recovery

CRAK-018 adds an operator safety guard around the CRAK-017 payout transaction lifecycle. It remains testnet/regtest engineering infrastructure and does not add automatic signing or transaction broadcast.

## Goals

- Reconcile every source block again immediately before an operator signs/broadcasts a payout.
- Require every linked source credit to remain canonical, mature, and reserved in `planned` state.
- Decode the funded PSBT and verify that each planned worker address still receives the exact planned satoshi amount.
- Optionally enforce an operator-provided maximum fee in satoshis.
- Record successful and failed preflights in the SQLite ledger for audit/restart visibility.
- Provide a guarded txid attach path that requires a recent successful preflight.
- Allow recovery from an abandoned, never-broadcast PSBT by unlocking its wallet inputs and cancelling the payment only after explicit operator attestation.

## Safety boundary

`crakpool-payguard` never signs a PSBT and never broadcasts a transaction. The operator remains responsible for external signing and broadcast.

Cancellation is intentionally fail-closed. `cancel` requires `--confirm-not-broadcast`. Do not use it if the PSBT may have been signed or broadcast outside Crakbit, because unlocking the inputs could make an external payment conflict with a later spend.

The inherited RPC parser exposes only `testnet4` and `regtest`. CRAK-018 is not a mainnet custody milestone.

## Flow

1. Create a mature CRAK-016 payout plan.
2. Build the funded unsigned PSBT with CRAK-017.
3. Run CRAK-018 `preflight` immediately before external signing/broadcast.
4. Sign and broadcast using operator-controlled wallet tooling.
5. Attach the resulting txid with CRAK-018 `guarded-attach` while the successful preflight is still fresh.
6. Continue CRAK-017 confirmation checking and settlement.

The lifecycle is therefore:

`planned -> psbt_ready -> [preflight audit] -> broadcast -> confirmed -> paid`

An abandoned unbroadcast PSBT may instead move:

`psbt_ready -> cancelled`

with linked canonical credits released back to `pending` and orphaned credits kept `orphaned`.

## Commands

Preflight:

```bash
crakpool-payguard --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  preflight --network testnet4 --wallet pool --batch <BATCH_ID> \
  --max-fee-sats <MAX_FEE_SATS>
```

Guarded txid attachment after external signing/broadcast:

```bash
crakpool-payguard --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  guarded-attach --batch <BATCH_ID> --txid <TXID>
```

The default successful-preflight freshness window is 900 seconds and can be changed with `--preflight-max-age`.

Cancel an abandoned PSBT only after verifying it was never signed or broadcast:

```bash
crakpool-payguard --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  cancel --network testnet4 --wallet pool --batch <BATCH_ID> \
  --confirm-not-broadcast
```

Inspect the current payment and latest preflight audit:

```bash
crakpool-payguard --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  status --batch <BATCH_ID>
```
