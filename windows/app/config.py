"""
Configuration – stored in %APPDATA%\LLMCluster\config.json
"""
import json
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "LLMCluster"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _default_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _default_name() -> str:
    return socket.gethostname()


@dataclass
class NodeConfig:
    role: str = "worker"
    node_name: str = ""
    advertise_ip: str = ""
    rpc_port: int = 50052
    sidecar_port: int = 8765
    llama_server_port: int = 8080
    mgmt_port: int = 8888
    model_path: str = ""
    gpu_layers: int = 0
    context_size: int = 4096
    parallel: int = 4
    auto_start: bool = True
    install_dir: str = ""

    def __post_init__(self):
        if not self.node_name:
            self.node_name = _default_name()
        if not self.advertise_ip:
            self.advertise_ip = _default_ip()
        if not self.install_dir:
            self.install_dir = str(
                Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "LLMCluster"
            )


def load() -> NodeConfig:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            return NodeConfig(**{k: v for k, v in data.items()
                                 if k in NodeConfig.__dataclass_fields__})
        except Exception:
            pass
    return NodeConfig()


def save(cfg: NodeConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(asdict(cfg), f, indent=2)
