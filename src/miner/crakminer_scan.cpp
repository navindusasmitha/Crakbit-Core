#include <yespower.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Options {
    std::array<unsigned char, 80> header{};
    std::array<unsigned char, 32> target_be{};
    uint32_t start_nonce{0};
    uint64_t max_hashes{1'000'000};
    unsigned int threads{1};
    unsigned int cpu_limit{100};
};

[[noreturn]] void fail(const std::string& msg)
{
    std::cerr << "crakminer-scan: " << msg << '\n';
    std::exit(1);
}

unsigned char hex_nibble(char c)
{
    if (c >= '0' && c <= '9') return static_cast<unsigned char>(c - '0');
    if (c >= 'a' && c <= 'f') return static_cast<unsigned char>(10 + c - 'a');
    if (c >= 'A' && c <= 'F') return static_cast<unsigned char>(10 + c - 'A');
    throw std::runtime_error("invalid hex character");
}

template <size_t N>
std::array<unsigned char, N> parse_hex_exact(const std::string& hex)
{
    if (hex.size() != N * 2) {
        throw std::runtime_error("unexpected hex length");
    }
    std::array<unsigned char, N> out{};
    for (size_t i = 0; i < N; ++i) {
        out[i] = static_cast<unsigned char>((hex_nibble(hex[i * 2]) << 4) | hex_nibble(hex[i * 2 + 1]));
    }
    return out;
}

uint64_t parse_u64(const std::string& value, const char* name)
{
    size_t used = 0;
    unsigned long long parsed = 0;
    try {
        parsed = std::stoull(value, &used, 10);
    } catch (const std::exception&) {
        fail(std::string(name) + " must be an unsigned integer");
    }
    if (used != value.size()) fail(std::string(name) + " must be an unsigned integer");
    return static_cast<uint64_t>(parsed);
}

void usage()
{
    std::cout
        << "Usage: crakminer-scan --header <160 hex chars> --target <64 hex chars> [options]\n\n"
        << "Options:\n"
        << "  --threads <n>       Native yespower worker threads (default: 1)\n"
        << "  --cpu-limit <1-100> Approximate per-worker duty cycle (default: 100)\n"
        << "  --start-nonce <n>   First nonce to scan (default: 0)\n"
        << "  --max-hashes <n>    Maximum nonce attempts for this template (default: 1000000)\n"
        << "  -h, --help          Show this help\n";
}

Options parse_args(int argc, char** argv)
{
    Options opts;
    std::string header_hex;
    std::string target_hex;

    for (int i = 1; i < argc; ++i) {
        const std::string arg{argv[i]};
        auto value = [&](const char* name) -> std::string {
            if (++i >= argc) fail(std::string("missing value for ") + name);
            return argv[i];
        };

        if (arg == "--header") header_hex = value("--header");
        else if (arg == "--target") target_hex = value("--target");
        else if (arg == "--threads") opts.threads = static_cast<unsigned int>(parse_u64(value("--threads"), "--threads"));
        else if (arg == "--cpu-limit") opts.cpu_limit = static_cast<unsigned int>(parse_u64(value("--cpu-limit"), "--cpu-limit"));
        else if (arg == "--start-nonce") {
            const uint64_t n = parse_u64(value("--start-nonce"), "--start-nonce");
            if (n > std::numeric_limits<uint32_t>::max()) fail("--start-nonce exceeds uint32 range");
            opts.start_nonce = static_cast<uint32_t>(n);
        } else if (arg == "--max-hashes") opts.max_hashes = parse_u64(value("--max-hashes"), "--max-hashes");
        else if (arg == "-h" || arg == "--help") {
            usage();
            std::exit(0);
        } else {
            fail("unknown option: " + arg);
        }
    }

    if (header_hex.empty()) fail("--header is required");
    if (target_hex.empty()) fail("--target is required");
    if (opts.threads < 1 || opts.threads > 256) fail("--threads must be between 1 and 256");
    if (opts.cpu_limit < 1 || opts.cpu_limit > 100) fail("--cpu-limit must be between 1 and 100");
    if (opts.max_hashes < 1) fail("--max-hashes must be greater than zero");

    try {
        opts.header = parse_hex_exact<80>(header_hex);
        opts.target_be = parse_hex_exact<32>(target_hex);
    } catch (const std::exception& e) {
        fail(e.what());
    }
    return opts;
}

bool meets_target(const yespower_binary_t& hash, const std::array<unsigned char, 32>& target_be)
{
    // CBlockHeader::GetHash() copies yespower's 32 output bytes directly into
    // uint256, whose display form reverses the internal little-endian byte array.
    for (size_t i = 0; i < 32; ++i) {
        const unsigned char display_byte = hash.uc[31 - i];
        if (display_byte < target_be[i]) return true;
        if (display_byte > target_be[i]) return false;
    }
    return true;
}

std::string display_hash(const yespower_binary_t& hash)
{
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (int i = 31; i >= 0; --i) out << std::setw(2) << static_cast<unsigned int>(hash.uc[i]);
    return out.str();
}

void set_nonce(std::array<unsigned char, 80>& header, uint32_t nonce)
{
    header[76] = static_cast<unsigned char>(nonce & 0xffU);
    header[77] = static_cast<unsigned char>((nonce >> 8) & 0xffU);
    header[78] = static_cast<unsigned char>((nonce >> 16) & 0xffU);
    header[79] = static_cast<unsigned char>((nonce >> 24) & 0xffU);
}

} // namespace

int main(int argc, char** argv)
{
    const Options opts = parse_args(argc, argv);

    static constexpr unsigned char PERS[] = "Crakbit-Core-v0.1";
    const yespower_params_t params{
        YESPOWER_1_0,
        2048,
        8,
        reinterpret_cast<const uint8_t*>(PERS),
        sizeof(PERS) - 1,
    };

    const uint64_t nonce_capacity = static_cast<uint64_t>(std::numeric_limits<uint32_t>::max()) - opts.start_nonce + 1ULL;
    const uint64_t total_budget = std::min(opts.max_hashes, nonce_capacity);
    constexpr uint64_t CHUNK = 32;

    std::atomic<uint64_t> next_index{0};
    std::atomic<uint64_t> attempts{0};
    std::atomic<bool> found{false};
    std::mutex result_mutex;
    uint32_t found_nonce = 0;
    std::string found_hash;
    std::atomic<bool> worker_error{false};

    auto worker = [&]() {
        std::array<unsigned char, 80> header = opts.header;
        while (!found.load(std::memory_order_relaxed)) {
            const uint64_t begin = next_index.fetch_add(CHUNK, std::memory_order_relaxed);
            if (begin >= total_budget) break;
            const uint64_t end = std::min(begin + CHUNK, total_budget);
            const auto started = std::chrono::steady_clock::now();

            for (uint64_t index = begin; index < end && !found.load(std::memory_order_relaxed); ++index) {
                const uint32_t nonce = static_cast<uint32_t>(static_cast<uint64_t>(opts.start_nonce) + index);
                set_nonce(header, nonce);

                yespower_binary_t hash{};
                if (yespower_tls(header.data(), header.size(), &params, &hash) != 0) {
                    worker_error.store(true, std::memory_order_relaxed);
                    found.store(true, std::memory_order_relaxed);
                    break;
                }
                attempts.fetch_add(1, std::memory_order_relaxed);

                if (meets_target(hash, opts.target_be)) {
                    bool expected = false;
                    if (found.compare_exchange_strong(expected, true)) {
                        std::lock_guard<std::mutex> guard(result_mutex);
                        found_nonce = nonce;
                        found_hash = display_hash(hash);
                    }
                    break;
                }
            }

            if (opts.cpu_limit < 100 && !found.load(std::memory_order_relaxed)) {
                const auto elapsed = std::chrono::steady_clock::now() - started;
                const auto elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count();
                if (elapsed_ns > 0) {
                    const long double ratio = static_cast<long double>(100 - opts.cpu_limit) / opts.cpu_limit;
                    const auto sleep_ns = static_cast<long long>(static_cast<long double>(elapsed_ns) * ratio);
                    if (sleep_ns > 0) std::this_thread::sleep_for(std::chrono::nanoseconds(sleep_ns));
                }
            }
        }
    };

    std::vector<std::thread> workers;
    workers.reserve(opts.threads);
    for (unsigned int i = 0; i < opts.threads; ++i) workers.emplace_back(worker);
    for (auto& thread : workers) thread.join();

    if (worker_error.load()) {
        std::cerr << "crakminer-scan: yespower_tls failed\n";
        return 1;
    }

    if (!found_hash.empty()) {
        std::cout << "nonce=" << found_nonce
                  << " hash=" << found_hash
                  << " attempts=" << attempts.load() << '\n';
        return 0;
    }

    std::cout << "not-found attempts=" << attempts.load() << '\n';
    return 2;
}
