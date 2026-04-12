# Project Governance

## Core Principles

This project is built around one foundational idea: **no single machine, person,
or entity should control the majority of a distributed AI compute cluster.**

The following principles govern how this software is designed, how clusters
built with it should be operated, and how the project itself is run.

---

## The Orchestrator Problem (Why This Matters)

In a naïve distributed LLM setup, the **orchestrator node** is all-powerful:

- It holds the model file
- It decides which workers get compute tasks
- It is the sole gateway to the inference API
- It can evict any worker at any time
- If it goes down, the entire cluster stops

This is a **51% problem** — identical in structure to the attack vector in
distributed ledger systems. A single orchestrator controlling a cluster is a
single point of authority, not a distributed system. It just looks distributed.

---

## The No-51% Rule

> **No single node, operator, or deployment may control more than 51% of
> any cluster's active compute or routing decisions.**

### What this means technically

| Situation | Allowed? |
|-----------|----------|
| 1 orchestrator + 1 worker (you own both) | ⚠ Technically fine at small scale, but you bear full authority |
| 1 orchestrator + N workers all on one machine | ✗ Violates the spirit — single point of failure and control |
| 1 orchestrator shared by a community of workers | ✓ Acceptable if orchestrator is auditable and rotatable |
| Federated orchestrators with worker quorum | ✓ Preferred model |
| Any single participant owning >51% of worker RAM/VRAM | ✗ That participant effectively controls model output quality |

### What this means for deployments

1. **Worker diversity**: A healthy cluster should have workers run by at least
   3 independent participants. Any cluster with fewer is centralized in practice.

2. **Orchestrator auditability**: The orchestrator's routing decisions and
   worker registry must be publicly visible to all cluster participants via
   the `/workers` and `/health` APIs — no hidden routing.

3. **Orchestrator replaceability**: The orchestrator is stateless by design.
   Any participant should be able to stand up a replacement orchestrator
   pointing at the same worker pool. Workers are not locked to a single
   orchestrator.

4. **No captive workers**: Workers broadcast themselves via mDNS and may
   disconnect and reconnect to any orchestrator freely. No authentication
   mechanism may be used to prevent a worker from leaving a cluster.

---

## Orchestrator Rotation

In community clusters, the orchestrator role should rotate periodically or
be governed by consensus of the worker pool.

**Recommended rotation models:**

- **Time-based**: Orchestrator role passes to the next participant every N days
- **Stake-weighted**: The participant contributing the most worker RAM earns
  orchestrator rights for that period
- **Election**: Workers vote (via the management API) to elect an orchestrator
  from candidates

The software supports all of these — orchestrators are hot-swappable without
restarting workers.

---

## Participation Rules

Anyone may contribute a worker node to a public cluster, subject to:

1. **Minimum contribution**: A worker must provide at least 8 GB of usable RAM
   to be listed in the active worker pool
2. **Honest reporting**: Workers must not misreport their RAM, VRAM, or
   GPU layer capacity
3. **Availability**: Workers are expected to maintain >80% uptime to remain
   in good standing in a community cluster
4. **No poisoning**: Workers must run unmodified llama-rpc-server binaries
   and must not inject modified tensors into the compute pipeline

---

## Project Governance (This Repository)

### Decisions

- **Architectural decisions** that affect the 51% principle or worker
  autonomy require public discussion in a GitHub Issue before merging
- **Breaking changes** to the worker–orchestrator API require a deprecation
  period of at least one release
- **New mandatory authentication** that could prevent workers from leaving
  a cluster will not be merged

### Contributions

All contributions are welcome. PRs that increase centralization of control
(e.g., mandatory central registration, closed worker allowlists) will be
declined by design — they contradict the project's core purpose.

### Philosophy

This project treats distributed AI compute the same way open networking
treats packet routing: **the infrastructure should be dumb, open, and
ungovernable by any single party.** The intelligence lives in the nodes.

---

## Summary

| Principle | Rule |
|-----------|------|
| Ownership cap | No single entity controls >51% of cluster compute |
| Orchestrator power | Orchestrators are auditable, replaceable, and rotatable |
| Worker freedom | Workers may join or leave any cluster at any time |
| Transparency | All routing and worker state is publicly visible via API |
| Minimum participation | Workers contribute ≥8 GB RAM to be active |
| Open software | No mandatory central registration or closed allowlists |
