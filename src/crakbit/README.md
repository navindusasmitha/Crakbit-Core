# Crakbit consensus overlay

This directory contains Crakbit-owned consensus constants and the smallest possible set of source files needed to make the pinned engineering base behave as Crakbit.

Design rules:

- keep inherited Bitcoin networking, UTXO, script and wallet code where practical;
- keep SHA256d as the block identifier;
- use yespower only for the proof-of-work target comparison;
- no founder reserve, premine, treasury or spendable-genesis allocation;
- retarget with DGW3 using a 60-second target;
- keep all mainnet identity values unset until testnet gates pass;
- fail migration checks if active legacy network identity or founder/treasury rules remain.

`crakbit-params.h` is the canonical C++ constant set. `consensus/params.json` is the machine-readable engineering specification and must agree with it.
