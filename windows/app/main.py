"""
LLM Cluster Node – Windows Entry Point
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [llmcluster] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

if __name__ == "__main__":
    from gui import App
    App().run()
