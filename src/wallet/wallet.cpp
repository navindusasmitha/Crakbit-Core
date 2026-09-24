#include "wallet/wallet.h"

#include "wallet/bech32.h"

#include <openssl/bn.h>
#include <openssl/ec.h>
#include <openssl/evp.h>
#include <openssl/obj_mac.h>

#include <array>
#include <cctype>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace crakbit::wallet {
namespace {

std::string hex(const unsigned char* data, std::size_t size) {
    std::ostringstream ss;
    ss << std::hex << std::setfill('0');
    for (std::size_t i = 0; i < size; ++i) ss << std::setw(2) << static_cast<unsigned>(data[i]);
    return ss.str();
}

std::vector<unsigned char> hash160(const unsigned char* data, std::size_t size) {
    std::array<unsigned char, 32> sha{};
    unsigned int sha_len = 0;
    if (EVP_Digest(data, size, sha.data(), &sha_len, EVP_sha256(), nullptr) != 1 || sha_len != sha.size())
        throw std::runtime_error("SHA256 failed");

    std::array<unsigned char, 20> ripe{};
    unsigned int ripe_len = 0;
    if (EVP_Digest(sha.data(), sha.size(), ripe.data(), &ripe_len, EVP_ripemd160(), nullptr) != 1 || ripe_len != ripe.size())
        throw std::runtime_error("RIPEMD160 failed");
    return {ripe.begin(), ripe.end()};
}

WalletInfo generate_wallet(const std::string& name) {
    using KeyPtr = std::unique_ptr<EC_KEY, decltype(&EC_KEY_free)>;
    KeyPtr key(EC_KEY_new_by_curve_name(NID_secp256k1), EC_KEY_free);
    if (!key) throw std::runtime_error("unable to create secp256k1 key context");
    EC_KEY_set_conv_form(key.get(), POINT_CONVERSION_COMPRESSED);
    if (EC_KEY_generate_key(key.get()) != 1) throw std::runtime_error("secp256k1 key generation failed");

    const BIGNUM* priv = EC_KEY_get0_private_key(key.get());
    const EC_GROUP* group = EC_KEY_get0_group(key.get());
    const EC_POINT* pub = EC_KEY_get0_public_key(key.get());
    if (!priv || !group || !pub) throw std::runtime_error("generated key is incomplete");

    std::array<unsigned char, 32> priv_bytes{};
    if (BN_bn2binpad(priv, priv_bytes.data(), static_cast<int>(priv_bytes.size())) != static_cast<int>(priv_bytes.size()))
        throw std::runtime_error("private key serialization failed");

    const std::size_t pub_len = EC_POINT_point2oct(group, pub, POINT_CONVERSION_COMPRESSED,
                                                   nullptr, 0, nullptr);
    if (pub_len != 33) throw std::runtime_error("compressed public key size is invalid");
    std::vector<unsigned char> pub_bytes(pub_len);
    if (EC_POINT_point2oct(group, pub, POINT_CONVERSION_COMPRESSED,
                           pub_bytes.data(), pub_bytes.size(), nullptr) != pub_bytes.size())
        throw std::runtime_error("public key serialization failed");

    const auto program_raw = hash160(pub_bytes.data(), pub_bytes.size());
    std::vector<std::uint8_t> program(program_raw.begin(), program_raw.end());

    WalletInfo info;
    info.name = name;
    info.private_key_hex = hex(priv_bytes.data(), priv_bytes.size());
    info.public_key_hex = hex(pub_bytes.data(), pub_bytes.size());
    info.address = encode_segwit_v0_address("tcb", program);
    return info;
}

std::string value_after(const std::string& line, const std::string& prefix) {
    if (line.rfind(prefix, 0) != 0) throw std::runtime_error("invalid wallet file format");
    return line.substr(prefix.size());
}

} // namespace

WalletStore::WalletStore(std::filesystem::path datadir)
    : wallet_dir_(std::move(datadir) / "wallets") {}

void WalletStore::validate_name(const std::string& name) {
    if (name.empty() || name.size() > 64) throw std::runtime_error("wallet name length must be 1..64");
    for (unsigned char c : name) {
        if (!(std::isalnum(c) || c == '-' || c == '_'))
            throw std::runtime_error("wallet name may contain only letters, digits, '-' and '_'");
    }
}

std::filesystem::path WalletStore::wallet_path(const std::string& name) const {
    validate_name(name);
    return wallet_dir_ / (name + ".wallet");
}

WalletInfo WalletStore::create(const std::string& name) const {
    validate_name(name);
    std::filesystem::create_directories(wallet_dir_);
    const auto path = wallet_path(name);
    if (std::filesystem::exists(path)) throw std::runtime_error("wallet already exists: " + name);

    const WalletInfo info = generate_wallet(name);
    std::ofstream out(path, std::ios::out | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot create wallet file");
    out << "version=1\n"
        << "name=" << info.name << '\n'
        << "private_key=" << info.private_key_hex << '\n'
        << "public_key=" << info.public_key_hex << '\n'
        << "address=" << info.address << '\n';
    out.flush();
    if (!out) throw std::runtime_error("wallet file write failed");
    out.close();

    std::filesystem::permissions(path,
        std::filesystem::perms::owner_read | std::filesystem::perms::owner_write,
        std::filesystem::perm_options::replace);
    return info;
}

WalletInfo WalletStore::load(const std::string& name) const {
    const auto path = wallet_path(name);
    std::ifstream in(path);
    if (!in) throw std::runtime_error("wallet not found: " + name);

    std::string version_line, name_line, priv_line, pub_line, address_line;
    if (!std::getline(in, version_line) || !std::getline(in, name_line) ||
        !std::getline(in, priv_line) || !std::getline(in, pub_line) || !std::getline(in, address_line))
        throw std::runtime_error("wallet file is incomplete");
    if (version_line != "version=1") throw std::runtime_error("unsupported wallet version");

    WalletInfo info;
    info.name = value_after(name_line, "name=");
    info.private_key_hex = value_after(priv_line, "private_key=");
    info.public_key_hex = value_after(pub_line, "public_key=");
    info.address = value_after(address_line, "address=");
    if (info.name != name || info.address.rfind("tcb1", 0) != 0)
        throw std::runtime_error("wallet identity validation failed");
    return info;
}

} // namespace crakbit::wallet
