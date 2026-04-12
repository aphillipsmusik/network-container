"""
Windows Firewall helpers – uses netsh (no admin elevation needed if already elevated).
"""
import subprocess
import logging

log = logging.getLogger(__name__)

RULES = [
    ("LLM Cluster RPC",       50052, "TCP"),
    ("LLM Cluster Inference",  8080, "TCP"),
    ("LLM Cluster Mgmt",       8888, "TCP"),
    ("LLM Cluster Sidecar",    8765, "TCP"),
    ("LLM Cluster mDNS",       5353, "UDP"),
]


def _run(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception as exc:
        log.warning("firewall cmd failed: %s", exc)
        return False


def open_ports() -> list[str]:
    """Add inbound firewall rules for all cluster ports. Returns list of results."""
    results = []
    for name, port, proto in RULES:
        ok = _run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={name}",
            "dir=in",
            "action=allow",
            f"protocol={proto}",
            f"localport={port}",
            "enable=yes",
            "profile=any",
        ])
        status = "opened" if ok else "skipped/already exists"
        results.append(f"Port {port}/{proto}: {status}")
        log.info("Firewall %s/%s: %s", port, proto, status)
    return results


def close_ports() -> None:
    """Remove cluster firewall rules."""
    for name, _, _ in RULES:
        _run([
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={name}",
        ])


def is_elevated() -> bool:
    """Return True if the process has admin privileges."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
