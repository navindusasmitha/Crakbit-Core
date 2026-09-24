#pragma once

#include <cstdint>
#include <string_view>

namespace crakbit::consensus {

inline constexpr std::string_view CHAIN_NAME = "Crakbit Native Testnet v0.1";
inline constexpr std::string_view TICKER = "CBIT";
inline constexpr std::uint64_t COIN = 100'000'000ULL;
inline constexpr std::uint8_t DECIMALS = 8;

inline constexpr std::uint64_t INITIAL_SUBSIDY = 10ULL * COIN;
inline constexpr std::uint64_t HALVING_INTERVAL = 1'051'200ULL;
inline constexpr std::uint64_t TREASURY_START = 1ULL;
inline constexpr std::uint64_t TREASURY_END = 400'000ULL;
inline constexpr std::uint32_t TREASURY_PERCENT = 5;

inline constexpr std::uint32_t BLOCK_TARGET_SECONDS = 120;
inline constexpr std::uint32_t DGW_WINDOW = 24;
inline constexpr std::uint32_t DGW_CLAMP = 3;

inline constexpr std::uint32_t RANDOMX_EPOCH_BLOCKS = 256;
inline constexpr std::uint32_t RANDOMX_SEED_LAG = 16;
inline constexpr std::string_view RANDOMX_BOOTSTRAP_KEY =
    "Crakbit/RandomX/native-testnet-v0.1/2026-09-24";

inline constexpr std::uint64_t GENESIS_TIMESTAMP = 1'790'208'000ULL; // 2026-09-24 00:00:00 UTC
inline constexpr std::string_view GENESIS_MESSAGE =
    "Crakbit Native Testnet v0.1 - 24 Sep 2026 - Independent chain by Crakbit Society";

inline std::uint64_t block_subsidy(std::uint64_t height) {
    if (height == 0) return 0;
    const std::uint64_t era = height / HALVING_INTERVAL;
    if (era >= 64) return 0;
    return INITIAL_SUBSIDY >> era;
}

inline std::uint64_t treasury_share(std::uint64_t height) {
    if (height < TREASURY_START || height > TREASURY_END) return 0;
    return (block_subsidy(height) * TREASURY_PERCENT) / 100ULL;
}

inline std::uint64_t miner_share(std::uint64_t height) {
    return block_subsidy(height) - treasury_share(height);
}

} // namespace crakbit::consensus
