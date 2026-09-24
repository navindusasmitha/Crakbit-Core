#pragma once

#include "core/block.h"
#include "pow/randomx_pow.h"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace crakbit::core {

class Chain {
public:
    explicit Chain(std::filesystem::path datadir);

    void init();
    void load();
    Block mine_one(const std::string& miner_id);
    void verify() const;

    const std::vector<Block>& blocks() const { return blocks_; }
    std::uint64_t balance(const std::string& miner_id) const;
    std::filesystem::path datadir() const { return datadir_; }

private:
    std::filesystem::path datadir_;
    std::filesystem::path chain_file_;
    std::vector<Block> blocks_;

    void append_block(const Block& block);
    Block mine_genesis() const;
    crakbit::pow::Uint256 next_target() const;
    std::string seed_key_for_height(std::uint64_t height) const;
    static std::uint64_t now();
};

} // namespace crakbit::core
