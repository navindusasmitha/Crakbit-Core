'use strict';
// Crakbit Core testnet-v0.1 pool consensus mirrors.
// Internal filenames remain compatible with the pinned WAM pool layer.

const COIN = 100000000;

module.exports = {
    COIN,
    SUBSIDY_HALVING_INTERVAL: 1051200,
    INITIAL_BLOCK_SUBSIDY_WAM: 10,
    MAX_HALVINGS: 30,
    MAX_MONEY_WAM: 21024000,
    GENESIS_PREMINE_WAM: 0,
    DEVFEE_PERCENT: 5,
    DEVFEE_LAST_HEIGHT: 400000,
    POW_TARGET_SPACING: 120,
    COINBASE_MATURITY: 100,

    // Pool follows production epoch values. Testnet GBT reports its active
    // network values and the testnet dashboard/config overrides to 256/16.
    RANDOMX_EPOCH_BLOCKS: 2048,
    RANDOMX_EPOCH_LAG: 64,
    RANDOMX_BOOTSTRAP_KEY: 'Crakbit/RandomX/testnet-v0.1/2026',
    RANDOMX_HASH_SIZE: 32,

    HEADER_SIZE: 80,
    EXTRANONCE1_SIZE: 4,
    EXTRANONCE2_SIZE: 4,
    DIFF1: BigInt('0x00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff'),

    // Testnet keeps the proven WAM test address-version bytes while using a
    // Crakbit-specific bech32 HRP. Mainnet address bytes are not frozen yet.
    ADDRESS_VERSIONS: {
        mainnet: { pubkey: 73, script: 135, firstChar: 'W', bech32: 'cbit' },
        testnet: { pubkey: 65, script: 128, firstChar: 'T', bech32: 'tcb' },
        regtest: { pubkey: 65, script: 128, firstChar: 'T', bech32: 'cbtrt' }
    }
};
