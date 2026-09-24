#include "pow/randomx_pow.h"

#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace crakbit::pow {

Uint256 pow_limit() {
    // Native local-testnet limit: 12 leading zero bits.
    return (Uint256(1) << 244) - 1;
}

Uint256 parse_target(std::string_view text) {
    Uint256 value = 0;
    for (char c : text) {
        unsigned digit = 0;
        if (c >= '0' && c <= '9') digit = static_cast<unsigned>(c - '0');
        else if (c >= 'a' && c <= 'f') digit = static_cast<unsigned>(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') digit = static_cast<unsigned>(c - 'A' + 10);
        else throw std::runtime_error("invalid target hex");
        value <<= 4;
        value += digit;
    }
    return value;
}

std::string target_hex(const Uint256& value) {
    std::ostringstream ss;
    ss << std::hex << value;
    std::string out = ss.str();
    if (out.size() < 64) out.insert(out.begin(), 64 - out.size(), '0');
    return out;
}

bool meets_target(const std::array<std::uint8_t, 32>& hash, const Uint256& target) {
    Uint256 value = 0;
    for (std::uint8_t byte : hash) {
        value <<= 8;
        value += byte;
    }
    return value <= target;
}

RandomXHasher::RandomXHasher(std::string key) {
    randomx_flags flags = randomx_get_flags();
    // Local/testnet light mode: cache-backed VM, no 2+ GiB full dataset requirement.
    flags = static_cast<randomx_flags>(flags & ~RANDOMX_FLAG_FULL_MEM);
    cache_ = randomx_alloc_cache(flags);
    if (!cache_) throw std::runtime_error("RandomX cache allocation failed");
    randomx_init_cache(cache_, key.data(), key.size());
    vm_ = randomx_create_vm(flags, cache_, nullptr);
    if (!vm_) {
        randomx_release_cache(cache_);
        cache_ = nullptr;
        throw std::runtime_error("RandomX VM creation failed");
    }
}

RandomXHasher::~RandomXHasher() {
    if (vm_) randomx_destroy_vm(vm_);
    if (cache_) randomx_release_cache(cache_);
}

std::array<std::uint8_t, 32> RandomXHasher::hash(std::string_view input) const {
    std::array<std::uint8_t, 32> out{};
    randomx_calculate_hash(vm_, input.data(), input.size(), out.data());
    return out;
}

} // namespace crakbit::pow
