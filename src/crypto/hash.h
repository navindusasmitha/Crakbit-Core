#pragma once

#include <array>
#include <cstdint>
#include <iomanip>
#include <sstream>
#include <string>
#include <string_view>

#include <openssl/sha.h>

namespace crakbit::crypto {

inline std::array<std::uint8_t, 32> sha256(std::string_view input) {
    std::array<std::uint8_t, 32> out{};
    SHA256(reinterpret_cast<const unsigned char*>(input.data()), input.size(), out.data());
    return out;
}

inline std::string hex(const std::uint8_t* data, std::size_t size) {
    std::ostringstream ss;
    ss << std::hex << std::setfill('0');
    for (std::size_t i = 0; i < size; ++i) ss << std::setw(2) << static_cast<unsigned>(data[i]);
    return ss.str();
}

inline std::string sha256_hex(std::string_view input) {
    const auto digest = sha256(input);
    return hex(digest.data(), digest.size());
}

} // namespace crakbit::crypto
