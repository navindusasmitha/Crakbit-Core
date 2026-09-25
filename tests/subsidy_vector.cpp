// Copyright (c) 2026 The Crakbit Core developers
// Distributed under the MIT software license.

#include <consensus/consensus.h>
#include <crakbit/subsidy.h>

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {
constexpr int HALVING_INTERVAL{2'100'000};
}

int main(int argc, char** argv)
{
    static_assert(COINBASE_MATURITY == 100, "Crakbit v0.1 requires 100-block coinbase maturity");

    if (argc == 2 && std::string{argv[1]} == "--maturity") {
        std::cout << COINBASE_MATURITY << '\n';
        return 0;
    }

    if (argc == 2 && std::string{argv[1]} == "--supply") {
        int64_t total{0};
        for (int era = 0; era < 64; ++era) {
            const CAmount subsidy{crakbit::CalculateBlockSubsidy(era * HALVING_INTERVAL, HALVING_INTERVAL)};
            if (subsidy == 0) break;
            total += subsidy * int64_t{HALVING_INTERVAL};
        }
        std::cout << total << '\n';
        return 0;
    }

    if (argc == 3 && std::string{argv[1]} == "--height") {
        const int height{std::stoi(argv[2])};
        std::cout << crakbit::CalculateBlockSubsidy(height, HALVING_INTERVAL) << '\n';
        return 0;
    }

    std::cerr << "usage: crakbit_subsidy_vector --height N | --maturity | --supply\n";
    return 2;
}
