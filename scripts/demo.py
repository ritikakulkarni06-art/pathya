"""Run one loopback demo API plus one durable worker; online adapters stay disabled."""

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from app.main import create_app
from app.worker.runner import child_environment, stop_process
from scripts.seed_demo import DEFAULT_DEMO_DIR, demo_settings, seed_demo


def verify_worker(client: httpx.Client, document_id: str, worker: subprocess.Popen[bytes]) -> None:
    scheduled = client.post(f"/documents/{document_id}/reindex")
    if scheduled.status_code != 202:
        raise RuntimeError("The demo API could not queue a search indexing job.")
    job_url = "/jobs/" + scheduled.json()["job_id"]
    deadline = time.monotonic() + 30
    while worker.poll() is None and time.monotonic() < deadline:
        response = client.get(job_url)
        response.raise_for_status()
        job = response.json()
        if job["state"] == "ready" and job["attempts"] == 1:
            return
        if job["state"] in {"failed", "cancelled"} or job["last_error_code"] is not None:
            break
        time.sleep(0.1)
    raise RuntimeError("The durable demo worker did not complete the search indexing job.")


def run_demo(directory: Path, port: int = 8000, *, smoke: bool = False) -> dict[str, Any]:
    if not 0 <= port <= 65535:
        raise ValueError("Choose a valid local port, or zero for a smoke-test port.")
    info = seed_demo(directory)
    settings = demo_settings(directory)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=port,
            workers=1,
            access_log=False,
            log_level="warning",
            loop="asyncio",
            timeout_graceful_shutdown=5,
        )
    )
    thread = threading.Thread(target=server.run, name="pathya-demo-api", daemon=True)
    worker: subprocess.Popen[bytes] | None = None
    try:
        thread.start()
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError(
                    "The demo API did not start. Check the selected port and local storage."
                )
            time.sleep(0.05)
        bound_port = server.servers[0].sockets[0].getsockname()[1]
        url = "http://127.0.0.1:" + str(bound_port)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        worker = subprocess.Popen(
            [sys.executable, "-m", "app.worker"],
            env=child_environment(settings),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            start_new_session=sys.platform != "win32",
        )
        with httpx.Client(
            base_url=url, trust_env=False, timeout=10, follow_redirects=False
        ) as client:
            if (
                client.get("/healthz").status_code != 200
                or client.get("/readyz").status_code != 200
            ):
                raise RuntimeError("The demo API did not pass health/readiness checks.")
            if client.get("/documents/" + info["document_id"]).status_code != 200:
                raise RuntimeError("The demo API is not serving the seeded demo chapter.")
            if smoke:
                verify_worker(client, info["document_id"], worker)
        if worker.poll() is not None:
            raise RuntimeError("The durable demo worker stopped during startup.")
        print("Synthetic demo API: " + url)
        print("Health: " + url + "/healthz")
        print("Chapter: " + url + "/documents/" + info["document_id"] + "/content")
        print("Manifest: " + url + "/documents/" + info["document_id"] + "/manifest")
        print("Demo user: local@pathya.invalid (local mode; no password)")
        print(info["notice"])
        if smoke:
            print("Demo smoke checks passed; stopping the API and worker.")
        else:
            print("Press Ctrl+C to stop the API and worker.")
            while thread.is_alive():
                if worker.poll() is not None:
                    raise RuntimeError(
                        "The demo worker stopped. Check local storage and worker configuration."
                    )
                thread.join(timeout=0.5)
        return {**info, "url": url, "smoke_passed": smoke}
    except KeyboardInterrupt:
        return {**info, "stopped": True}
    finally:
        server.should_exit = True
        if thread.ident is not None:
            thread.join(timeout=15)
        if worker is not None and worker.poll() is None:
            if sys.platform == "win32":
                stop_process(worker)
            else:
                worker.terminate()
                try:
                    worker.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    stop_process(worker)
        if thread.is_alive() or (worker is not None and worker.poll() is None):
            raise RuntimeError("The demo API or worker did not shut down cleanly.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start an isolated, offline synthetic Pathya backend demo."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DEMO_DIR)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Verify the live API and an indexing job, then stop both",
    )
    args = parser.parse_args()
    result = run_demo(args.data_dir, args.port, smoke=args.smoke)
    if args.smoke:
        print(
            json.dumps(
                {
                    "smoke_passed": result.get("smoke_passed", False),
                    "llm_enabled": False,
                    "synthetic_audio": True,
                }
            )
        )


if __name__ == "__main__":
    main()
