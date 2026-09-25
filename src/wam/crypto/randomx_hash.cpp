// Copyright (c) 2026 The WAM Coin developers
// Copyright (c) 2026 The Crakbit developers
// Distributed under the MIT software license, see COPYING.

#include <wam/crypto/randomx_hash.h>

#include <primitives/block.h>
#include <streams.h>

#include <yespower.h>

#include <cassert>
#include <cstdint>
#include <cstring>
#include <stdexcept>

namespace wam {
namespace {

static constexpr uint32_t CRAKBIT_YESPOWER_N = 2048;
static constexpr uint32_t CRAKBIT_YESPOWER_R = 8;
static constexpr unsigned char CRAKBIT_YESPOWER_PERS[] = "Crakbit-Core-v0.1";
static constexpr size_t CRAKBIT_YESPOWER_MEMORY_BYTES =
    static_cast<size_t>(128) * CRAKBIT_YESPOWER_N * CRAKBIT_YESPOWER_R;

const yespower_params_t& CrakbitYespowerParams()
{
    static const yespower_params_t params{
        YESPOWER_1_0,
        CRAKBIT_YESPOWER_N,
        CRAKBIT_YESPOWER_R,
        CRAKBIT_YESPOWER_PERS,
        sizeof(CRAKBIT_YESPOWER_PERS) - 1,
    };
    return params;
}

} // namespace

int GetRandomXSeedHeight(int /*nHeight*/, const Consensus::Params& /*params*/)
{
    return 0;
}

uint256 GetRandomXBootstrapSeed()
{
    return uint256{};
}

uint256 GetRandomXSeedHash(const CBlockIndex* /*pindexPrev*/, const Consensus::Params& /*params*/)
{
    return uint256{};
}

uint256 GetRandomXHashRaw(const unsigned char* input, size_t len, const uint256& /*seed*/)
{
    yespower_binary_t digest{};
    if (yespower_tls(reinterpret_cast<const uint8_t*>(input), len,
                     &CrakbitYespowerParams(), &digest) != 0) {
        throw std::runtime_error("Crakbit yespower hash failed");
    }

    static_assert(sizeof(digest.uc) == 32, "Crakbit requires a 256-bit yespower result");
    uint256 result;
    std::memcpy(result.begin(), digest.uc, 32);
    return result;
}

uint256 GetRandomXPoWHash(const CBlockHeader& header, const uint256& /*seed*/)
{
    DataStream ss{};
    ss << header;
    assert(ss.size() == RANDOMX_INPUT_SIZE);

    return GetRandomXHashRaw(reinterpret_cast<const unsigned char*>(ss.data()),
                             ss.size(), uint256{});
}

void SetRandomXMiningMode(bool /*fMining*/)
{
    // yespower has no multi-gigabyte dataset or mining/verification mode.
}

void FlushRandomXCaches()
{
    // yespower_tls keeps small thread-local scratch storage internally.
}

size_t GetRandomXMemoryUsage()
{
    return CRAKBIT_YESPOWER_MEMORY_BYTES;
}

} // namespace wam
