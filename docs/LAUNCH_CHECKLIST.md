# Crakbit launch checklist

Mainnet stays disabled until every required item below is complete. The purpose of this file is to make irreversible consensus decisions explicit before block 1 exists.

## Phase A — source and policy

- [ ] `python3 scripts/verify-lock.py` passes.
- [ ] `python3 scripts/verify-address-prefixes.py` passes.
- [ ] `python3 scripts/verify_supply.py --schedule` prints terminal issuance `20,999,999.72700000 CRAK` and never exceeds 21M.
- [ ] Premine is exactly zero.
- [ ] Treasury/dev fee is exactly zero.
- [ ] WAM founder reserve, vesting and mandatory treasury validation paths are absent, not merely disabled by runtime flags.
- [ ] inherited WAM/Bitcoin/yespower copyright and license notices are preserved.

## Phase B — serialization and consensus integration

- [ ] `python3 genesis/test_serialization.py` reproduces Bitcoin's reference genesis hashes.
- [ ] yespower reference vectors pass on x86-64 and ARM64.
- [ ] Crakbit 80-byte-header yespower vectors are committed and pass.
- [ ] SHA256d remains the block identifier; yespower is used only for proof-of-work target comparison.
- [ ] DGW3 retargets every block using the 60-second target.
- [ ] difficulty tests cover stable hashrate, sudden +10x/-10x hashrate, timestamp bounds, target clamps and overflow/underflow cases.
- [ ] block subsidy tests cover every halving boundary and terminal zero subsidy.

## Phase C — network identity

- [ ] No WAM message magic, ports, HRP, address prefixes, genesis hashes, checkpoints or DNS seeds remain active.
- [ ] testnet message start is unique.
- [ ] testnet P2P/RPC ports are unique.
- [ ] testnet address prefixes and Bech32 HRP are verified.
- [ ] a brand-new Crakbit testnet genesis is mined and hard-coded.
- [ ] mainnet identity fields remain unset.

## Phase D — system tests

- [ ] daemon and CLI compile cleanly in release mode.
- [ ] inherited Bitcoin unit/functional tests affected by the fork pass.
- [ ] Crakbit consensus unit tests pass.
- [ ] wallet create/backup/restore/send/receive/restart tests pass.
- [ ] three independent nodes reach and maintain the same chain tip.
- [ ] intentional reorg tests converge correctly.
- [ ] solo CPU mining works with 1 thread and multiple threads.
- [ ] Stratum pool submits valid blocks and rejects invalid templates.
- [ ] explorer follows the same chain and supply values as RPC.
- [ ] 48+ hour sustained public testnet run completes without consensus divergence.

## Phase E — only then consider mainnet

- [ ] freeze monetary and difficulty constants.
- [ ] choose new mainnet message magic, ports, address prefixes and HRP.
- [ ] generate mainnet genesis only after the final reviewed binary is reproducible.
- [ ] publish source, checksums and launch parameters before block 1.
- [ ] start multiple independent seed/full nodes before inviting miners.

If any item changes after genesis generation but before block 1, discard that genesis and generate a new one. After block 1 exists, consensus changes require an explicit network upgrade process.
