// Copyright (c) 2026 The Crakbit developers
// Distributed under the MIT software license.
#ifndef CRAKBIT_PARAMS_H
#define CRAKBIT_PARAMS_H

#include <cstdint>

namespace crakbit {

inline constexpr std::int64_t COIN = 100000000;
inline constexpr std::int64_t MAX_MONEY = 21000000LL * COIN;
inline constexpr std::int64_t INITIAL_SUBSIDY = 5LL * COIN;
inline constexpr std::int32_t HALVING_INTERVAL = 2100000;
inline constexpr std::int32_t COINBASE_MATURITY = 100;

inline constexpr std::int64_t PREMINE = 0;
inline constexpr std::int32_t TREASURY_PERCENT = 0;

inline constexpr std::uint32_t TARGET_SPACING_SECONDS = 60;
inline constexpr std::uint32_t DGW_PAST_BLOCKS = 24;

inline constexpr std::uint32_t YESPOWER_N = 2048;
inline constexpr std::uint32_t YESPOWER_R = 8;
inline constexpr char YESPOWER_PERSONALIZATION[] = "Crakbit-Core-v0.1";

inline constexpr bool MAINNET_ENABLED = false;

// Testnet-only identity. Mainnet values stay deliberately unset until the
// public testnet gates pass.
inline constexpr std::uint8_t TESTNET_MESSAGE_START[4] = {0x43, 0x52, 0x41, 0x4b};
inline constexpr std::uint16_t TESTNET_P2P_PORT = 17771;
inline constexpr std::uint16_t TESTNET_RPC_PORT = 17772;
inline constexpr std::uint8_t TESTNET_PUBKEY_ADDRESS = 28;
inline constexpr std::uint8_t TESTNET_SCRIPT_ADDRESS = 87;
inline constexpr std::uint8_t TESTNET_SECRET_KEY = 197;
inline constexpr char TESTNET_BECH32_HRP[] = "crak";

static_assert(INITIAL_SUBSIDY > 0);
static_assert(MAX_MONEY == 21000000LL * COIN);
static_assert(PREMINE == 0);
static_assert(TREASURY_PERCENT == 0);
static_assert(TARGET_SPACING_SECONDS == 60);

} // namespace crakbit

#endif // CRAKBIT_PARAMS_H
