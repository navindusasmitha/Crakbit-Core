# WAM -> Crakbit derivation map

Crakbit uses WAM Coin as an engineering upstream, not as a network clone. WAM's source is MIT licensed; inherited copyright and license notices must remain intact.

## Why use it

WAM already demonstrates the difficult integration points needed by this project: a Bitcoin Core fork, custom CPU PoW, a separate SHA256d block ID and PoW hash, per-block DGW v3 retargeting, genesis tooling, miner, Stratum pool, explorer, install workflow and an auditable patch series.

## Consensus mapping

| WAM rule | Crakbit rule |
|---|---|
| Bitcoin Core v28.1 base | retain initially |
| RandomX PoW | replace with yespower 1.0 (`N=2048`, `r=8`) |
| SHA256d block ID + separate PoW hash | retain architecture |
| DGW v3, every block | retain; retune/test for 60s target |
| 120 second target | 60 seconds |
| 50 WAM subsidy | 5 CRAK |
| 200,000 block halving | 2,100,000 blocks |
| 22M hard ceiling | 21M hard ceiling |
| 2M spendable genesis reserve | remove; 0 premine |
| 5% treasury to height 400,000 | remove entirely |
| WAM mainnet/testnet IDs | replace entirely |
| `wamd` / `wam-cli` | `crakbitd` / `crakbit-cli` |
| WAM RandomX RPCs | remove/replace with Crakbit PoW info RPC |

## Patch order

1. Fetch WAM `v0.1.9` and record the exact commit SHA.
2. Preserve WAM/Bitcoin license history and patch metadata.
3. Rename user-facing binaries/config/data directories to Crakbit.
4. Remove founder reserve, vesting and spendable-genesis changes.
5. Remove mandatory treasury consensus validation and treasury RPC/pool logic.
6. Set `MAX_MONEY` and subsidy schedule for 21M / 5 CRAK / 2.1M blocks.
7. Replace RandomX hash integration with pinned Openwall yespower.
8. Keep SHA256d block IDs; use yespower only for PoW target comparison.
9. Retain DGW v3 and change target spacing to 60 seconds; add vectors.
10. Replace every WAM network identity value and DNS seed.
11. Replace miner/pool PoW implementation with yespower.
12. Generate a brand-new Crakbit testnet genesis and run multi-node tests.

## Hard rejection checks

A Crakbit build must fail CI if it still contains active WAM mainnet values such as ports `9555/9554`, message magic `57414d21`, Bech32 HRP `wam`, WAM genesis hashes, a nonzero founder allocation, or a consensus treasury percentage.

The migration should remove obsolete consensus code paths, not hide them behind runtime flags.
