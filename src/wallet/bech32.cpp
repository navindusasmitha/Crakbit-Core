#include "wallet/bech32.h"

#include <array>
#include <stdexcept>

namespace crakbit::wallet {
namespace {

constexpr char CHARSET[] = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";

std::uint32_t polymod(const std::vector<std::uint8_t>& values) {
    std::uint32_t chk = 1;
    constexpr std::array<std::uint32_t, 5> GEN{
        0x3b6a57b2U, 0x26508e6dU, 0x1ea119faU, 0x3d4233ddU, 0x2a1462b3U};
    for (std::uint8_t v : values) {
        const std::uint8_t top = static_cast<std::uint8_t>(chk >> 25);
        chk = ((chk & 0x1ffffffU) << 5) ^ v;
        for (std::size_t i = 0; i < 5; ++i) {
            if ((top >> i) & 1U) chk ^= GEN[i];
        }
    }
    return chk;
}

std::vector<std::uint8_t> hrp_expand(std::string_view hrp) {
    std::vector<std::uint8_t> out;
    out.reserve(hrp.size() * 2 + 1);
    for (unsigned char c : hrp) out.push_back(c >> 5);
    out.push_back(0);
    for (unsigned char c : hrp) out.push_back(c & 31U);
    return out;
}

std::vector<std::uint8_t> convert_bits(const std::vector<std::uint8_t>& in,
                                       int from_bits,
                                       int to_bits,
                                       bool pad) {
    std::uint32_t acc = 0;
    int bits = 0;
    const std::uint32_t maxv = (1U << to_bits) - 1U;
    const std::uint32_t max_acc = (1U << (from_bits + to_bits - 1)) - 1U;
    std::vector<std::uint8_t> out;
    for (std::uint8_t value : in) {
        if ((value >> from_bits) != 0U) throw std::runtime_error("invalid convertbits value");
        acc = ((acc << from_bits) | value) & max_acc;
        bits += from_bits;
        while (bits >= to_bits) {
            bits -= to_bits;
            out.push_back(static_cast<std::uint8_t>((acc >> bits) & maxv));
        }
    }
    if (pad) {
        if (bits) out.push_back(static_cast<std::uint8_t>((acc << (to_bits - bits)) & maxv));
    } else if (bits >= from_bits || ((acc << (to_bits - bits)) & maxv)) {
        throw std::runtime_error("invalid convertbits padding");
    }
    return out;
}

std::vector<std::uint8_t> checksum(std::string_view hrp,
                                   const std::vector<std::uint8_t>& data) {
    auto values = hrp_expand(hrp);
    values.insert(values.end(), data.begin(), data.end());
    values.insert(values.end(), 6, 0);
    const std::uint32_t mod = polymod(values) ^ 1U; // BIP173 Bech32 for witness v0.
    std::vector<std::uint8_t> out(6);
    for (int i = 0; i < 6; ++i)
        out[i] = static_cast<std::uint8_t>((mod >> (5 * (5 - i))) & 31U);
    return out;
}

} // namespace

std::string encode_segwit_v0_address(std::string_view hrp,
                                     const std::vector<std::uint8_t>& witness_program) {
    if (hrp.empty()) throw std::runtime_error("empty bech32 HRP");
    if (witness_program.size() != 20 && witness_program.size() != 32)
        throw std::runtime_error("witness v0 program must be 20 or 32 bytes");

    std::vector<std::uint8_t> data{0};
    const auto converted = convert_bits(witness_program, 8, 5, true);
    data.insert(data.end(), converted.begin(), converted.end());
    const auto sum = checksum(hrp, data);

    std::string out(hrp);
    out.push_back('1');
    for (std::uint8_t v : data) out.push_back(CHARSET[v]);
    for (std::uint8_t v : sum) out.push_back(CHARSET[v]);
    return out;
}

} // namespace crakbit::wallet
