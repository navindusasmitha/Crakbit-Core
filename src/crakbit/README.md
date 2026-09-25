# Crakbit consensus overlay

This directory contains the Crakbit-owned consensus constants and, as the migration progresses, the smallest possible set of source files needed to make the pinned WAM/Bitcoin Core tree behave as Crakbit.

Design rules:

- keep inherited Bitcoin/WAM networking, UTXO, script and wallet code upstream;
- keep SHA256d as the block identifier;
- use yespower only for the proof-of-work target comparison;
- no founder reserve, premine, treasury or spendable-genesis allocation;
- retarget with DGW3 using a 60-second target;
- keep all mainnet identity values unset until testnet gates pass;
- fail migration checks if active WAM network identity or treasury/founder rules remain.

`crakbit-params.h` is the canonical C++ constant set. `consensus/params.json` is the machine-readable engineering specification and must agree with it.
