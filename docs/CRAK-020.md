# CRAK-020 payout end-to-end regtest reliability

CRAK-020 proves the complete CRAK-016 through CRAK-019 payout lifecycle on an isolated regtest node in CI.

This milestone is a reliability test, not a custody automation feature. The operator-facing payout commands remain testnet4/regtest only and CRAK-017/018 continue to require external/manual signing and broadcast in normal use.

## What the smoke proves

The CRAK-020 workflow performs the following sequence from a clean temporary regtest environment:

1. Start a wallet-enabled Crakbit regtest node.
2. Create pool and worker wallets.
3. Pre-fund the pool wallet with a separate coinbase for transaction fees.
4. Start the persistent accounting pool and mine one credited pool block.
5. Register the worker payout address.
6. Mine enough descendants for the credited pool block to satisfy the 100-confirmation maturity gate.
7. Create a CRAK-016 payout plan.
8. Build a funded unsigned CRAK-017 PSBT.
9. Run the CRAK-018 preflight and verify source maturity, exact recipient output, and fee cap.
10. Sign and broadcast the PSBT inside the isolated regtest CI only.
11. Attach the txid through CRAK-018 `guarded-attach`.
12. Confirm CRAK-019 reports the payment as waiting for confirmations.
13. Mine six confirmation blocks.
14. Refresh the payment through CRAK-019 and verify it becomes settlement-ready.
15. Settle through CRAK-017 with the six-confirmation gate.
16. Verify the payout batch is `paid`, the linked credit is paid, and the worker wallet received exactly 5 CRAK.

## Safety boundary

The automatic signing and broadcast step exists only inside `tests/payout_e2e_smoke.sh` on isolated `regtest` for CI verification.

CRAK-020 does **not** add a production or testnet automatic signer/broadcaster. Normal payout handling remains:

`plan -> build PSBT -> preflight -> external sign/broadcast -> guarded attach -> confirmations -> settle`

No mainnet mode is introduced.

## CI

The dedicated workflow is:

`.github/workflows/verify-payout-e2e.yml`

It builds the wallet node, CLI, and native scanner from the pinned/materialized Crakbit source tree, then runs:

```bash
bash tests/payout_e2e_smoke.sh .work/crakbit-build
```

The final success line includes the batch id, txid, confirmation gate result, paid state, and worker wallet balance.
