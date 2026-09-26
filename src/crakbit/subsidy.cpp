// Copyright (c) 2026 The Crakbit Core developers
// Distributed under the MIT software license.

#include <crakbit/subsidy.h>

namespace crakbit {

CAmount CalculateBlockSubsidy(int height, int halving_interval) noexcept
{
    if (height < 0 || halving_interval <= 0) return 0;

    const int halvings{height / halving_interval};
    if (halvings >= 64) return 0;

    return INITIAL_BLOCK_SUBSIDY >> halvings;
}

} // namespace crakbit
