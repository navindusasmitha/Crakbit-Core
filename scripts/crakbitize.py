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

    def replace_exact(self, rel: str, old: str, new: str, expected: int, label: str) -> None:
        p = self.path(rel)
        text = p.read_text(encoding="utf-8")
        count = text.count(old)
        if count != expected:
            raise MigrationError(f"{rel}: {label}: expected {expected} anchors, found {count}")
        p.write_text(text.replace(old, new), encoding="utf-8")
        print(f"  edit {rel}: {label} ({count})")

    def replace_once(self, rel: str, old: str, new: str, label: str) -> None:
        self.replace_exact(rel, old, new, 1, label)

    def regex(self, rel: str, pattern: str, repl: str, expected: int, label: str) -> None:
        p = self.path(rel)
        text = p.read_text(encoding="utf-8")
        out, n = re.subn(pattern, repl, text, flags=re.MULTILINE)
        if n != expected:
            raise MigrationError(f"{rel}: {label}: expected {expected} matches, found {n}")
        p.write_text(out, encoding="utf-8")
        print(f"  edit {rel}: {label} ({n})")


def migrate(tree: Tree) -> None:
    # Monetary hard cap. WAM's patcher writes this literal into amount.h.
    tree.replace_once(
        "src/consensus/amount.h",
        "static constexpr CAmount MAX_MONEY = 22000000 * COIN;",
        "static constexpr CAmount MAX_MONEY = 21000000 * COIN;",
        "22M WAM hard cap -> 21M CRAK",
    )

    cp = "src/kernel/chainparams.cpp"

    # Crakbit has no founder reserve. WAM uses the same testnet founder helper
    # in BOTH testnet and regtest, so the exact expected count is two. Requiring
    # exactly two preserves the fail-closed property while fixing run #1's
    # correct refusal to guess which occurrence was intended.
    tree.replace_once(
        cp,
        "BuildGenesisOutputs(WAM_FOUNDER_ADDRESS_MAINNET)",
        "SingleGenesisOutput(CScript() << OP_TRUE)",
        "mainnet genesis has no founder output",
    )
    tree.replace_exact(
        cp,
        "BuildGenesisOutputs(WAM_FOUNDER_ADDRESS_TESTNET)",
        "SingleGenesisOutput(CScript() << OP_TRUE)",
        2,
        "testnet/regtest genesis have no founder outputs",
    )

    # Old WAM hashes necessarily stop matching after phrase/economics changes.
    # Final Crakbit values are restored as assertions after the yespower genesis
    # miner fixes each network's nonce.
    tree.regex(
        cp,
        r'^\s*assert\(consensus\.hashGenesisBlock == uint256S\("0x[0-9a-f]+"\)\);\s*$',
        "        // CRAKBIT_MIGRATION: final genesis hash assertion pending yespower mining",
        3,
        "remove obsolete WAM genesis-hash assertions",
    )
    tree.regex(
        cp,
        r'^\s*assert\(genesis\.hashMerkleRoot\s*== uint256S\("0x[0-9a-f]+"\)\);\s*$',
        "        // CRAKBIT_MIGRATION: final merkle assertion pending genesis freeze",
        3,
        "remove obsolete WAM merkle assertions",
    )

    # A new chain must not inherit either WAM network's accumulated work floor.
    tree.replace_once(
        cp,
        'consensus.nMinimumChainWork = uint256S("0000000000000000000000000000000000000000000000000000002adc39e008");',
        'consensus.nMinimumChainWork = uint256{};',
        "reset WAM mainnet minimum chain work",
    )
    tree.replace_once(
        cp,
        'consensus.nMinimumChainWork = uint256S("00000000000000000000000000000000000000000000000000000001852b0ce7");',
        'consensus.nMinimumChainWork = uint256{};',
        "reset WAM testnet minimum chain work",
    )

    # ------------------------------------------------------------------
    # Network identity: no Crakbit mode may handshake with WAM by accident.
    # ------------------------------------------------------------------
    tree.replace_once(
        cp,
        "        pchMessageStart[0] = 0x57; // 'W'\n"
        "        pchMessageStart[1] = 0x41; // 'A'\n"
        "        pchMessageStart[2] = 0x4d; // 'M'\n"
        "        pchMessageStart[3] = 0x21; // '!'",
        "        pchMessageStart[0] = 0x43; // 'C'\n"
        "        pchMessageStart[1] = 0x52; // 'R'\n"
        "        pchMessageStart[2] = 0x4b; // 'K'\n"
        "        pchMessageStart[3] = 0x21; // '!'",
        "mainnet P2P magic WAM! -> CRK!",
    )
    tree.replace_once(
        cp,
        "        pchMessageStart[0] = 0x77; // 'w'\n"
        "        pchMessageStart[1] = 0x61; // 'a'\n"
        "        pchMessageStart[2] = 0x6d; // 'm'\n"
        "        pchMessageStart[3] = 0x21; // '!'",
        "        pchMessageStart[0] = 0x43; // 'C'\n"
        "        pchMessageStart[1] = 0x52; // 'R'\n"
        "        pchMessageStart[2] = 0x41; // 'A'\n"
        "        pchMessageStart[3] = 0x4b; // 'K'",
        "testnet P2P magic wam! -> CRAK",
    )
    tree.replace_once(
        cp,
        "        pchMessageStart[0] = 0x57;\n"
        "        pchMessageStart[1] = 0x41;\n"
        "        pchMessageStart[2] = 0x4d;\n"
        "        pchMessageStart[3] = 0x52; // 'R'",
        "        pchMessageStart[0] = 0x43;\n"
        "        pchMessageStart[1] = 0x52;\n"
        "        pchMessageStart[2] = 0x4b;\n"
        "        pchMessageStart[3] = 0x52; // 'R'",
        "regtest P2P magic WAMR -> CRKR",
    )

    # Reserved Crakbit mainnet legacy prefixes. Mainnet itself remains disabled.
    tree.replace_once(
        cp,
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 73);  // 'W'\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 135); // 'w'\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 190); // 'V' / '7'",
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 28);  // reserved C...\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 87);  // reserved c...\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 197);",
        "mainnet legacy address versions",
    )
    tree.replace_once(cp, '        bech32_hrp = "wam";', '        bech32_hrp = "crak";',
                      "mainnet bech32 HRP")

    # Testnet and regtest deliberately use Bitcoin-style test legacy versions,
    # but distinct Crakbit bech32 HRPs and P2P magic.
    tree.replace_exact(
        cp,
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 65);\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 128);\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 239);",
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 111);\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 196);\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 239);",
        1,
        "regtest legacy address versions",
    )
    tree.replace_once(
        cp,
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 65);  // 'T'\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 128); // 't'\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 239); // 'c'",
        "        base58Prefixes[PUBKEY_ADDRESS] = std::vector<unsigned char>(1, 111);\n"
        "        base58Prefixes[SCRIPT_ADDRESS] = std::vector<unsigned char>(1, 196);\n"
        "        base58Prefixes[SECRET_KEY]     = std::vector<unsigned char>(1, 239);",
        "testnet legacy address versions",
    )
    tree.replace_once(cp, '        bech32_hrp = "twam";', '        bech32_hrp = "tcrak";',
                      "testnet bech32 HRP")
    tree.replace_once(cp, '        bech32_hrp = "wamrt";', '        bech32_hrp = "rcrak";',
                      "regtest bech32 HRP")

    # No WAM peer discovery may survive into a Crakbit binary.
    tree.replace_once(
        cp,
        "        vFixedSeeds = std::vector<uint8_t>(std::begin(chainparams_seed_test),\n"
        "                                           std::end(chainparams_seed_test));\n"
        "        vSeeds.clear();\n"
        "        vSeeds.emplace_back(\"testnet-seed.wamcoin.org.\");",
        "        vFixedSeeds.clear();\n"
        "        vSeeds.clear();\n"
        "        // Crakbit v0.1 has no hard-coded public seed until independent nodes exist.",
        "remove WAM testnet seeds",
    )
    tree.regex(cp, r'\s*vSeeds\.emplace_back\("seed[123]\.wamcoin\.org\."\);', '', 3,
               "remove WAM mainnet DNS seeds")
    tree.replace_once(
        cp,
        "        vFixedSeeds = std::vector<uint8_t>(std::begin(chainparams_seed_main),\n"
        "                                           std::end(chainparams_seed_main));",
        "        vFixedSeeds.clear();",
        "remove WAM mainnet fixed seeds",
    )

    # WAM hard-codes RPC numbers in chainparamsbase.cpp. Use p2p-1 because
    # Bitcoin Core reserves p2p+1 for the Tor onion listener.
    base = "src/chainparamsbase.cpp"
    rpc_pairs = {
        'CBaseChainParams>("", 9554)': 'CBaseChainParams>("", 17774)',
        'CBaseChainParams>("testnet3", 19554)': 'CBaseChainParams>("testnet3", 17770)',
        'CBaseChainParams>("regtest", 29554)': 'CBaseChainParams>("regtest", 17780)',
        'CBaseChainParams>("signet", 39554)': 'CBaseChainParams>("signet", 17790)',
        'CBaseChainParams>("testnet4", 49554)': 'CBaseChainParams>("testnet4", 17792)',
    }
    for old, new in rpc_pairs.items():
        tree.replace_once(base, old, new, f"RPC port {old} -> {new}")

    # User-facing and cryptographic identity. Internal `wam` namespace names
    # remain temporarily so the inherited patch framework compiles.
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

    (tree.root / ".crakbit-migrated").write_text(
        "source=WAM-v0.1.9\npow=yespower-1.0-N2048-r8\nmainnet=disabled\n",
        encoding="utf-8",
    )


def check(tree: Tree) -> None:
    for p in [
        tree.root / ".crakbit-migrated",
        tree.root / "src" / "wam" / "crypto" / "randomx_hash.cpp",
    ]:
        if not p.exists():
            raise MigrationError(f"missing migration output: {p}")

    whole = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in [
            tree.path("src/kernel/chainparams.cpp"),
            tree.path("src/consensus/amount.h"),
            tree.path("src/common/signmessage.cpp"),
            tree.path("src/clientversion.cpp"),
        ]
    )
    forbidden = [
        "testnet-seed.wamcoin.org",
        "seed1.wamcoin.org",
        "seed2.wamcoin.org",
        "seed3.wamcoin.org",
        "22000000 * COIN",
        'bech32_hrp = "wam"',
        'bech32_hrp = "twam"',
        'bech32_hrp = "wamrt"',
        'MESSAGE_MAGIC = "WAM Coin Signed Message:',
        'CLIENT_NAME("WAM")',
        '2adc39e008',
        '01852b0ce7',
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
