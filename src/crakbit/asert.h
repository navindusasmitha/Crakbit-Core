// Copyright (c) 2026 Crakbit Core developers
// Portions adapted from Bitcoin ABC / Bitcoin Cash ASERT (MIT licensed).
// Distributed under the MIT software license, see the accompanying LICENSE file.

#ifndef CRAKBIT_ASERT_H
#define CRAKBIT_ASERT_H

#include <cstdint>

class arith_uint256;
class CBlockIndex;

namespace Consensus {
struct Params;
}

namespace crakbit {

/**
 * Deterministic integer ASERT target calculation.
 *
 * The implementation uses fixed-point arithmetic only. No floating-point
 * operations participate in consensus.
 */
arith_uint256 CalculateASERT(const arith_uint256& ref_target,
                             int64_t target_spacing,
                             int64_t time_diff,
                             int64_t height_diff,
                             const arith_uint256& pow_limit,
                             int64_t half_life) noexcept;

/**
 * Calculate the next Crakbit testnet target using genesis as the absolute
 * schedule anchor. The conceptual parent of genesis is one target-spacing
 * before genesis, so an exactly-on-schedule chain keeps the anchor target.
 */
uint32_t GetNextASERTWorkRequired(const CBlockIndex* prev,
                                  const Consensus::Params& params) noexcept;

} // namespace crakbit

#endif // CRAKBIT_ASERT_H
