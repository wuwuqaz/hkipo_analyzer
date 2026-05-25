import os
import json
import pytest
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"


def _find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, expected_text: str, timeout: float = 90.0) -> str:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
                if expected_text in body:
                    return body
                last_error = AssertionError(f"Expected '{expected_text}' in response body")
        except (urllib.error.URLError, OSError, AssertionError) as exc:
            last_error = exc
        time.sleep(1)

    raise AssertionError(f"{url} did not become ready: {last_error}")


class _FakeApiHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            payload = {
                "status": "ok",
                "db_status": "ok",
                "worker_status": "idle",
                "uptime_seconds": 1.0,
            }
        elif self.path == "/api/version":
            payload = {
                "app_version": "0.1.0",
                "python_version": "3.11 (cpython)",
                "ipo_analyzer_version": "0.5.0-alpha",
            }
        else:
            self.send_response(404)
            self.end_headers()
            return

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def test_frontend_homepage_smoke():
    import shutil
    if shutil.which("npm") is None:
        pytest.skip("npm not found in PATH")
    if not (FRONTEND_DIR / "node_modules").exists():
        pytest.skip("frontend/node_modules not found; run npm install first")
    # Avoid port conflicts with an existing Next.js dev server.
    subprocess.run(["pkill", "-f", "next dev"], capture_output=True)
    time.sleep(1)
    frontend_port = _find_free_port()
    api_port = _find_free_port()

    api_server = ThreadingHTTPServer(("127.0.0.1", api_port), _FakeApiHandler)
    api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
    api_thread.start()

    frontend_env = os.environ.copy()
    frontend_env["NEXT_PUBLIC_API_URL"] = f"http://127.0.0.1:{api_port}/api"

    frontend_process = subprocess.Popen(
        [
            "npm",
            "run",
            "dev",
            "--",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(frontend_port),
        ],
        cwd=FRONTEND_DIR,
        env=frontend_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_http(f"http://127.0.0.1:{api_port}/api/health", '"status": "ok"', timeout=10.0)
        body = _wait_for_http(f"http://127.0.0.1:{frontend_port}/", "HK IPO Analyzer", timeout=90.0)
        assert "HK IPO Analyzer" in body
    finally:
        frontend_process.terminate()
        frontend_process.wait(timeout=10)
        api_server.shutdown()
        api_server.server_close()
