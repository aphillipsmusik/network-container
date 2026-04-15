"""Orchestrator Windows app – configuration."""
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
import json

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "LLMCluster"
CONFIG_FILE = CONFIG_DIR / "orchestrator.json"


def _default_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@dataclass
class OrchestratorConfig:
    node_name: str = ""
    advertise_ip: str = ""
    model_path: str = ""
    llama_server_port: int = 8080
    mgmt_port: int = 8888
    gpu_layers: int = 0
    context_size: int = 4096
    parallel: int = 4
    worker_stale_timeout: int = 90
    discovery_timeout: int = 10
    auto_start: bool = True
    install_dir: str = ""

    def __post_init__(self):
        if not self.node_name:
            self.node_name = f"orchestrator-{socket.gethostname()}"
        if not self.advertise_ip:
            self.advertise_ip = _default_ip()
        if not self.install_dir:
            self.install_dir = str(
                Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "LLMCluster"
            )

    @property
    def inference_url(self) -> str:
        return f"http://{self.advertise_ip}:{self.llama_server_port}"

    @property
    def mgmt_url(self) -> str:
        return f"http://localhost:{self.mgmt_port}"


def load() -> OrchestratorConfig:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            return OrchestratorConfig(**{
                k: v for k, v in data.items()
                if k in OrchestratorConfig.__dataclass_fields__
            })
        except Exception:
            pass
    return OrchestratorConfig()


def save(cfg: OrchestratorConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(asdict(cfg), f, indent=2)
