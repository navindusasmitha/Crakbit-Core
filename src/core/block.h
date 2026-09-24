#pragma once

#include <cstdint>
#include <string>

namespace crakbit::core {

struct BlockHeader {
    std::uint32_t version{1};
    std::uint64_t height{0};
    std::uint64_t timestamp{0};
    std::string previous_hash;
    std::string merkle_root;
    std::string target;
    std::uint64_t nonce{0};
};

struct Block {
    BlockHeader header;
    std::string pow_hash;
    std::string miner_id;
    std::uint64_t miner_reward{0};
    std::uint64_t treasury_reward{0};
};

std::string serialize_header(const BlockHeader& header);
std::string make_reward_root(std::uint64_t height,
                             const std::string& miner_id,
                             std::uint64_t miner_reward,
                             std::uint64_t treasury_reward);

} // namespace crakbit::core
