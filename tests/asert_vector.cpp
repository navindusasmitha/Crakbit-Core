// Copyright (c) 2026 Crakbit Core developers
// Distributed under the MIT software license, see the accompanying LICENSE file.

#include <crakbit/asert.h>

#include <arith_uint256.h>
#include <chain.h>
#include <kernel/chainparams.h>
#include <pow.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>

namespace {

uint32_t ParseHex32(const char* text)
{
    char* end{nullptr};
    const unsigned long value = std::strtoul(text, &end, 16);
    if (end == text || *end != '\0' || value > 0xffffffffUL) {
        std::fprintf(stderr, "invalid uint32 hex: %s\n", text);
        std::exit(2);
    }
    return static_cast<uint32_t>(value);
}

int64_t ParseInt64(const char* text)
{
    char* end{nullptr};
    const long long value = std::strtoll(text, &end, 10);
    if (end == text || *end != '\0') {
        std::fprintf(stderr, "invalid int64: %s\n", text);
        std::exit(2);
    }
    return static_cast<int64_t>(value);
}

int ChainSmoke()
{
    const std::unique_ptr<const CChainParams> params = CChainParams::TestNet4();
    const Consensus::Params& consensus = params->GetConsensus();
    const CBlock& genesis_block = params->GenesisBlock();

    CBlockIndex genesis{genesis_block};
    genesis.nHeight = 0;
    genesis.pprev = nullptr;
    genesis.BuildSkip();

    CBlockHeader first_candidate{};
    first_candidate.nTime = genesis.nTime + 60;
    const uint32_t first_bits = GetNextWorkRequired(&genesis, &first_candidate, consensus);

    CBlockHeader fast_first{};
    fast_first.nVersion = 1;
    fast_first.nTime = genesis.nTime + 30;
    fast_first.nBits = first_bits;
    CBlockIndex fast_index{fast_first};
    fast_index.nHeight = 1;
    fast_index.pprev = &genesis;
    fast_index.BuildSkip();

    CBlockHeader second_candidate{};
    second_candidate.nTime = fast_index.nTime + 60;
    const uint32_t fast_second_bits = GetNextWorkRequired(&fast_index, &second_candidate, consensus);

    CBlockHeader ideal_first{};
    ideal_first.nVersion = 1;
    ideal_first.nTime = genesis.nTime + 60;
    ideal_first.nBits = first_bits;
    CBlockIndex ideal_index{ideal_first};
    ideal_index.nHeight = 1;
    ideal_index.pprev = &genesis;
    ideal_index.BuildSkip();

    const uint32_t ideal_second_bits = GetNextWorkRequired(&ideal_index, &second_candidate, consensus);

    std::printf("first=%08x\n", first_bits);
    std::printf("fast_second=%08x\n", fast_second_bits);
    std::printf("ideal_second=%08x\n", ideal_second_bits);
    return 0;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc == 2 && std::strcmp(argv[1], "--chain-smoke") == 0) {
        return ChainSmoke();
    }

    if (argc != 7) {
        std::fprintf(stderr,
                     "usage: %s <ref_bits_hex> <time_diff> <height_diff> "
                     "<pow_limit_bits_hex> <spacing> <half_life>\n",
                     argv[0]);
        return 2;
    }

    arith_uint256 ref_target;
    ref_target.SetCompact(ParseHex32(argv[1]));
    const int64_t time_diff = ParseInt64(argv[2]);
    const int64_t height_diff = ParseInt64(argv[3]);
    arith_uint256 pow_limit;
    pow_limit.SetCompact(ParseHex32(argv[4]));
    const int64_t spacing = ParseInt64(argv[5]);
    const int64_t half_life = ParseInt64(argv[6]);

    const uint32_t result = crakbit::CalculateASERT(
                                ref_target,
                                spacing,
                                time_diff,
                                height_diff,
                                pow_limit,
                                half_life)
                                .GetCompact();
    std::printf("%08x\n", result);
    return 0;
}
