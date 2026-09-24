#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace crakbit::wallet {

std::string encode_segwit_v0_address(std::string_view hrp,
                                     const std::vector<std::uint8_t>& witness_program);

} // namespace crakbit::wallet
