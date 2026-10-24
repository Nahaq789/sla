import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import callback


@pytest.fixture
def server():
    """受け取ったリクエストを記録し、statuses の順に応答する HTTP サーバー。"""
    received = []
    statuses = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append(json.loads(self.rfile.read(length)))
            self.send_response(statuses.pop(0) if statuses else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/", received, statuses
    httpd.shutdown()


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(callback, "RETRY_WAIT_SECONDS", (0, 0, 0))


def test_post_result_sends_json(server):
    url, received, _ = server

    assert callback.post_result(url, {"status": "done", "summary": "日本語"}) is True
    assert received == [{"status": "done", "summary": "日本語"}]


def test_post_result_retries_until_success(server):
    url, received, statuses = server
    statuses.extend([500, 503])

    assert callback.post_result(url, {"status": "done"}) is True
    assert len(received) == 3


def test_post_result_gives_up_without_raising(server):
    url, received, statuses = server
    statuses.extend([500, 500, 500])

    assert callback.post_result(url, {"status": "done"}) is False
    assert len(received) == 3
