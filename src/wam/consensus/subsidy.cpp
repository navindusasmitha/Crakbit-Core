// Copyright (c) 2026 The WAM Coin developers
// Copyright (c) 2026 The Crakbit developers
// Distributed under the MIT software license, see COPYING.

#include <wam/consensus/subsidy.h>

#include <consensus/params.h>
#include <wam/wam-params.h>

#include <cassert>

namespace wam {

CAmount GetBlockSubsidy(int nHeight, const Consensus::Params& consensusParams)
{
    if (nHeight <= 0) return 0; // Crakbit has no genesis premine.

    const int nInterval = consensusParams.nSubsidyHalvingInterval;
    assert(nInterval > 0);

    // Height 1 is the first rewarded block, so each emission epoch contains
    // exactly nInterval mined blocks and genesis is outside the schedule.
    const int nHalvings = (nHeight - 1) / nInterval;
    if (nHalvings >= WAM_MAX_HALVINGS) return 0;

    return WAM_INITIAL_BLOCK_SUBSIDY >> nHalvings;
}

bool IsDevFeeActive(int /*nHeight*/)
{
    return false;
}

CAmount GetDevFeeAmount(CAmount /*nSubsidy*/, int /*nHeight*/)
{
    return 0;
}

CAmount GetMinerSubsidy(CAmount nSubsidy, int /*nHeight*/)
{
    return nSubsidy;
}

CAmount GetLifetimeDevFee(const Consensus::Params& /*consensusParams*/)
{
    return 0;
}

CAmount GetVestedPremine(int64_t /*nBlockTime*/)
{
    return 0;
}

CAmount GetTotalSupplyAtHeight(int nHeight, const Consensus::Params& consensusParams)
{
    if (nHeight <= 0) return 0;

    const int nInterval = consensusParams.nSubsidyHalvingInterval;
    assert(nInterval > 0);

    CAmount nSupply = 0;
    const int nCompletedEpochs = (nHeight - 1) / nInterval;

    for (int e = 0; e < nCompletedEpochs && e < WAM_MAX_HALVINGS; ++e) {
        nSupply += static_cast<CAmount>(nInterval) * (WAM_INITIAL_BLOCK_SUBSIDY >> e);
    }

    if (nCompletedEpochs < WAM_MAX_HALVINGS) {
        const int nBlocksIntoEpoch = ((nHeight - 1) % nInterval) + 1;
        nSupply += static_cast<CAmount>(nBlocksIntoEpoch)
                 * (WAM_INITIAL_BLOCK_SUBSIDY >> nCompletedEpochs);
    }

    assert(nSupply <= WAM_MAX_MONEY);
    return nSupply;
}

} // namespace wam
