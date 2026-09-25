// Crakbit-owned CRAK-005 consensus vector probe.
//
// The fields below serialize to exactly 80 bytes 0x00..0x4f. The expected
// hash therefore must match the frozen raw yespower vector, represented using
// Bitcoin uint256 display byte order.
#include <primitives/block.h>

#include <array>
#include <cstdint>
#include <iostream>
#include <span>

int main()
{
    std::array<unsigned char, 32> prev{};
    std::array<unsigned char, 32> merkle{};
    for (std::size_t i = 0; i < prev.size(); ++i) {
        prev[i] = static_cast<unsigned char>(0x04 + i);
        merkle[i] = static_cast<unsigned char>(0x24 + i);
    }

    CBlockHeader header;
    header.nVersion = 0x03020100;
    header.hashPrevBlock = uint256{std::span<const unsigned char>{prev}};
    header.hashMerkleRoot = uint256{std::span<const unsigned char>{merkle}};
    header.nTime = 0x47464544;
    header.nBits = 0x4b4a4948;
    header.nNonce = 0x4f4e4d4c;

    std::cout << header.GetHash().ToString() << '\n';
    return 0;
}
