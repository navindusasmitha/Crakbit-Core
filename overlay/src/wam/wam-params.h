// Crakbit Core testnet-v0.1 consensus constants.
//
// Compatibility note: the pinned WAM engineering layer expects the namespace
// and WAM_* identifiers below. During testnet we retain those INTERNAL names
// while replacing the values with Crakbit consensus. They are not WAM network
// parameters. A full internal rename is a pre-mainnet gate.

#ifndef WAM_WAM_PARAMS_H
#define WAM_WAM_PARAMS_H

#include <cstdint>

namespace wam {

// Base units
static constexpr int64_t WAM_COIN = 100'000'000;
static constexpr int WAM_DECIMALS = 8;

// Supply. This is a strict sanity ceiling. Integer right-shift rounding makes
// actual scheduled subsidy emission slightly smaller: 21,023,999.86334400 CBIT.
static constexpr int64_t WAM_MAX_MONEY = 21'024'000 * WAM_COIN;
static constexpr int64_t WAM_GENESIS_PREMINE = 0;
static constexpr int64_t WAM_MINING_ALLOCATION = WAM_MAX_MONEY;
static_assert(WAM_GENESIS_PREMINE + WAM_MINING_ALLOCATION == WAM_MAX_MONEY,
              "genesis allocation + mining ceiling must equal max money");

// Emission
static constexpr int64_t WAM_INITIAL_BLOCK_SUBSIDY = 10 * WAM_COIN;
static constexpr int WAM_SUBSIDY_HALVING_INTERVAL = 1'051'200;
static constexpr int WAM_MAX_HALVINGS = 30;
static_assert((WAM_INITIAL_BLOCK_SUBSIDY >> WAM_MAX_HALVINGS) == 0,
              "subsidy must terminate after the configured halvings");
static_assert((WAM_INITIAL_BLOCK_SUBSIDY >> (WAM_MAX_HALVINGS - 1)) > 0,
              "max halving count must not terminate one era early");

// Treasury: carved from subsidy, never added to it.
static constexpr int64_t WAM_DEVFEE_PERCENT = 5;
static constexpr int WAM_DEVFEE_START_HEIGHT = 1;
static constexpr int WAM_DEVFEE_LAST_HEIGHT = 400'000;
static_assert(WAM_DEVFEE_PERCENT >= 0 && WAM_DEVFEE_PERCENT <= 100,
              "treasury percent must be sane");
static_assert(WAM_DEVFEE_LAST_HEIGHT >= WAM_DEVFEE_START_HEIGHT,
              "treasury window must be non-empty");

// Provisional mainnet BIP44 index: ASCII "CBIT". Mainnet must not launch until
// this value has been reviewed/frozen and registration status is documented.
static constexpr uint32_t WAM_BIP44_COIN_TYPE = 0x43424954; // 1,128,417,620
static_assert(WAM_BIP44_COIN_TYPE < 0x80000000,
              "BIP44 index must fit before hardening bit");
static_assert(WAM_BIP44_COIN_TYPE != 0 && WAM_BIP44_COIN_TYPE != 1,
              "do not reuse Bitcoin/testnet BIP44 indexes for Crakbit mainnet");

// The pinned Core argument/help path constructs every CChainParams object even
// during a testnet invocation. Therefore the testnet branch must also carry a
// structurally valid MAIN object. It deliberately shares the temporary testnet
// genesis timestamp/target and has no discovery peers. A dedicated mainnet
// code-freeze commit must replace it with a newly mined independent genesis.
static constexpr int64_t WAM_GENESIS_TIME = 1790035200; // construction-only placeholder
static constexpr int64_t WAM_TESTNET_GENESIS_TIME = 1790035200; // 2026-09-22 00:00:00 UTC
static constexpr int64_t WAM_REGTEST_GENESIS_TIME = 1296688602;

// Zero-premine compatibility shape. The inherited genesis builder expects a
// tranche table, so one zero-value entry is used; it creates no CBIT.
static constexpr int WAM_PREMINE_TRANCHES = 1;
static constexpr int64_t WAM_PREMINE_TRANCHE_AMOUNT = 0;
static constexpr int64_t WAM_PREMINE_UNLOCK_TIMES[WAM_PREMINE_TRANCHES] = {0};
static_assert(WAM_PREMINE_TRANCHES * WAM_PREMINE_TRANCHE_AMOUNT == WAM_GENESIS_PREMINE,
              "genesis outputs must sum to zero premine");

// Timing and DGW
static constexpr int64_t WAM_POW_TARGET_SPACING = 120;
static constexpr int64_t WAM_DGW_PAST_BLOCKS = 24;
static constexpr int64_t WAM_DGW_CLAMP_FACTOR = 3;
static constexpr int WAM_COINBASE_MATURITY = 100;

// RandomX. Testnet overrides epoch length/lag in chainparams to 256/16 so the
// rollover path is exercised frequently.
static constexpr int WAM_RANDOMX_EPOCH_BLOCKS = 2048;
static constexpr int WAM_RANDOMX_EPOCH_LAG = 64;
static_assert(WAM_RANDOMX_EPOCH_LAG < WAM_RANDOMX_EPOCH_BLOCKS,
              "RandomX seed lag must be shorter than an epoch");

// Ports. RPC is p2p-1 because p2p+1 is used by Bitcoin Core's onion listener.
static constexpr int WAM_MAINNET_P2P_PORT = 19111;
static constexpr int WAM_MAINNET_RPC_PORT = 19110;
static constexpr int WAM_TESTNET_P2P_PORT = 29111;
static constexpr int WAM_TESTNET_RPC_PORT = 29110;
static constexpr int WAM_REGTEST_P2P_PORT = 39111;
static constexpr int WAM_REGTEST_RPC_PORT = 39110;
static_assert(WAM_MAINNET_RPC_PORT == WAM_MAINNET_P2P_PORT - 1 &&
              WAM_TESTNET_RPC_PORT == WAM_TESTNET_P2P_PORT - 1 &&
              WAM_REGTEST_RPC_PORT == WAM_REGTEST_P2P_PORT - 1,
              "RPC must remain p2p-1");

// Testnet-v0.1 genesis domain separation.
static constexpr const char* WAM_GENESIS_TIMESTAMP_PHRASE =
    "Crakbit Testnet v0.1 - 22 Sep 2026 - Build verify decentralize";
static constexpr const char* WAM_RANDOMX_BOOTSTRAP_KEY =
    "Crakbit/RandomX/testnet-v0.1/2026";

} // namespace wam

#endif // WAM_WAM_PARAMS_H
