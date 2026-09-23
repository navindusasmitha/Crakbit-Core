# Public Crakbit Testnet deployment runbook

This runbook turns a CI-verified Crakbit Testnet v0.1 build into a small public development network. It does **not** authorize mainnet.

## Minimum topology

Use at least two independently hosted nodes before calling the network public:

- **seed-a** — public P2P node, TCP 29111 open;
- **seed-b** — public P2P node on a different provider/network, TCP 29111 open;
- optional pool/explorer host — preferably separate from the seed nodes.

Never expose RPC 29110 to the public Internet. The installer binds RPC to `127.0.0.1`.

## 1. Require green CI first

The `Crakbit testnet build` workflow must pass all of these stages:

1. monetary-policy tests;
2. pinned WAM-reference checkout and Crakbit transform;
3. deterministic genesis generation;
4. node/CLI/wallet/miner build;
5. miner RandomX self-test;
6. pool native RandomX build + accounting tests;
7. explorer JavaScript parse check;
8. isolated node start;
9. block-0 hash equality between node and genesis artifact.

Download the `crakbit-testnet-linux` artifact from the exact green commit. Do not mix binaries from different workflow runs.

## 2. Verify artifacts

On each host, verify `SHA256SUMS` before installation. Both seed nodes must run binaries from the same Crakbit source commit and the same generated testnet genesis.

Record:

- Crakbit repository commit;
- pinned WAM reference commit;
- generated genesis hash;
- binary SHA-256 hashes;
- host/provider and public P2P address.

## 3. Install seed-a

Build or copy the verified `build/dist/` directory, then from the repository checkout:

```bash
sudo bash deploy/install-testnet-node.sh
```

Open **TCP 29111 only** in the host firewall/security group.

Verify locally:

```bash
sudo -u crakbit /opt/crakbit-testnet/bin/crakbit-cli \
  -datadir=/var/lib/crakbit-testnet \
  -conf=/etc/crakbit/testnet.conf \
  getblockchaininfo
```

## 4. Install seed-b

On a separate server, set seed-a explicitly:

```bash
sudo CRAKBIT_ADDNODE=SEED_A_IP:29111 bash deploy/install-testnet-node.sh
```

After both nodes are up, verify peer connectivity and that `getblockhash 0` is identical.

## 5. Mine bootstrap blocks

Use only Crakbit Testnet addresses. Start with low-value test mining and allow the network to cross at least one full testnet RandomX epoch boundary (256 blocks). Validate:

- blocks are accepted by both nodes;
- subsidy and treasury outputs match policy;
- difficulty retargets every block as intended;
- both nodes remain on the same best chain;
- restart/reindex does not change chain interpretation;
- wallet send/receive and coinbase maturity work;
- pool balances survive restart;
- explorer tip/hash agrees with the nodes.

## 6. Pool and explorer

Use `scripts/pool-testnet.sh` and `scripts/explorer-testnet.sh` from the same repository commit. Keep pool wallet/RPC credentials out of the repository. The public explorer may expose chain data, but node RPC credentials must remain private.

## 7. Public announcement gate

Publish the testnet only after:

- two independent nodes have reproduced the same genesis;
- at least 256 accepted blocks have exercised a RandomX epoch transition;
- a node restart and reindex succeed;
- pool accounting tests and a real test payout succeed;
- explorer and node tips agree;
- no WAM peer, port, seed or address namespace is reachable through Crakbit configuration;
- the exact source commit and genesis hash are published.

## Reset policy

Testnet may be reset when consensus code changes. A reset requires a new testnet version label, new genesis domain/phrase and explicit announcement. Never silently reuse the same testnet identity for incompatible consensus rules.
