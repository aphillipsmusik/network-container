# network-container

A distributed LLM inference cluster that pools the RAM, VRAM, and compute of
multiple machines — wired or wireless — to run large language models that
wouldn't fit on any single machine.

Built on [llama.cpp](https://github.com/ggerganov/llama.cpp)'s RPC backend,
containerized with Docker, with automatic node discovery via mDNS.

```
          Your Network
    ┌─────────────────────────────────────────────────┐
    │                                                 │
    │  ┌──────────────────┐    ┌──────────────────┐   │
    │  │   Orchestrator   │    │   Worker Node 1  │   │
    │  │                  │◄──►│   32 GB RAM      │   │
    │  │  llama-server    │    │   RTX 3090 24GB  │   │
    │  │  OpenAI API :8080│    └──────────────────┘   │
    │  │  Mgmt API  :8888 │                           │
    │  │  model.gguf      │    ┌──────────────────┐   │
    │  │                  │◄──►│   Worker Node 2  │   │
    │  └──────────────────┘    │   64 GB RAM      │   │
    │                          │   CPU only       │   │
    │                          └──────────────────┘   │
    │                                                 │
    │  ← auto-discovered via mDNS, no config needed → │
    └─────────────────────────────────────────────────┘
```

---

## How It Works

**llama.cpp RPC** treats remote machines as additional compute backends
(like extra GPUs). The orchestrator holds the model file and distributes
tensor computations across all worker nodes. The combined RAM/VRAM of all
nodes determines the maximum model size you can run.

- **Workers** run `llama-rpc-server` and advertise themselves on the network
  via mDNS (no manual IP configuration needed)
- **Orchestrator** discovers workers automatically, builds the `--rpc` flag
  list, and launches `llama-server` with an OpenAI-compatible API
- When workers join or leave, the inference server restarts automatically

---

## Requirements

| Node type    | Minimum                        | Recommended              |
|-------------|-------------------------------|--------------------------|
| Orchestrator | 8 GB RAM, model file on disk  | SSD, 32+ GB RAM          |
| Worker       | 8 GB RAM, Docker              | 32+ GB RAM, NVIDIA GPU   |
| Network      | WiFi 6 / 100 Mb/s ethernet   | Gigabit ethernet         |

> **Wireless note**: WiFi works but limits throughput. Expect 1–8 tokens/sec
> for 70B models over WiFi 6. Gigabit ethernet gives 5–20 tokens/sec for the
> same setup. See [docs/performance.md](docs/performance.md) for details.

---

## Quick Start

### 1. First-time setup (all nodes)

```bash
git clone https://github.com/aphillipsmusik/network-container
cd network-container
sudo ./scripts/setup-node.sh
```

### 2. Start worker nodes (every contributing machine)

```bash
# Configure
cp .env.example worker/.env
nano worker/.env      # set NODE_NAME and ADVERTISE_IP

# Start
cd worker
docker compose up -d

# Verify
curl http://localhost:8765/health
```

### 3. Start the orchestrator (one machine with the model)

```bash
# Download a model (or skip if you have one)
./scripts/download-model.sh llama3-70b Q4_K_M /models

# Configure
cp .env.example orchestrator/.env
nano orchestrator/.env    # set MODEL_PATH and MODEL_DIR

# Start
cd orchestrator
docker compose up -d

# Check cluster
./scripts/health-check.sh
```

### 4. Use the API

The orchestrator exposes an **OpenAI-compatible API** on port 8080:

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 256
  }'
```

Works as a drop-in replacement for the OpenAI API in any client:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<orchestrator-ip>:8080/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="local",
    messages=[{"role": "user", "content": "Explain quantum entanglement."}]
)
print(response.choices[0].message.content)
```

---

## GPU Support

To use NVIDIA GPUs on any node, use the GPU Docker Compose override:

```bash
# Worker with GPU
cd worker
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Orchestrator with GPU
cd orchestrator
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Set `GPU_LAYERS=99` in your `.env` to offload all layers to the GPU.

---

## Management API

The orchestrator exposes a management API on port 8888:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Orchestrator status |
| `/workers` | GET | All discovered workers |
| `/workers/active` | GET | Non-stale workers + RPC endpoints |
| `/restart` | POST | Rebuild RPC list and relaunch |
| `/server/status` | GET | llama-server health |
| `/server/models` | GET | Available models |

```bash
# List active workers
curl http://localhost:8888/workers/active | python3 -m json.tool

# Force restart with current worker list
curl -X POST http://localhost:8888/restart
```

---

## Interactive Setup Wizard

Instead of manual `.env` editing, use the join wizard:

```bash
./scripts/join-cluster.sh
```

It prompts for your role (worker/orchestrator), detects your IP, writes the
`.env`, and starts Docker Compose automatically.

---

## Benchmarking

```bash
./scripts/benchmark.sh [orchestrator-ip] [port]
```

Reports tokens/sec and compares against reference hardware benchmarks.

---

## File Structure

```
network-container/
├── worker/                    # Worker node
│   ├── Dockerfile.cpu         # CPU build
│   ├── Dockerfile.gpu         # NVIDIA GPU build
│   ├── docker-compose.yml
│   ├── docker-compose.gpu.yml
│   ├── build/build-llama.sh   # Bare-metal build script
│   └── sidecar/               # Python registration service
│       ├── main.py            # mDNS advertiser + health API
│       ├── config.py
│       └── requirements.txt
│
├── orchestrator/              # Orchestrator node
│   ├── Dockerfile.cpu
│   ├── Dockerfile.gpu
│   ├── docker-compose.yml
│   ├── docker-compose.gpu.yml
│   ├── build/build-llama.sh
│   └── app/                   # Python management service
│       ├── main.py            # Entry point
│       ├── discovery.py       # mDNS worker discovery
│       ├── launcher.py        # llama-server lifecycle
│       ├── api.py             # FastAPI management API
│       ├── config.py
│       └── requirements.txt
│
├── scripts/
│   ├── setup-node.sh          # First-time node setup
│   ├── join-cluster.sh        # Interactive join wizard
│   ├── download-model.sh      # Download GGUF models
│   ├── health-check.sh        # Cluster health report
│   └── benchmark.sh           # Throughput benchmark
│
├── docs/
│   ├── performance.md         # Speed expectations by hardware
│   └── network-setup.md       # Network config + troubleshooting
│
└── .env.example               # Configuration template
```

---

## Supported Models

Any GGUF-format model works. Tested with:

- **LLaMA 3** 8B, 70B
- **Mistral** 7B
- **Phi-3** Mini
- **Qwen2** 72B
- Any model from [TheBloke](https://huggingface.co/TheBloke) or [bartowski](https://huggingface.co/bartowski) on HuggingFace

---

## Docs

- [Performance Guide](docs/performance.md) – throughput expectations, optimization tips
- [Network Setup](docs/network-setup.md) – port config, WiFi tuning, troubleshooting
