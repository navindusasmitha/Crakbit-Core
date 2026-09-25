// Copyright (c) 2026 The Crakbit Core developers
// Distributed under the MIT software license.

#ifndef CRAKBIT_SUBSIDY_H
#define CRAKBIT_SUBSIDY_H

#include <consensus/amount.h>

namespace crakbit {

inline constexpr CAmount INITIAL_BLOCK_SUBSIDY{5 * COIN};

/**
 * Return the block subsidy for a non-negative height using Bitcoin-style
 * integer right-shift halvings.
 */
CAmount CalculateBlockSubsidy(int height, int halving_interval) noexcept;

} // namespace crakbit

#endif // CRAKBIT_SUBSIDY_H
