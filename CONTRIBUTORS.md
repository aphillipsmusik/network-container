# Contributors

This project recognizes two categories of contribution: **code** and **compute**.
Both are essential — the software is nothing without nodes, and nodes are nothing
without the software.

---

## Project Founder

| Name | GitHub | Role |
|------|--------|------|
| A. Phillips | [@aphillipsmusik](https://github.com/aphillipsmusik) | Founder, architect |

---

## Code Contributors

People who have contributed to the software, documentation, or tooling.

| Name | GitHub | Contributions |
|------|--------|---------------|
| A. Phillips | [@aphillipsmusik](https://github.com/aphillipsmusik) | Core architecture, Windows installer, governance |

> To appear here: open a pull request. All accepted PRs earn a listing.

---

## Compute Contributors

People who run public worker or orchestrator nodes, contributing RAM, VRAM,
and bandwidth to open clusters.

Compute contributors are recognized by their **node tier**, based on the
RAM they consistently make available to the network.

| Tier | RAM contributed | Badge |
|------|----------------|-------|
| Seed | 8–15 GB | 🌱 |
| Node | 16–31 GB | ⬡ |
| Core | 32–63 GB | ◈ |
| Backbone | 64–127 GB | ◉ |
| Anchor | 128 GB+ | ★ |

### Active Compute Contributors

| Node name | Operator | Tier | RAM | GPU | Since |
|-----------|----------|------|-----|-----|-------|
| *(none yet — be the first)* | | | | | |

> To be listed: run a public worker node for at least 7 consecutive days,
> then open an issue titled `[compute] add node – <your-node-name>` with
> your node name, average RAM available, and contact handle.

---

## Governance Note

In keeping with the [no-51% rule](GOVERNANCE.md), no single compute contributor
may account for more than 51% of a cluster's total active RAM. The contributor
table is a record of participation — not a ranking of authority.

The more contributors listed here, the healthier the network.

---

## How to Contribute

### Code
1. Fork the repo
2. Create a branch: `git checkout -b feature/your-thing`
3. Open a pull request against `main`
4. PRs that increase decentralization, improve worker autonomy, or reduce
   orchestrator authority are prioritized

### Compute
1. Run `scripts/setup-node.sh` (Linux/Mac) or the Windows installer
2. Start a worker: `cd worker && docker compose up -d`
3. Keep it running on your local network or make it publicly reachable
4. Open an issue to be listed above

### Documentation, Testing, Issues
All welcome — open an issue or PR. No contribution is too small.
