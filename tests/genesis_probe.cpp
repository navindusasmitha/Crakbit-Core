#include <arith_uint256.h>
#include <kernel/chainparams.h>
#include <primitives/block.h>

#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string_view>

static void MineGenesis(std::string_view label, std::unique_ptr<const CChainParams> params)
{
    CBlock block{params->GenesisBlock()};

    bool negative{false};
    bool overflow{false};
    arith_uint256 target;
    target.SetCompact(block.nBits, &negative, &overflow);
    if (negative || overflow || target == 0) {
        throw std::runtime_error("invalid compact target in genesis candidate");
    }

    for (uint64_t nonce = 0; nonce <= std::numeric_limits<uint32_t>::max(); ++nonce) {
        block.nNonce = static_cast<uint32_t>(nonce);
        const uint256 hash{block.GetHash()};
        if (UintToArith256(hash) <= target) {
            std::cout << label
                      << " nonce=" << block.nNonce
                      << " hash=" << hash.ToString()
                      << " merkle=" << block.hashMerkleRoot.ToString()
                      << " bits=0x" << std::hex << block.nBits << std::dec
                      << '\n';
            return;
        }
    }

    throw std::runtime_error("no valid genesis nonce found in uint32 range");
}

int main()
{
    MineGenesis("testnet4", CChainParams::TestNet4());
    MineGenesis("regtest", CChainParams::RegTest({}));
    return 0;
}
