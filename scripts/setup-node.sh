#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup-node.sh  –  First-time setup for any node in the LLM cluster
#
# Installs: Docker, Docker Compose, Avahi (mDNS), NVIDIA container toolkit
#           (if GPU detected), and opens the required firewall ports.
#
# Usage:
#   chmod +x scripts/setup-node.sh
#   sudo ./scripts/setup-node.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

[ "$EUID" -eq 0 ] || err "Please run as root (sudo $0)"

OS=$(. /etc/os-release && echo "$ID")
log "Detected OS: $OS"

# ── Docker ────────────────────────────────────────────────────────────────────
if command -v docker &>/dev/null; then
    log "Docker already installed: $(docker --version)"
else
    log "Installing Docker…"
    if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
        apt-get update -q
        apt-get install -y ca-certificates curl gnupg lsb-release
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
            > /etc/apt/sources.list.d/docker.list
        apt-get update -q
        apt-get install -y docker-ce docker-ce-cli containerd.io \
                           docker-buildx-plugin docker-compose-plugin
    elif [[ "$OS" == "fedora" || "$OS" == "centos" || "$OS" == "rhel" ]]; then
        dnf -y install dnf-plugins-core
        dnf config-manager --add-repo \
            https://download.docker.com/linux/fedora/docker-ce.repo
        dnf -y install docker-ce docker-ce-cli containerd.io \
                       docker-buildx-plugin docker-compose-plugin
        systemctl enable --now docker
    elif [[ "$OS" == "arch" ]]; then
        pacman -Sy --noconfirm docker docker-compose
        systemctl enable --now docker
    else
        warn "Unknown distro – install Docker manually: https://docs.docker.com/engine/install/"
    fi
fi

# Add current user to docker group
if [ -n "${SUDO_USER:-}" ]; then
    usermod -aG docker "$SUDO_USER"
    log "Added $SUDO_USER to docker group (re-login required)"
fi

# ── Avahi / mDNS ──────────────────────────────────────────────────────────────
log "Installing Avahi for mDNS discovery…"
if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
    apt-get install -y -q avahi-daemon avahi-utils libnss-mdns
    sed -i 's/^#host-name=.*/host-name='"$(hostname)"'/' /etc/avahi/avahi-daemon.conf
    systemctl enable --now avahi-daemon
elif [[ "$OS" == "fedora" || "$OS" == "centos" || "$OS" == "rhel" ]]; then
    dnf -y install avahi nss-mdns
    systemctl enable --now avahi-daemon
elif [[ "$OS" == "arch" ]]; then
    pacman -Sy --noconfirm avahi nss-mdns
    systemctl enable --now avahi-daemon
fi

# ── Firewall ports ────────────────────────────────────────────────────────────
log "Opening firewall ports…"
PORTS=(50052 8080 8888 8765)
if command -v ufw &>/dev/null; then
    for p in "${PORTS[@]}"; do ufw allow "$p"/tcp; done
    ufw allow 5353/udp   # mDNS
    ufw --force enable
    log "ufw rules applied"
elif command -v firewall-cmd &>/dev/null; then
    for p in "${PORTS[@]}"; do
        firewall-cmd --permanent --add-port="$p"/tcp
    done
    firewall-cmd --permanent --add-port=5353/udp
    firewall-cmd --reload
    log "firewalld rules applied"
else
    warn "No firewall manager found – open ports manually: ${PORTS[*]} + 5353/udp"
fi

# ── NVIDIA container toolkit (if GPU present) ─────────────────────────────────
if lspci 2>/dev/null | grep -qi nvidia; then
    log "NVIDIA GPU detected – installing container toolkit…"
    if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            > /etc/apt/sources.list.d/nvidia-container-toolkit.list
        apt-get update -q
        apt-get install -y nvidia-container-toolkit
        nvidia-ctk runtime configure --runtime=docker
        systemctl restart docker
        log "NVIDIA container toolkit installed"
    else
        warn "Install NVIDIA container toolkit manually for your distro:"
        warn "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    fi
else
    log "No NVIDIA GPU detected – CPU-only mode"
fi

log ""
log "══════════════════════════════════════════════════════"
log "  Setup complete! Next steps:"
log ""
log "  1. Copy the env template:"
log "     cp .env.example .env && nano .env"
log ""
log "  2. Start as a WORKER node:"
log "     cd worker && docker compose up -d"
log ""
log "  3. OR start as the ORCHESTRATOR node:"
log "     cd orchestrator && docker compose up -d"
log ""
log "  See docs/network-setup.md for detailed instructions."
log "══════════════════════════════════════════════════════"
