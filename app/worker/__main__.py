import argparse

from app.config import load_settings
from app.worker.runner import run_worker

parser = argparse.ArgumentParser(description="Run the single durable Pathya worker")
parser.add_argument("--once", action="store_true", help="Process at most one attempt and exit")
arguments = parser.parse_args()
run_worker(load_settings(), once=arguments.once)
