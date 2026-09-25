#!/usr/bin/env python3
"""Apply CRAK-001/002 to the pinned disposable Crakbit source tree.

CRAK-001 removes inherited founder/premine economics.
CRAK-002 removes inherited treasury/dev-fee economics.

The transform is intentionally strict and idempotent: expected source anchors
must exist, otherwise it aborts instead of guessing at consensus code.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREE = ROOT / ".work" / "crakbit-source"


class PatchError(RuntimeError):
    pass


def read(path: Path) -> str:
    if not path.exists():
        raise PatchError(f"missing expected source file: {path}")
    return path.read_text(encoding="utf-8")


def write_if_changed(path: Path, old: str, new: str) -> bool:
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def replace_anchor(text: str, old: str, new: str, label: str, *, expected: int = 1) -> str:
    old_count = text.count(old)
    new_count = text.count(new)
    if old_count == expected:
        return text.replace(old, new, expected)
    if old_count == 0 and new_count >= expected:
        return text  # already patched
    raise PatchError(f"{label}: expected {expected} source anchor(s), found {old_count}; patched={new_count}")


def replace_regex(text: str, pattern: str, replacement: str, label: str, *, minimum: int = 1) -> str:
    out, count = re.subn(pattern, replacement, text, flags=re.M)
    if count >= minimum:
        return out
    # Idempotence: if replacement already appears enough times, accept.
    if out.count(replacement) >= minimum or text.count(replacement) >= minimum:
        return text
    raise PatchError(f"{label}: no expected source anchors matched")


def replace_function_body(text: str, return_prefix: str, name: str, body: str) -> str:
    """Replace a unique C++ free-function body while preserving its signature."""
    pattern = re.compile(rf"(?m)^\s*{re.escape(return_prefix)}\s+{re.escape(name)}\s*\(")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise PatchError(f"{name}: expected one function definition candidate, found {len(matches)}")
    start = matches[0].start()
    open_brace = text.find("{", matches[0].end())
    if open_brace < 0:
        raise PatchError(f"{name}: opening brace not found")
    # Reject a prototype accidentally matched before the body.
    semicolon = text.find(";", matches[0].end(), open_brace)
    if semicolon >= 0:
        raise PatchError(f"{name}: matched a declaration instead of a definition")
    depth = 0
    i = open_brace
    in_string = False
    quote = ""
    escape = False
    line_comment = False
    block_comment = False
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if line_comment:
            if c == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if c == "*" and n == "/":
                block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
            i += 1
            continue
        if c == "/" and n == "/":
            line_comment = True
            i += 2
            continue
        if c == "/" and n == "*":
            block_comment = True
            i += 2
            continue
        if c in ('"', "'"):
            in_string = True
            quote = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                close_brace = i
                replacement = "{\n" + body.rstrip() + "\n}"
                return text[:open_brace] + replacement + text[close_brace + 1:]
        i += 1
    raise PatchError(f"{name}: unterminated function body")


def patch_params(tree: Path) -> int:
    path = tree / "src/wam/wam-params.h"
    src = read(path)
    out = src
    out = replace_regex(out, r"^(\s*inline\s+constexpr\s+CAmount\s+WAM_GENESIS_PREMINE\s*=\s*).+?;\s*$", r"\g<1>0;", "genesis premine constant")
    out = replace_regex(out, r"^(\s*inline\s+constexpr\s+int\s+WAM_DEVFEE_PERCENT\s*=\s*).+?;\s*$", r"\g<1>0;", "dev fee percent")
    out = replace_regex(out, r"^(\s*inline\s+constexpr\s+CAmount\s+WAM_PREMINE_TRANCHE_AMOUNT\s*=\s*).+?;\s*$", r"\g<1>0;", "premine tranche amount")
    return int(write_if_changed(path, src, out))


def patch_subsidy(tree: Path) -> int:
    path = tree / "src/wam/consensus/subsidy.cpp"
    src = read(path)
    out = src
    out = replace_anchor(out, "if (nHeight == 0) return WAM_GENESIS_PREMINE;", "if (nHeight == 0) return 0;", "height-zero premine")
    out = replace_function_body(out, "bool", "IsDevFeeActive", "    return false;")
    out = replace_function_body(out, "CAmount", "GetDevFeeAmount", "    return 0;")
    out = replace_function_body(out, "CAmount", "GetMinerSubsidy", "    return nSubsidy;")
    out = replace_function_body(out, "CAmount", "GetLifetimeDevFee", "    return 0;")
    out = replace_function_body(out, "CAmount", "GetVestedPremine", "    return 0;")
    out = replace_anchor(out, "CAmount total = WAM_GENESIS_PREMINE;", "CAmount total = 0;", "supply premine baseline")
    return int(write_if_changed(path, src, out))


def patch_devfee(tree: Path) -> int:
    path = tree / "src/wam/consensus/devfee.cpp"
    src = read(path)
    out = src
    out = replace_function_body(out, "const CScript&", "DevFeeScript", "    static const CScript empty;\n    return empty;")
    out = replace_function_body(out, "CAmount", "GetPaidDevFee", "    return 0;")
    out = replace_function_body(out, "bool", "CheckDevFeeOutput", "    return true;")
    return int(write_if_changed(path, src, out))


def patch_chainparams(tree: Path) -> int:
    path = tree / "src/wam/chainparams.cpp"
    src = read(path)
    out = src
    substitutions = [
        (r"^(\s*consensus\.nGenesisPremine\s*=\s*)WAM_GENESIS_PREMINE;\s*$", r"\g<1>0;", "chainparams premine"),
        (r"^(\s*consensus\.nDevFeePercent\s*=\s*)WAM_DEVFEE_PERCENT;\s*$", r"\g<1>0;", "chainparams dev fee percent"),
        (r"^(\s*consensus\.nDevFeeStartHeight\s*=\s*)WAM_DEVFEE_START_HEIGHT;\s*$", r"\g<1>0;", "chainparams dev fee start"),
        (r"^(\s*consensus\.nDevFeeLastHeight\s*=\s*)WAM_DEVFEE_LAST_HEIGHT;\s*$", r"\g<1>0;", "chainparams dev fee end"),
        (r"^\s*consensus\.devFeeAddress\s*=\s*WAM_TREASURY_ADDRESS_[A-Z0-9_]+;\s*$", "        consensus.devFeeAddress.clear();", "chainparams treasury address"),
    ]
    for pattern, repl, label in substitutions:
        out = replace_regex(out, pattern, repl, label)
    return int(write_if_changed(path, src, out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = args.tree.resolve()
    if not (tree / "src/wam/chainparams.cpp").exists():
        raise SystemExit(f"not the expected pinned base source tree: {tree}")

    changed = 0
    changed += patch_params(tree)
    changed += patch_subsidy(tree)
    changed += patch_devfee(tree)
    changed += patch_chainparams(tree)

    marker = tree / ".crakbit-economics"
    marker.write_text("CRAK-001=applied\nCRAK-002=applied\npremine=0\ntreasury=0\n", encoding="utf-8")
    print(f"CRAK-001/002 economics patch: PASS (changed_files={changed})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        raise SystemExit(f"economics patch failed: {exc}")
