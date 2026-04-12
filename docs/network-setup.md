# Network Setup Guide

## Overview

The cluster uses two network protocols:

1. **mDNS (multicast DNS)** – automatic node discovery, no configuration needed
2. **TCP** – all data transfer (activations, model weights, API calls)

```
┌──────────────────────────────────────────────────────────┐
│                      Local Network                        │
│                                                          │
│   ┌─────────────┐     mDNS       ┌──────────────────┐   │
│   │  Orchestrator│◄──────────────►│  Worker Node 1   │   │
│   │             │                │  (RPC:50052)      │   │
│   │  :8080 API  │◄──TCP──────────│  (sidecar:8765)   │   │
│   │  :8888 mgmt │                └──────────────────┘   │
│   └─────────────┘                                        │
│          ▲              mDNS      ┌──────────────────┐   │
│          └────────────────────────│  Worker Node 2   │   │
│                        TCP  ──────│  (RPC:50052)     │   │
│                                  └──────────────────┘   │
│                                                          │
│                             ┌──────────────────┐        │
│                             │  Worker Node N   │        │
│                             └──────────────────┘        │
└──────────────────────────────────────────────────────────┘
```

---

## Ports Required

| Port  | Protocol | Service          | Who opens it |
|-------|----------|------------------|--------------|
| 50052 | TCP      | llama-rpc-server | Every worker |
| 8080  | TCP      | llama-server API | Orchestrator |
| 8888  | TCP      | Management API   | Orchestrator |
| 8765  | TCP      | Worker sidecar   | Every worker |
| 5353  | UDP      | mDNS (multicast) | All nodes    |

---

## Step-by-Step Setup

### Prerequisites (all nodes)

1. Run the setup script:
   ```bash
   sudo ./scripts/setup-node.sh
   ```
   This installs Docker, Avahi (mDNS daemon), and opens firewall ports.

2. Re-login so your user is in the `docker` group:
   ```bash
   newgrp docker
   # or log out and back in
   ```

---

### Setting Up Worker Nodes

Run these steps on **every machine that contributes compute/RAM**:

```bash
# 1. Copy env template
cp .env.example worker/.env
nano worker/.env

# Set at minimum:
# NODE_NAME=worker-macbook-pro      # unique name
# ADVERTISE_IP=192.168.1.102        # this machine's LAN IP

# 2. Start the worker
cd worker
docker compose up -d

# 3. Verify it's running
curl http://localhost:8765/health
```

The worker will automatically advertise itself via mDNS. No further
configuration is needed on the worker side.

---

### Setting Up the Orchestrator Node

Run these steps on **one machine** (the one with the model file):

```bash
# 1. Download a model (if you don't have one)
./scripts/download-model.sh llama3-70b Q4_K_M /models

# 2. Configure the orchestrator
cp .env.example orchestrator/.env
nano orchestrator/.env

# Set at minimum:
# MODEL_PATH=/models/Meta-Llama-3-70B-Instruct-Q4_K_M.gguf
# MODEL_DIR=/models

# 3. Start the orchestrator
cd orchestrator
docker compose up -d

# 4. Check the cluster health
./scripts/health-check.sh localhost
```

The orchestrator will wait 10–15 seconds for workers to announce themselves,
then launch llama-server with all discovered workers as `--rpc` backends.

---

### Verifying Discovery

Check which workers the orchestrator has found:

```bash
curl http://localhost:8888/workers | python3 -m json.tool
```

If workers are missing:

1. Confirm Avahi is running on all nodes: `systemctl status avahi-daemon`
2. Test mDNS from the orchestrator: `avahi-browse -t _llama-rpc._tcp`
3. Check firewall on the worker: port 5353/UDP and 50052/TCP must be open
4. Verify `ADVERTISE_IP` in the worker's `.env` is reachable from the orchestrator

---

## Wireless-Specific Configuration

### Force 5 GHz / 6 GHz Band

Edit `/etc/NetworkManager/system-connections/<your-wifi>.nmconnection`:

```ini
[wifi]
band=a          # "a" = 5GHz, omit for auto
channel=0       # 0 = auto
```

Or use nmcli:
```bash
nmcli connection modify "YourSSID" wifi.band a
nmcli connection up "YourSSID"
```

### Disable WiFi Power Management

Power management can introduce 50–200ms latency spikes:

```bash
# Disable for current session
sudo iwconfig wlan0 power off

# Persist across reboots
echo 'ACTION=="add", SUBSYSTEM=="net", KERNEL=="wlan*", RUN+="/sbin/iwconfig %k power off"' \
  | sudo tee /etc/udev/rules.d/70-wifi-power.rules
```

### Use QoS to Prioritize Cluster Traffic

On Linux (for wired + wireless):

```bash
# Prioritize traffic to/from cluster nodes (replace with your subnet)
sudo tc qdisc add dev wlan0 root handle 1: prio
sudo tc filter add dev wlan0 parent 1:0 protocol ip prio 1 u32 \
     match ip dst 192.168.1.0/24 flowid 1:1
```

### Check WiFi Signal Quality

```bash
watch -n 1 'iwconfig wlan0 | grep -E "Signal|Bit Rate|Link"'
```

For reliable distributed inference, aim for:
- Signal level: > -65 dBm
- Bit Rate: > 300 Mb/s (displayed rate)
- Link Quality: > 70/70

---

## Troubleshooting

### "No workers found" on orchestrator

```bash
# Check mDNS is working
avahi-browse -t _llama-rpc._tcp

# Manually ping the worker's RPC port
nc -zv <worker-ip> 50052

# Check worker logs
docker logs llama-rpc-worker
```

### Slow inference (< 1 tok/s)

- Check network speed between nodes: `iperf3 -s` on one, `iperf3 -c <ip>` on other
- If < 200 Mb/s, the network is the bottleneck
- Consider wired ethernet or a dedicated WiFi 6 router for cluster traffic

### Worker shows as stale

The orchestrator marks workers stale after 90 seconds without a heartbeat.

```bash
# Check if mDNS heartbeat is being sent
docker logs llama-rpc-worker | grep heartbeat

# Restart the worker
docker restart llama-rpc-worker
```

### llama-server won't start

```bash
# Check orchestrator logs
docker logs llama-orchestrator

# Verify the model file exists and is readable
ls -lh /models/*.gguf

# Test llama-server directly (outside Docker)
llama-server --model /models/your-model.gguf --host 0.0.0.0 --port 8080
```

### Force restart with current workers

```bash
curl -X POST http://localhost:8888/restart
```
