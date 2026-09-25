// Copyright (c) 2026 The WAM Coin developers
// Copyright (c) 2026 The Crakbit developers
// Distributed under the MIT software license, see COPYING.

#ifndef WAM_CRYPTO_RANDOMX_HASH_H
#define WAM_CRYPTO_RANDOMX_HASH_H

#include <uint256.h>

#include <cstddef>

class CBlockHeader;
class CBlockIndex;
namespace Consensus { struct Params; }

namespace wam {

/**
 * Transitional API for the WAM-derived patch framework.
 *
 * The historical RandomX function names remain temporarily because the WAM
 * patch series calls them from several Bitcoin Core integration points. Their
 * implementation is Crakbit yespower 1.0; there is no RandomX VM, cache,
 * dataset, epoch key, or seed dependency in a Crakbit proof of work.
 *
 * Block identifiers stay Bitcoin-style SHA256d. Only the target-comparison
 * proof hash is yespower.
 */
static constexpr size_t RANDOMX_INPUT_SIZE = 80; // compatibility name only

int GetRandomXSeedHeight(int nHeight, const Consensus::Params& params);
uint256 GetRandomXBootstrapSeed();
uint256 GetRandomXSeedHash(const CBlockIndex* pindexPrev, const Consensus::Params& params);

/** Crakbit yespower hash of the serialized 80-byte block header. `seed` ignored. */
uint256 GetRandomXPoWHash(const CBlockHeader& header, const uint256& seed);

/** Crakbit yespower hash of arbitrary input. `seed` ignored. */
uint256 GetRandomXHashRaw(const unsigned char* input, size_t len, const uint256& seed);

/** Compatibility no-op: yespower does not have light/full dataset modes. */
void SetRandomXMiningMode(bool fMining);

/** Compatibility no-op: yespower TLS owns only small per-thread scratch memory. */
void FlushRandomXCaches();

/** Approximate per-thread yespower working memory for N=2048,r=8. */
size_t GetRandomXMemoryUsage();

} // namespace wam

#endif // WAM_CRYPTO_RANDOMX_HASH_H
