# Performance Guide

## How Speed Is Determined

Distributed inference speed is bottlenecked by the **slowest link** in the chain:

```
tokens/sec = min(compute_capacity, network_bandwidth / activation_size)
```

Between every transformer layer, the active node must transmit the **hidden state
activation tensor** to the next node. For a 70B model this is typically
**4-16 MB per token** across the network boundary.

---

## Network Bandwidth Requirements by Model Size

| Model | Hidden Dim | Activation size/token | Min bandwidth needed |
|-------|-----------|----------------------|----------------------|
| 7B    | 4096      | ~4 MB                | ~100 Mb/s (fast WiFi ok) |
| 13B   | 5120      | ~6 MB                | ~200 Mb/s            |
| 30B   | 7168      | ~8 MB                | ~400 Mb/s (GbE min)  |
| 70B   | 8192      | ~16 MB               | ~800 Mb/s (GbE+)     |
| 405B  | 16384     | ~32 MB               | ~2.5 Gb/s (10GbE)    |

---

## Real-World Throughput Expectations

### Wired Ethernet

| Setup | Model | tokens/sec |
|-------|-------|-----------|
| 2× modern CPUs, GbE  | 7B Q4  | 10–25 |
| 4× modern CPUs, GbE  | 70B Q4 | 5–15  |
| 2× RTX 4090, GbE     | 70B Q4 | 20–40 |
| 4× RTX 4090, 10GbE   | 70B Q4 | 40–80 |
| 8× A100 80GB, InfiniBand | 70B | 100+  |

### Wireless (WiFi)

| Standard | Theoretical | Real-world | 70B feasible? |
|----------|------------|------------|---------------|
| WiFi 5 (802.11ac) | 3.5 Gbps | 200–400 Mb/s | Marginal (1–4 tok/s) |
| WiFi 6 (802.11ax) | 9.6 Gbps | 600–1200 Mb/s | Yes (3–8 tok/s) |
| WiFi 6E (6GHz)    | 9.6 Gbps | 800–2000 Mb/s | Yes (5–10 tok/s) |
| WiFi 7 (802.11be) | 46 Gbps  | 2–5 Gbps     | Good (8–20 tok/s) |

> **Note**: WiFi is half-duplex and subject to interference, congestion, and
> distance degradation. Measured performance will vary significantly from these
> estimates. A busy 2.4GHz environment can drop to <50 Mb/s effective throughput.

---

## Latency vs Throughput

Distributed inference has two distinct performance dimensions:

- **Time to first token (TTFT)**: Limited by the full pipeline latency.
  Each hop across the network adds 1–10ms. For 4 workers that's 4–40ms
  of unavoidable latency on top of compute.

- **Throughput (tokens/sec)**: Limited by network bandwidth during generation.
  This is what you optimize by using faster network hardware.

For **interactive chat** the TTFT matters most. For **batch processing** the
steady-state tokens/sec matters most.

---

## Optimization Tips

### 1. Use wired connections where possible
Even a single wired GbE node as the orchestrator with WiFi workers is better
than all-WiFi.

### 2. Use 5 GHz or 6 GHz bands
2.4 GHz has far more interference and lower bandwidth. Force your cluster
traffic onto 5 GHz or 6 GHz only.

### 3. Quantization matters more than model size
A 70B Q2_K model can outperform a 70B Q8_0 model in speed while using 4×
less bandwidth. Use Q4_K_M as a good quality/speed balance.

### 4. Parallelize via --parallel, not more workers
If you have enough combined RAM, increasing `--parallel` allows multiple
users to be served simultaneously without more network overhead.

### 5. Batched inference
The llama-server supports batching: multiple requests share the same
forward pass, dramatically improving GPU utilization with no extra network cost.

### 6. Place the model file on an SSD
Model loading time (cold start) is disk-bound. An NVMe SSD vs HDD can be
the difference between a 10-second and 3-minute startup.

---

## When NOT to Use Distributed Mode

- You can fit the model on a single machine → run it locally (faster)
- You only have WiFi 5 or older → latency and bandwidth will be prohibitive
  for models > 13B
- You're doing single-token generation / autocomplete → pipeline overhead
  dominates, local is always faster
- Your model is < 7B → just use one machine

## When Distributed Makes Sense

- The model doesn't fit in a single machine's RAM/VRAM
- You have 4+ machines with 32GB+ RAM each and want to run a 70B+ model
- You have a mix of GPU machines and want to pool their VRAM
- You want fault-tolerant inference (orchestrator can route around failed workers)
