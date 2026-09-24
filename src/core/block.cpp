#include "core/block.h"

#include "crypto/hash.h"

#include <sstream>

namespace crakbit::core {

std::string serialize_header(const BlockHeader& h) {
    // Consensus serialization for native v0.1. Any future change requires a network version bump.
    std::ostringstream ss;
    ss << h.version << '|'
       << h.height << '|'
       << h.timestamp << '|'
       << h.previous_hash << '|'
       << h.merkle_root << '|'
       << h.target << '|'
       << h.nonce;
    return ss.str();
}

std::string make_reward_root(std::uint64_t height,
                             const std::string& miner_id,
                             std::uint64_t miner_reward,
                             std::uint64_t treasury_reward) {
    std::ostringstream ss;
    ss << "CBIT-REWARD|" << height << '|' << miner_id << '|'
       << miner_reward << '|' << treasury_reward;
    return crakbit::crypto::sha256_hex(ss.str());
}

} // namespace crakbit::core
