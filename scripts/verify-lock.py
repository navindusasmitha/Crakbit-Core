#!/usr/bin/env python3
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / 'SOURCE_LOCK.json').read_text(encoding='utf-8'))
params = json.loads((ROOT / 'consensus' / 'params.json').read_text(encoding='utf-8'))
vectors = json.loads((ROOT / 'tests' / 'yespower_vectors.json').read_text(encoding='utf-8'))

sha40 = re.compile(r'^[0-9a-f]{40}$')
errors = []

for name, entry in lock['upstreams'].items():
    sha = entry.get('commit_sha', '')
    if not sha40.fullmatch(sha):
        errors.append(f'{name}: commit_sha is not a 40-char lowercase git SHA')

pow_lock = lock['pow']
pow_params = params['proof_of_work']
for key in ('algorithm', 'version', 'N', 'r', 'personalization'):
    if pow_lock[key] != pow_params[key]:
        errors.append(f'PoW mismatch for {key}: SOURCE_LOCK={pow_lock[key]!r} params={pow_params[key]!r}')

if pow_params['algorithm'] != 'yespower' or pow_params['version'] != 'YESPOWER_1_0':
    errors.append('PoW must remain yespower YESPOWER_1_0 for v0.1')
if pow_params['N'] != 2048 or pow_params['r'] != 8:
    errors.append('v0.1 PoW parameters must remain N=2048, r=8')
if pow_params['target_spacing_seconds'] != 60:
    errors.append('target block spacing must be 60 seconds')

vector_profile = vectors.get('profile', {})
for key in ('algorithm', 'version', 'N', 'r', 'personalization'):
    if vector_profile.get(key) != pow_lock[key]:
        errors.append(
            f'vector profile mismatch for {key}: vectors={vector_profile.get(key)!r} '
            f'SOURCE_LOCK={pow_lock[key]!r}'
        )

vector_list = vectors.get('vectors', [])
if len(vector_list) != 1:
    errors.append('v0.1 must contain exactly one frozen sequential-header yespower vector')
else:
    vector = vector_list[0]
    try:
        input_bytes = bytes.fromhex(vector['input_hex'])
        raw_hash = bytes.fromhex(vector['raw_hash_hex'])
        display_hash = bytes.fromhex(vector['uint256_display_hex'])
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f'invalid yespower vector encoding: {exc}')
    else:
        if input_bytes != bytes(range(80)):
            errors.append('yespower vector input must be the exact 80-byte sequence 00..4f')
        if len(raw_hash) != 32:
            errors.append('yespower raw vector must be exactly 32 bytes')
        if len(display_hash) != 32:
            errors.append('yespower uint256 display vector must be exactly 32 bytes')
        if display_hash != raw_hash[::-1]:
            errors.append('uint256 display vector must be raw yespower bytes in reverse display order')

money = params['money']
if money['initial_subsidy_coins'] != 5:
    errors.append('initial subsidy must be 5 CRAK')
if money['halving_interval_blocks'] != 2_100_000:
    errors.append('halving interval must be 2,100,000 blocks')
if money['premine_coins'] != 0:
    errors.append('premine must be zero')
if money['coinbase_maturity_blocks'] != 100:
    errors.append('coinbase maturity must be 100 blocks')

ideal_supply = 2 * money['initial_subsidy_coins'] * money['halving_interval_blocks']
if ideal_supply != money['intended_max_supply_coins']:
    errors.append(f'intended supply mismatch: geometric target is {ideal_supply:,}')

if lock.get('mainnet_enabled') or params.get('mainnet_enabled'):
    errors.append('mainnet must remain disabled in v0.1 engineering base')

if errors:
    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)
    raise SystemExit(1)

print('Crakbit source/consensus/vector lock: OK')
