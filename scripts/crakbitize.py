#!/usr/bin/env python3
"""Convert a freshly WAM-patched Bitcoin Core v28.1 tree into Crakbit.

This is intentionally a second, narrow transformation layer instead of editing
WAM's large historical patcher in-place. Every consensus-visible replacement
below is anchored and must match the expected WAM v0.1.9 generated source.
Unexpected source aborts the migration rather than guessing.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


class MigrationError(RuntimeError):
    pass


class Tree:
    def __init__(self, root: pathlib.Path):
        self.root = root

    def path(self, rel: str) -> pathlib.Path:
        p = self.root / rel
        if not p.exists():
            raise MigrationError(f"missing generated source: {rel}")
        return p

    def replace_once(self, rel: str, old: str, new: str, label: str) -> None:
        p = self.path(rel)
        text = p.read_text(encoding="utf-8")
        count = text.count(old)
        if count != 1:
            raise MigrationError(f"{rel}: {label}: expected one anchor, found {count}")
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"  edit {rel}: {label}")

    def regex(self, rel: str, pattern: str, repl: str, expected: int, label: str) -> None:
        p = self.path(rel)
        text = p.read_text(encoding="utf-8")
        out, n = re.subn(pattern, repl, text, flags=re.MULTILINE)
        if n != expected:
            raise MigrationError(f"{rel}: {label}: expected {expected} matches, found {n}")
        p.write_text(out, encoding="utf-8")
        print(f"  edit {rel}: {label} ({n})")


def migrate(tree: Tree) -> None:
    # ------------------------------------------------------------------
    # Monetary hard cap. WAM's patcher writes this literal into amount.h.
    # ------------------------------------------------------------------
    tree.replace_once(
        "src/consensus/amount.h",
        "static constexpr CAmount MAX_MONEY = 22000000 * COIN;",
        "static constexpr CAmount MAX_MONEY = 21000000 * COIN;",
        "22M WAM hard cap -> 21M CRAK",
    )

    cp = "src/kernel/chainparams.cpp"

    # The migration header sets the genesis premine to zero. Avoid carrying a
    # WAM founder address in block 0 even as a zero-valued output: use one
    # zero-valued OP_TRUE output until the final Crakbit genesis is mined.
    tree.replace_once(
        cp,
        "BuildGenesisOutputs(WAM_FOUNDER_ADDRESS_MAINNET)",
        "SingleGenesisOutput(CScript() << OP_TRUE)",
        "mainnet genesis has no founder output",
    )
    tree.replace_once(
        cp,
        "BuildGenesisOutputs(WAM_FOUNDER_ADDRESS_TESTNET)",
        "SingleGenesisOutput(CScript() << OP_TRUE)",
        "testnet genesis has no founder output",
    )

    # Old WAM hashes necessarily stop matching after the phrase/economics
    # change. During migration the genesis remains deterministic because every
    # field is compiled into chainparams, but the old assertions must not claim
    # it is WAM's block. Final Crakbit testnet hashes are re-added after the
    # yespower genesis miner fixes the nonce.
    tree.regex(
        cp,
        r'^\s*assert\(consensus\.hashGenesisBlock == uint256S\("0x[0-9a-f]+"\)\);\s*$',
        "        // CRAKBIT_MIGRATION: final genesis hash assertion pending yespower mining",
        3,
        "remove three obsolete WAM genesis-hash assertions",
    )
    tree.regex(
        cp,
        r'^\s*assert\(genesis\.hashMerkleRoot\s*== uint256S\("0x[0-9a-f]+"\)\);\s*$',
        "        // CRAKBIT_MIGRATION: final merkle assertion pending genesis freeze",
        3,
        "remove three obsolete WAM merkle assertions",
    )

    # Testnet must not inherit WAM's accumulated minimum chain work. A nonzero
    # WAM value would make a brand-new Crakbit chain impossible to sync.
    tree.regex(
        cp,
        r'consensus\.nMinimumChainWork = uint256S\("00000000000000000000000000000000000000000000000000000001852b0ce7"\);',
        'consensus.nMinimumChainWork = uint256{};',
        1,
        "reset WAM testnet minimum chain work",
    )

    # Crakbit testnet network identity. `CRAK` on the wire is intentionally
    # different from every WAM magic. Test addresses use standard test prefixes
    # so they cannot be confused with future C/c mainnet addresses.
    tree.replace_once(cp,
        "        pchMessageStart[0] = 0x77; // 'w'\n"
        "        pchMessageStart[1] = 0x61; // 'a'\n"
        "        pchMessageStart[2] = 0x6d; // 'm'\n"
        "        pchMessageStart[3] = 0x21; // '!'",
        "        pchMessageStart[0] = 0x43; // 'C'\n"
        "        pchMessageStart[1] = 0x52; // 'R'\n"
        "        pchMessageStart[2] = 0x41; // 'A'\n"
        "        pchMessageStart[3] = 0x4b; // 'K'",
        "testnet P2P magic WAM -> CRAK")

    tree.replace_once(cp,
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 65);  // 'T'\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 128); // 't'\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 239); // 'c'",
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 111);\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 196);\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 239);",
        "testnet address versions")
    tree.replace_once(cp, '        bech32_hrp = "twam";', '        bech32_hrp = "tcrak";',
                      "testnet bech32 HRP")

    # No WAM peer discovery may survive into a Crakbit testnet binary.
    tree.replace_once(cp,
        "        vFixedSeeds = std::vector<uint8_t>(std::begin(chainparams_seed_test),\n"
        "                                           std::end(chainparams_seed_test));\n"
        "        vSeeds.clear();\n"
        "        vSeeds.emplace_back(\"testnet-seed.wamcoin.org.\");",
        "        vFixedSeeds.clear();\n"
        "        vSeeds.clear();\n"
        "        // Crakbit v0.1 has no hard-coded public seed until independent nodes exist.",
        "remove WAM testnet seeds")

    # Mainnet is not launchable yet, but its compiled identity must still not
    # contact WAM if an operator selects it accidentally.
    tree.regex(cp, r'\s*vSeeds\.emplace_back\("seed[123]\.wamcoin\.org\."\);', '', 3,
               "remove WAM mainnet DNS seeds")
    tree.replace_once(cp,
        "        vFixedSeeds = std::vector<uint8_t>(std::begin(chainparams_seed_main),\n"
        "                                           std::end(chainparams_seed_main));",
        "        vFixedSeeds.clear();",
        "remove WAM mainnet fixed seeds")
    tree.replace_once(cp, '        bech32_hrp = "wam";', '        bech32_hrp = "crak";',
                      "mainnet bech32 HRP reservation")

    # WAM's patcher hard-codes RPC numbers in chainparamsbase.cpp rather than
    # reading wam-params.h. Use p2p-1; p2p+1 is Core's onion listener.
    base = "src/chainparamsbase.cpp"
    rpc_pairs = {
        'CBaseChainParams>("", 9554)': 'CBaseChainParams>("", 17774)',
        'CBaseChainParams>("testnet3", 19554)': 'CBaseChainParams>("testnet3", 17770)',
        'CBaseChainParams>("regtest", 29554)': 'CBaseChainParams>("regtest", 17780)',
        'CBaseChainParams>("signet", 39554)': 'CBaseChainParams>("signet", 17790)',
        'CBaseChainParams>("testnet4", 49554)': 'CBaseChainParams>("testnet4", 17792)',
    }
    for old, new in rpc_pairs.items():
        tree.replace_once(base, old, new, f"RPC port {old.split(', ')[-1][:-1]} -> {new.split(', ')[-1][:-1]}")

    # User-facing cryptographic identity. Internal `wam` namespace names stay
    # during the migration, but peers and signed messages must say Crakbit.
    tree.replace_once("src/clientversion.cpp", 'const std::string CLIENT_NAME("WAM");',
                      'const std::string CLIENT_NAME("Crakbit");', "P2P user-agent name")
    tree.replace_once("src/common/signmessage.cpp",
                      'const std::string MESSAGE_MAGIC = "WAM Coin Signed Message:\\n";',
                      'const std::string MESSAGE_MAGIC = "Crakbit Signed Message:\\n";',
                      "signed-message domain separation")
    tree.replace_once("src/clientversion.cpp",
                      'https://github.com/wam-coin-official/wam-coin',
                      'https://github.com/navindusasmitha/Crakbit-Core',
                      "source-code URL")

    # Mark generated tree so a build script can refuse an unconverted WAM tree.
    (tree.root / ".crakbit-migrated").write_text(
        "source=WAM-v0.1.9\npow=yespower-1.0-N2048-r8\nmainnet=disabled\n",
        encoding="utf-8",
    )


def check(tree: Tree) -> None:
    required = [
        tree.root / ".crakbit-migrated",
        tree.root / "src" / "wam" / "crypto" / "randomx_hash.cpp",
    ]
    for p in required:
        if not p.exists():
            raise MigrationError(f"missing migration output: {p}")

    whole = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in [
            tree.path("src/kernel/chainparams.cpp"),
            tree.path("src/consensus/amount.h"),
            tree.path("src/common/signmessage.cpp"),
        ]
    )
    forbidden = [
        "testnet-seed.wamcoin.org",
        "seed1.wamcoin.org",
        "seed2.wamcoin.org",
        "seed3.wamcoin.org",
        "22000000 * COIN",
        'bech32_hrp = "twam"',
        'MESSAGE_MAGIC = "WAM Coin Signed Message:',
    ]
    bad = [x for x in forbidden if x in whole]
    if bad:
        raise MigrationError("forbidden WAM identity/economics remain: " + ", ".join(bad))

    print("Crakbit generated-source migration checks: OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True, type=pathlib.Path)
    ap.add_argument("--check", action="store_true")
    ns = ap.parse_args()

    try:
        tree = Tree(ns.tree.resolve())
        if ns.check:
            check(tree)
        else:
            migrate(tree)
            check(tree)
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
