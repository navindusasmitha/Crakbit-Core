#include "consensus/params.h"
#include "core/chain.h"
#include "wallet/wallet.h"

#include <cstdlib>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

std::filesystem::path default_datadir() {
    const char* home = std::getenv("HOME");
    if (!home) return ".crakbit/native-testnet";
    return std::filesystem::path(home) / ".crakbit" / "native-testnet";
}

std::string amount(std::uint64_t units) {
    const std::uint64_t whole = units / crakbit::consensus::COIN;
    const std::uint64_t frac = units % crakbit::consensus::COIN;
    std::ostringstream ss;
    ss << whole << '.' << std::setw(8) << std::setfill('0') << frac;
    return ss.str();
}

void usage() {
    std::cout << "Crakbit Core native wallet v0.2\n\n"
              << "Usage: crakbitd [--datadir PATH] <command> [args]\n\n"
              << "Commands:\n"
              << "  init                         Create/verify native genesis\n"
              << "  status                       Show local chain status\n"
              << "  wallet-create <name>         Create testnet secp256k1 wallet\n"
              << "  wallet-address <name>        Print tcb1 wallet address\n"
              << "  mine-wallet <name> [count]   Mine local blocks to wallet address\n"
              << "  wallet-balance <name>        Sum rewards mined to wallet address\n"
              << "  mine <destination> [count]   Legacy/local mine-to-destination command\n"
              << "  chain                        Print block summary\n"
              << "  balance <destination>        Sum rewards for destination\n";
}

} // namespace

int main(int argc, char** argv) {
    try {
        std::filesystem::path datadir = default_datadir();
        int arg = 1;
        if (arg < argc && std::string(argv[arg]) == "--datadir") {
            if (++arg >= argc) throw std::runtime_error("--datadir requires a path");
            datadir = argv[arg++];
        }
        if (arg >= argc) { usage(); return 0; }

        const std::string command = argv[arg++];
        crakbit::wallet::WalletStore wallets(datadir);

        if (command == "wallet-create") {
            if (arg >= argc) throw std::runtime_error("wallet-create requires a name");
            const auto info = wallets.create(argv[arg]);
            std::cout << "wallet: " << info.name << '\n'
                      << "address: " << info.address << '\n'
                      << "warning: native v0.2 testnet wallet keys are stored unencrypted on disk\n";
            return 0;
        }

        if (command == "wallet-address") {
            if (arg >= argc) throw std::runtime_error("wallet-address requires a name");
            std::cout << wallets.load(argv[arg]).address << '\n';
            return 0;
        }

        crakbit::core::Chain chain(datadir);
        if (command == "init") {
            chain.init();
            const auto& g = chain.blocks().front();
            std::cout << "Crakbit native chain initialized\n"
                      << "datadir: " << datadir << '\n'
                      << "genesis: " << g.pow_hash << '\n';
            return 0;
        }

        chain.init();

        if (command == "status") {
            const auto& tip = chain.blocks().back();
            std::cout << "chain: " << crakbit::consensus::CHAIN_NAME << '\n'
                      << "blocks: " << (chain.blocks().size() - 1) << '\n'
                      << "height: " << tip.header.height << '\n'
                      << "tip: " << tip.pow_hash << '\n'
                      << "datadir: " << datadir << '\n';
        } else if (command == "mine" || command == "mine-wallet") {
            if (arg >= argc) throw std::runtime_error(command + " requires a destination/name");
            std::string destination = argv[arg++];
            if (command == "mine-wallet") destination = wallets.load(destination).address;
            unsigned count = arg < argc ? static_cast<unsigned>(std::stoul(argv[arg])) : 1U;
            if (count == 0 || count > 1000) throw std::runtime_error("mine count must be 1..1000");
            for (unsigned i = 0; i < count; ++i) {
                const auto b = chain.mine_one(destination);
                std::cout << "mined height=" << b.header.height
                          << " hash=" << b.pow_hash
                          << " destination=" << destination
                          << " miner=" << amount(b.miner_reward) << " CBIT"
                          << " treasury=" << amount(b.treasury_reward) << " CBIT\n";
            }
        } else if (command == "chain") {
            for (const auto& b : chain.blocks()) {
                std::cout << b.header.height << "  " << b.pow_hash
                          << "  destination=" << b.miner_id
                          << "  reward=" << amount(b.miner_reward) << '\n';
            }
        } else if (command == "balance" || command == "wallet-balance") {
            if (arg >= argc) throw std::runtime_error(command + " requires a destination/name");
            std::string destination = argv[arg];
            if (command == "wallet-balance") destination = wallets.load(destination).address;
            std::cout << amount(chain.balance(destination)) << " CBIT\n";
        } else {
            usage();
            return 2;
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "crakbitd: " << e.what() << '\n';
        return 1;
    }
}
