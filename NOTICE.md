# Source and attribution notice

Crakbit Core is a derivative blockchain engineering project.

The testnet-v0.1 source materialization process uses the MIT-licensed WAM Coin repository as a pinned engineering reference and inherits its pinned Bitcoin Core and RandomX source dependencies. The exact WAM reference commit is recorded in `SOURCE_LOCK.json`.

Upstream projects:

- Bitcoin Core — https://github.com/bitcoin/bitcoin — MIT license.
- WAM Coin — https://github.com/wam-coin-official/wam-coin — MIT license.
- RandomX — https://github.com/tevador/RandomX — BSD-3-Clause license.

Crakbit-specific consensus parameters, testnet identity, build wrappers, operating scripts and documentation in this repository are maintained separately from those upstream projects. Use of upstream code or naming in compatibility internals does not imply endorsement by those projects.

Before a Crakbit mainnet release, the release bundle must include all licenses/notices required by every redistributed dependency and a machine-verifiable source manifest.
