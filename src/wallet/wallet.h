#pragma once

#include <filesystem>
#include <string>

namespace crakbit::wallet {

struct WalletInfo {
    std::string name;
    std::string private_key_hex;
    std::string public_key_hex;
    std::string address;
};

class WalletStore {
public:
    explicit WalletStore(std::filesystem::path datadir);

    WalletInfo create(const std::string& name) const;
    WalletInfo load(const std::string& name) const;

private:
    std::filesystem::path wallet_dir_;

    static void validate_name(const std::string& name);
    std::filesystem::path wallet_path(const std::string& name) const;
};

} // namespace crakbit::wallet
