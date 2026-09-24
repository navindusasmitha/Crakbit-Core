#include "core/chain.h"

#include "consensus/params.h"
#include "crypto/hash.h"

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>

namespace crakbit::core {
namespace {

std::vector<std::string> split_tab(const std::string& line) {
    std::vector<std::string> parts;
    std::stringstream ss(line);
    std::string item;
    while (std::getline(ss, item, '\t')) parts.push_back(item);
    return parts;
}

std::string hash_hex(const std::array<std::uint8_t, 32>& hash) {
    return crakbit::crypto::hex(hash.data(), hash.size());
}

void validate_miner_id(const std::string& id) {
    if (id.empty()) throw std::runtime_error("miner id cannot be empty");
    if (id.find('\t') != std::string::npos || id.find('\n') != std::string::npos || id.find('\r') != std::string::npos)
        throw std::runtime_error("miner id contains invalid whitespace");
}

} // namespace

Chain::Chain(std::filesystem::path datadir)
    : datadir_(std::move(datadir)), chain_file_(datadir_ / "chain.tsv") {}

std::uint64_t Chain::now() {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::system_clock::now().time_since_epoch()).count());
}

void Chain::init() {
    std::filesystem::create_directories(datadir_);
    if (std::filesystem::exists(chain_file_)) {
        load();
        return;
    }
    blocks_.clear();
    const Block genesis = mine_genesis();
    blocks_.push_back(genesis);
    append_block(genesis);
}

Block Chain::mine_genesis() const {
    Block b;
    b.header.version = 1;
    b.header.height = 0;
    b.header.timestamp = consensus::GENESIS_TIMESTAMP;
    b.header.previous_hash = std::string(64, '0');
    b.header.merkle_root = crakbit::crypto::sha256_hex(consensus::GENESIS_MESSAGE);
    b.header.target = crakbit::pow::target_hex(crakbit::pow::pow_limit());
    b.miner_id = "genesis";
    b.miner_reward = 0;
    b.treasury_reward = 0;

    crakbit::pow::RandomXHasher hasher(std::string(consensus::RANDOMX_BOOTSTRAP_KEY));
    const auto target = crakbit::pow::parse_target(b.header.target);
    for (std::uint64_t nonce = 0;; ++nonce) {
        b.header.nonce = nonce;
        const auto digest = hasher.hash(serialize_header(b.header));
        if (crakbit::pow::meets_target(digest, target)) {
            b.pow_hash = hash_hex(digest);
            return b;
        }
    }
}

void Chain::load() {
    blocks_.clear();
    std::ifstream in(chain_file_);
    if (!in) throw std::runtime_error("cannot open chain database");
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const auto p = split_tab(line);
        if (p.size() != 11) throw std::runtime_error("corrupt chain row");
        Block b;
        b.header.version = static_cast<std::uint32_t>(std::stoul(p[0]));
        b.header.height = std::stoull(p[1]);
        b.header.timestamp = std::stoull(p[2]);
        b.header.previous_hash = p[3];
        b.header.merkle_root = p[4];
        b.header.target = p[5];
        b.header.nonce = std::stoull(p[6]);
        b.pow_hash = p[7];
        b.miner_id = p[8];
        b.miner_reward = std::stoull(p[9]);
        b.treasury_reward = std::stoull(p[10]);
        blocks_.push_back(std::move(b));
    }
    if (blocks_.empty()) throw std::runtime_error("chain database is empty");
    verify();
}

void Chain::append_block(const Block& b) {
    std::ofstream out(chain_file_, std::ios::app);
    if (!out) throw std::runtime_error("cannot append chain database");
    out << b.header.version << '\t'
        << b.header.height << '\t'
        << b.header.timestamp << '\t'
        << b.header.previous_hash << '\t'
        << b.header.merkle_root << '\t'
        << b.header.target << '\t'
        << b.header.nonce << '\t'
        << b.pow_hash << '\t'
        << b.miner_id << '\t'
        << b.miner_reward << '\t'
        << b.treasury_reward << '\n';
    out.flush();
    if (!out) throw std::runtime_error("chain database write failed");
}

crakbit::pow::Uint256 Chain::next_target() const {
    using namespace crakbit::pow;
    if (blocks_.size() < consensus::DGW_WINDOW) return pow_limit();

    const std::size_t count = consensus::DGW_WINDOW;
    const std::size_t begin = blocks_.size() - count;
    boost::multiprecision::uint512_t sum = 0;
    for (std::size_t i = begin; i < blocks_.size(); ++i)
        sum += parse_target(blocks_[i].header.target);

    boost::multiprecision::uint512_t avg = sum / count;
    const std::uint64_t first_time = blocks_[begin].header.timestamp;
    const std::uint64_t last_time = blocks_.back().header.timestamp;
    std::uint64_t actual = last_time > first_time ? last_time - first_time : 1;
    const std::uint64_t expected = static_cast<std::uint64_t>(consensus::BLOCK_TARGET_SECONDS) * count;
    actual = std::max(expected / consensus::DGW_CLAMP,
                      std::min(expected * consensus::DGW_CLAMP, actual));

    boost::multiprecision::uint512_t adjusted = (avg * actual) / expected;
    const boost::multiprecision::uint512_t limit = pow_limit();
    if (adjusted > limit) adjusted = limit;
    return static_cast<Uint256>(adjusted);
}

std::string Chain::seed_key_for_height(std::uint64_t height) const {
    if (height < consensus::RANDOMX_EPOCH_BLOCKS + consensus::RANDOMX_SEED_LAG)
        return std::string(consensus::RANDOMX_BOOTSTRAP_KEY);

    const std::uint64_t epoch_start = (height / consensus::RANDOMX_EPOCH_BLOCKS) * consensus::RANDOMX_EPOCH_BLOCKS;
    const std::uint64_t seed_height = epoch_start > consensus::RANDOMX_SEED_LAG
        ? epoch_start - consensus::RANDOMX_SEED_LAG : 0;
    if (seed_height >= blocks_.size()) throw std::runtime_error("RandomX seed height unavailable");
    return "Crakbit/RandomX/native/" + blocks_[seed_height].pow_hash;
}

Block Chain::mine_one(const std::string& miner_id) {
    validate_miner_id(miner_id);
    if (blocks_.empty()) init();

    Block b;
    b.header.version = 1;
    b.header.height = blocks_.size();
    b.header.timestamp = std::max(now(), blocks_.back().header.timestamp + 1);
    b.header.previous_hash = blocks_.back().pow_hash;
    b.miner_id = miner_id;
    b.miner_reward = consensus::miner_share(b.header.height);
    b.treasury_reward = consensus::treasury_share(b.header.height);
    b.header.merkle_root = make_reward_root(b.header.height, miner_id, b.miner_reward, b.treasury_reward);
    const auto target = next_target();
    b.header.target = crakbit::pow::target_hex(target);

    const std::string seed_key = seed_key_for_height(b.header.height);
    crakbit::pow::RandomXHasher hasher(seed_key);
    for (std::uint64_t nonce = 0;; ++nonce) {
        b.header.nonce = nonce;
        const auto digest = hasher.hash(serialize_header(b.header));
        if (crakbit::pow::meets_target(digest, target)) {
            b.pow_hash = hash_hex(digest);
            break;
        }
    }

    blocks_.push_back(b);
    append_block(b);
    return b;
}

void Chain::verify() const {
    if (blocks_.empty()) throw std::runtime_error("empty chain");

    for (std::size_t i = 0; i < blocks_.size(); ++i) {
        const Block& b = blocks_[i];
        if (b.header.height != i) throw std::runtime_error("invalid block height");
        if (i == 0) {
            if (b.header.previous_hash != std::string(64, '0')) throw std::runtime_error("invalid genesis previous hash");
            if (b.header.timestamp != consensus::GENESIS_TIMESTAMP) throw std::runtime_error("invalid genesis timestamp");
            if (b.header.merkle_root != crakbit::crypto::sha256_hex(consensus::GENESIS_MESSAGE))
                throw std::runtime_error("invalid genesis identity");
        } else {
            if (b.header.previous_hash != blocks_[i - 1].pow_hash) throw std::runtime_error("broken block linkage");
            if (b.miner_reward != consensus::miner_share(i)) throw std::runtime_error("invalid miner subsidy");
            if (b.treasury_reward != consensus::treasury_share(i)) throw std::runtime_error("invalid treasury subsidy");
        }

        const std::string key = seed_key_for_height(i);
        crakbit::pow::RandomXHasher hasher(key);
        const auto digest = hasher.hash(serialize_header(b.header));
        if (hash_hex(digest) != b.pow_hash) throw std::runtime_error("invalid stored PoW hash");
        if (!crakbit::pow::meets_target(digest, crakbit::pow::parse_target(b.header.target)))
            throw std::runtime_error("block does not meet target");
    }
}

std::uint64_t Chain::balance(const std::string& miner_id) const {
    std::uint64_t total = 0;
    for (const Block& b : blocks_) if (b.miner_id == miner_id) total += b.miner_reward;
    return total;
}

} // namespace crakbit::core
