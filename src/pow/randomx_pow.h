#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

#include <boost/multiprecision/cpp_int.hpp>
#include <randomx.h>

namespace crakbit::pow {

using Uint256 = boost::multiprecision::uint256_t;

Uint256 pow_limit();
Uint256 parse_target(std::string_view hex);
std::string target_hex(const Uint256& value);
bool meets_target(const std::array<std::uint8_t, 32>& hash, const Uint256& target);

class RandomXHasher {
public:
    explicit RandomXHasher(std::string key);
    ~RandomXHasher();

    RandomXHasher(const RandomXHasher&) = delete;
    RandomXHasher& operator=(const RandomXHasher&) = delete;

    std::array<std::uint8_t, 32> hash(std::string_view input) const;

private:
    randomx_cache* cache_{nullptr};
    randomx_vm* vm_{nullptr};
};

} // namespace crakbit::pow
