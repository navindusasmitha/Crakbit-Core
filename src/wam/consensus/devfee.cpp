// Copyright (c) 2026 The WAM Coin developers
// Copyright (c) 2026 The Crakbit developers
// Distributed under the MIT software license, see COPYING.

#include <wam/consensus/devfee.h>

#include <consensus/params.h>
#include <consensus/validation.h>
#include <primitives/transaction.h>
#include <script/script.h>

namespace wam {

const CScript& DevFeeScript(const Consensus::Params& /*consensusParams*/)
{
    // Crakbit has no consensus treasury output. Keeping an empty script behind
    // the inherited API avoids decoding any historical WAM treasury address.
    static const CScript empty_script{};
    return empty_script;
}

CAmount GetPaidDevFee(const CTransaction& /*coinbase*/,
                      const Consensus::Params& /*consensusParams*/)
{
    return 0;
}

bool CheckDevFeeOutput(const CTransaction& /*coinbase*/,
                       int /*nHeight*/,
                       CAmount /*nBlockSubsidy*/,
                       const Consensus::Params& /*consensusParams*/,
                       BlockValidationState& /*state*/)
{
    // Deliberately unconditional: Crakbit consensus does not reserve any block
    // subsidy for a founder, developer, treasury or mandatory payout address.
    return true;
}

} // namespace wam
