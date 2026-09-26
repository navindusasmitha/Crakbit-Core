# CRAK-019 payout operations monitor

CRAK-019 adds operator-facing payout observability on top of CRAK-017 and CRAK-018. It does not add automatic signing, transaction broadcast, or settlement.

## Goals

- Show every payout batch and its effective lifecycle state.
- Classify the next operator action from ledger state instead of requiring manual database inspection.
- Flag stale planned, PSBT-ready, broadcast, and under-confirmed payouts.
- Include latest CRAK-018 preflight context beside PSBT-ready payments.
- Summarize payout states, next actions, stale counts, and total planned satoshis.
- Provide an explicit one-batch confirmation refresh that reuses CRAK-017 recipient verification.

## Safety boundary

`crakpool-payops` never signs a PSBT, never broadcasts a transaction, and never settles credits automatically. `list`, `show`, and `summary` are read-only. `refresh` only calls the existing CRAK-017 confirmation-check path for a payment that already has an attached txid.

The inherited RPC parser remains limited to `testnet4` and `regtest`.

## Next-action classification

Typical actions are:

- `planned` -> `build_psbt`
- `psbt_ready` without a fresh valid preflight -> `run_preflight`
- `psbt_ready` with a fresh valid preflight -> `sign_broadcast_then_guarded_attach`
- `broadcast` -> `refresh_confirmations` or `wait_confirmations`
- `confirmed` below the confirmation gate -> `refresh_confirmations` or `wait_confirmations`
- `confirmed` at/above the gate -> `settle`
- `paid` / `cancelled` -> `none`
- invalid or unexpected states -> `manual_review`

The monitor does not execute those actions for the operator.

## Commands

Summary:

```bash
crakpool-payops --db ~/.crakbit/crakpool-testnet4.sqlite3 summary
```

List all payouts with next actions:

```bash
crakpool-payops --db ~/.crakbit/crakpool-testnet4.sqlite3 list
```

Filter one state:

```bash
crakpool-payops --db ~/.crakbit/crakpool-testnet4.sqlite3 list --state broadcast
```

Show one batch:

```bash
crakpool-payops --db ~/.crakbit/crakpool-testnet4.sqlite3 show --batch <BATCH_ID>
```

Explicitly refresh an already-broadcast payment:

```bash
crakpool-payops --db ~/.crakbit/crakpool-testnet4.sqlite3 \
  refresh --network testnet4 --wallet pool --batch <BATCH_ID>
```

Defaults:

- stale threshold: 3600 seconds
- settlement display gate: 6 confirmations
- CRAK-018 successful preflight freshness: 900 seconds

These values can be changed on the read-only monitor commands with `--stale-seconds`, `--confirmations`, and `--preflight-max-age`.
