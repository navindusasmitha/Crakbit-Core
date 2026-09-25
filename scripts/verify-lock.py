#!/usr/bin/env python3
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / 'SOURCE_LOCK.json').read_text(encoding='utf-8'))
params = json.loads((ROOT / 'consensus' / 'params.json').read_text(encoding='utf-8'))

sha40 = re.compile(r'^[0-9a-f]{40}$')
errors = []

base = lock['upstreams']['base_source']
base_sha = base.get('commit_sha', '')
if not sha40.fullmatch(base_sha):
    errors.append('base_source.commit_sha must be a 40-char lowercase git SHA')

bitcoin = lock['upstreams']['bitcoin_core']
bitcoin_sha = bitcoin.get('commit_sha', '')
if not sha40.fullmatch(bitcoin_sha):
    errors.append('bitcoin_core.commit_sha must be a 40-char lowercase git SHA')
if bitcoin.get('tag') != 'v28.1':
    errors.append(f"bitcoin_core.tag must remain v28.1 during this migration, got {bitcoin.get('tag')!r}")
if bitcoin_sha != '32efe850438ef22e2de39e562af557872a402c31':
    errors.append('bitcoin_core.commit_sha does not match the verified v28.1 release commit')

yes_sha = lock['upstreams']['yespower'].get('commit_sha', '')
if not sha40.fullmatch(yes_sha):
    errors.append('yespower commit_sha is not a 40-char lowercase git SHA')

pow_lock = lock['pow']
pow_params = params['proof_of_work']
for key in ('algorithm', 'version', 'N', 'r', 'personalization'):
    if pow_lock[key] != pow_params[key]:
        errors.append(f'PoW mismatch for {key}: SOURCE_LOCK={pow_lock[key]!r} params={pow_params[key]!r}')

if pow_params['algorithm'] != 'yespower' or pow_params['version'] != 'YESPOWER_1_0':
    errors.append('PoW must be yespower YESPOWER_1_0')
if pow_params['N'] != 2048 or pow_params['r'] != 8:
    errors.append('PoW parameters must be N=2048, r=8')
if pow_params['target_spacing_seconds'] != 60:
    errors.append('target block spacing must be 60 seconds')
if pow_params.get('block_id_hash') != 'SHA256d' or pow_params.get('pow_hash') != 'yespower':
    errors.append('Crakbit requires SHA256d block IDs with a separate yespower PoW hash')

money = params['money']
expected = {
    'initial_subsidy_coins': 5,
    'halving_interval_blocks': 2_100_000,
    'premine_coins': 0,
    'treasury_percent': 0,
    'coinbase_maturity_blocks': 100,
}
for key, value in expected.items():
    if money.get(key) != value:
        errors.append(f'{key} must be {value!r}, got {money.get(key)!r}')

ideal_supply = 2 * money['initial_subsidy_coins'] * money['halving_interval_blocks']
if ideal_supply != money['intended_max_supply_coins']:
    errors.append(f'intended supply mismatch: geometric target is {ideal_supply:,}')

if params['difficulty'].get('design') != 'DarkGravityWave-v3':
    errors.append('difficulty design must be DarkGravityWave-v3')

net = params['network_separation']['testnet']
forbidden_legacy = {
    'message_start_hex': '77616d21',
    'p2p_port': 19555,
    'rpc_port': 19554,
    'bech32_hrp': 'twam',
}
for key, forbidden in forbidden_legacy.items():
    if net.get(key) == forbidden:
        errors.append(f'testnet {key} still matches a legacy upstream identity and must be unique')

if lock.get('mainnet_enabled') or params.get('mainnet_enabled'):
    errors.append('mainnet must remain disabled during testnet migration')

if errors:
    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)
    raise SystemExit(1)

print('Crakbit source/consensus lock: OK')
