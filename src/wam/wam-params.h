// Copyright (c) 2026 The WAM Coin developers
// Copyright (c) 2026 The Crakbit developers
// Distributed under the MIT software license, see COPYING.
//
// This header intentionally keeps the historical `wam::WAM_*` symbol names
// while the WAM-derived patch framework is being migrated.  The symbols below
// are Crakbit consensus parameters. Renaming the compatibility namespace is a
// later, non-consensus cleanup and must not be mixed with the PoW migration.

#ifndef WAM_WAM_PARAMS_H
#define WAM_WAM_PARAMS_H

#include <cstdint>

namespace wam {

// ---------------------------------------------------------------------------
// Crakbit monetary policy
// ---------------------------------------------------------------------------
static constexpr int64_t WAM_COIN = 100'000'000;
static constexpr int WAM_DECIMALS = 8;

static constexpr int64_t WAM_MAX_MONEY = 21'000'000 * WAM_COIN;
static constexpr int64_t WAM_GENESIS_PREMINE = 0;
static constexpr int64_t WAM_MINING_ALLOCATION = 21'000'000 * WAM_COIN;

static_assert(WAM_GENESIS_PREMINE + WAM_MINING_ALLOCATION == WAM_MAX_MONEY,
              "Crakbit premine + mining allocation must equal the hard cap");

static constexpr int64_t WAM_INITIAL_BLOCK_SUBSIDY = 5 * WAM_COIN;
static constexpr int WAM_SUBSIDY_HALVING_INTERVAL = 2'100'000;
static constexpr int WAM_MAX_HALVINGS = 29;
static_assert((WAM_INITIAL_BLOCK_SUBSIDY >> WAM_MAX_HALVINGS) == 0,
              "Crakbit subsidy must eventually reach zero");

// Crakbit has no mandatory treasury/dev output. These compatibility constants
// remain zero while the inherited WAM dev-fee API is removed from the build.
static constexpr int64_t WAM_DEVFEE_PERCENT = 0;
static constexpr int WAM_DEVFEE_START_HEIGHT = 0;
static constexpr int WAM_DEVFEE_LAST_HEIGHT = 0;

// BIP-44 migration value. 0x4352414B is ASCII "CRAK" and is deliberately not
// Bitcoin's 0 or the shared testnet value 1. Registration is still required
// before a production wallet can treat this as permanent.
static constexpr uint32_t WAM_BIP44_COIN_TYPE = 0x4352414B;
static_assert(WAM_BIP44_COIN_TYPE < 0x80000000,
              "BIP-44 coin type is the pre-hardened index");
static_assert(WAM_BIP44_COIN_TYPE != 0 && WAM_BIP44_COIN_TYPE != 1,
              "Crakbit must not use Bitcoin/testnet coin types");

// ---------------------------------------------------------------------------
// Genesis compatibility
// ---------------------------------------------------------------------------
// Mainnet remains disabled. Testnet starts from 25/Sep/2026 00:00:00 UTC.
static constexpr int64_t WAM_GENESIS_TIME = 1790294400;
static constexpr int64_t WAM_TESTNET_GENESIS_TIME = 1790294400;
static constexpr int64_t WAM_REGTEST_GENESIS_TIME = 1296688602;

// The WAM chainparams helper expects a tranche table. A single zero-valued
// entry preserves that API while minting exactly zero premine. Crakbit's final
// chainparams will replace the founder-output helper entirely.
static constexpr int WAM_PREMINE_TRANCHES = 1;
static constexpr int64_t WAM_PREMINE_TRANCHE_AMOUNT = 0;
static constexpr int64_t WAM_PREMINE_UNLOCK_TIMES[WAM_PREMINE_TRANCHES] = {0};
static_assert(WAM_PREMINE_TRANCHES * WAM_PREMINE_TRANCHE_AMOUNT == WAM_GENESIS_PREMINE,
              "Crakbit compatibility genesis outputs must mint zero coins");

// ---------------------------------------------------------------------------
// Timing and difficulty
// ---------------------------------------------------------------------------
static constexpr int64_t WAM_POW_TARGET_SPACING = 60;
static constexpr int64_t WAM_DGW_PAST_BLOCKS = 24;
static constexpr int64_t WAM_DGW_CLAMP_FACTOR = 3;
static constexpr int WAM_COINBASE_MATURITY = 100;

// Historical RandomX fields are kept only so the inherited WAM consensus
// structure still compiles during the migration. yespower has no seed epochs.
static constexpr int WAM_RANDOMX_EPOCH_BLOCKS = 1;
static constexpr int WAM_RANDOMX_EPOCH_LAG = 0;

// ---------------------------------------------------------------------------
// Network identity
// ---------------------------------------------------------------------------
// RPC uses p2p-1. Bitcoin Core reserves p2p+1 for its onion listener.
static constexpr int WAM_MAINNET_P2P_PORT = 17775;
static constexpr int WAM_MAINNET_RPC_PORT = 17774;
static constexpr int WAM_TESTNET_P2P_PORT = 17771;
static constexpr int WAM_TESTNET_RPC_PORT = 17770;
static constexpr int WAM_REGTEST_P2P_PORT = 17781;
static constexpr int WAM_REGTEST_RPC_PORT = 17780;

static_assert(WAM_MAINNET_RPC_PORT == WAM_MAINNET_P2P_PORT - 1
              && WAM_TESTNET_RPC_PORT == WAM_TESTNET_P2P_PORT - 1
              && WAM_REGTEST_RPC_PORT == WAM_REGTEST_P2P_PORT - 1,
              "Crakbit RPC must be p2p-1 because p2p+1 is reserved for onion");

static constexpr const char* WAM_GENESIS_TIMESTAMP_PHRASE =
    "Crakbit CPU Mining Network 25/Sep/2026";

// Kept only for source compatibility with the old RandomX API. yespower uses
// the fixed personalization string `Crakbit-Core-v0.1` instead of seed epochs.
static constexpr const char* WAM_RANDOMX_BOOTSTRAP_KEY =
    "Crakbit-Core-v0.1";

} // namespace wam

#endif // WAM_WAM_PARAMS_H
