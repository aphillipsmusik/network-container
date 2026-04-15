"""
Entry point for the Windows Orchestrator application.
Bootstraps logging, loads config, and launches the GUI.
"""
import logging
import sys
from pathlib import Path


def _setup_logging():
    log_dir = Path.home() / "AppData" / "Local" / "LLMCluster"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "orchestrator.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    _setup_logging()
    log = logging.getLogger(__name__)
    log.info("LLM Cluster Orchestrator starting")

    # Deferred import so logging is configured first
    from gui import OrchestratorApp

    app = OrchestratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
