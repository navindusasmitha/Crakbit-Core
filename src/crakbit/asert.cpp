// Copyright (c) 2026 Crakbit Core developers
// Portions adapted from the Bitcoin Cash ASERT reference implementation
// Copyright (c) 2020 The Bitcoin developers
// Distributed under the MIT software license, see the accompanying LICENSE file.

#include <crakbit/asert.h>

#include <arith_uint256.h>
#include <chain.h>
#include <consensus/params.h>

#include <cassert>
#include <cstdint>

namespace crakbit {
namespace {

using arith_uint512 = base_uint<512>;

arith_uint512 Widen(const arith_uint256& value)
{
    arith_uint512 out{};
    for (unsigned int i = 0; i < 4; ++i) {
        arith_uint512 limb{(value >> (64 * i)).GetLow64()};
        limb <<= 64 * i;
        out += limb;
    }
    return out;
}

arith_uint256 Narrow(const arith_uint512& value)
{
    arith_uint256 out{};
    for (unsigned int i = 0; i < 4; ++i) {
        arith_uint256 limb{(value >> (64 * i)).GetLow64()};
        limb <<= 64 * i;
        out += limb;
    }
    return out;
}

} // namespace

arith_uint256 CalculateASERT(const arith_uint256& ref_target,
                             const int64_t target_spacing,
                             const int64_t time_diff,
                             const int64_t height_diff,
                             const arith_uint256& pow_limit,
                             const int64_t half_life) noexcept
{
    assert(ref_target > 0 && ref_target <= pow_limit);
    assert(target_spacing > 0);
    assert(height_diff >= 0);
    assert(half_life > 0);

    // The fixed-point exponent is signed with 16 fractional bits. C++ integer
    // division truncates toward zero, exactly as required by the ASERT spec.
    const int64_t schedule = target_spacing * (height_diff + 1);
    const int64_t drift = time_diff - schedule;
    constexpr int64_t MAX_SAFE_DRIFT = (int64_t{1} << 47) - 1;
    assert(drift >= -MAX_SAFE_DRIFT && drift <= MAX_SAFE_DRIFT);
    const int64_t exponent = (drift * 65536) / half_life;

    // C++20 guarantees arithmetic right shift for signed integers. Crakbit
    // builds as C++20 through the pinned Bitcoin Core v31.1 build system.
    static_assert((int64_t{-1} >> 1) == int64_t{-1});

    int64_t shifts = exponent >> 16;
    const uint64_t frac = static_cast<uint16_t>(exponent);
    assert(exponent == shifts * 65536 + static_cast<int64_t>(frac));

    // Cubic approximation to 2^x over x in [0,1), copied from the audited
    // aserti3-2d reference formulation. The error is deterministic and bounded.
    const uint32_t factor = 65536 + static_cast<uint32_t>(
        (195766423245049ULL * frac +
         971821376ULL * frac * frac +
         5127ULL * frac * frac * frac +
         (1ULL << 47)) >> 48);

    // Bitcoin Cash's original implementation assumes >=32 leading zero bits
    // in powLimit. Crakbit testnet deliberately uses an easier CPU-test target,
    // so a 512-bit intermediate is used instead. This preserves the exact
    // mathematical operation without overflow before the final powLimit clamp.
    arith_uint512 next = Widen(ref_target);
    next *= factor;

    shifts -= 16; // factor carries 16 fractional bits.
    if (shifts <= 0) {
        const uint64_t right = static_cast<uint64_t>(-shifts);
        if (right >= 512) {
            next = 0;
        } else {
            next >>= static_cast<unsigned int>(right);
        }
    } else {
        if (shifts >= 512 || next.bits() + static_cast<uint64_t>(shifts) > 512) {
            return pow_limit;
        }
        next <<= static_cast<unsigned int>(shifts);
    }

    if (next == 0) {
        return arith_uint256{1};
    }

    const arith_uint512 wide_limit = Widen(pow_limit);
    if (next > wide_limit) {
        return pow_limit;
    }
    return Narrow(next);
}

uint32_t GetNextASERTWorkRequired(const CBlockIndex* prev,
                                  const Consensus::Params& params) noexcept
{
    assert(prev != nullptr);
    assert(params.fPowUseASERT);
    assert(params.nASERTHalfLife > 0);
    assert(params.nPowTargetSpacing > 0);

    const CBlockIndex* anchor = prev->GetAncestor(0);
    assert(anchor != nullptr);
    assert(anchor->nHeight == 0);

    const arith_uint256 pow_limit = UintToArith256(params.powLimit);
    bool negative{false};
    bool overflow{false};
    arith_uint256 ref_target;
    ref_target.SetCompact(anchor->nBits, &negative, &overflow);
    assert(!negative && !overflow && ref_target > 0 && ref_target <= pow_limit);

    // A new chain has no real parent for genesis. Define its conceptual parent
    // one target-spacing earlier. This makes genesis itself exactly on the
    // ASERT schedule and keeps the anchor target for an ideal 60-second chain.
    const int64_t anchor_parent_time =
        anchor->GetBlockTime() - params.nPowTargetSpacing;
    const int64_t time_diff = prev->GetBlockTime() - anchor_parent_time;
    const int64_t height_diff = prev->nHeight - anchor->nHeight;

    return CalculateASERT(ref_target,
                          params.nPowTargetSpacing,
                          time_diff,
                          height_diff,
                          pow_limit,
                          params.nASERTHalfLife)
        .GetCompact();
}

} // namespace crakbit
