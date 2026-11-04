"""Shared pytest fixtures, including a tiny local file server."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest

from bot.config import Config


# ---------------------------------------------------------------------------
# config / downloader
# ---------------------------------------------------------------------------
@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config.from_dict(
        {
            "token": "123456789:testTokenForUnitTests",
            "download_dir": str(tmp_path / "downloads"),
            "max_file_size_mb": 2,
            "keep_downloaded_files": True,
        }
    )


# ---------------------------------------------------------------------------
# local HTTP server
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    files: dict = {}
    support_head = True

    def log_message(self, *args):  # silence the default stderr logging
        pass

    def _payload_for(self, path: str):
        return self.files.get(path)

    def do_HEAD(self):  # noqa: N802 - http.server API
        if not self.support_head:
            self.send_response(405)
            self.end_headers()
            return
        payload = self._payload_for(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return
        body, content_type, filename = payload
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        payload = self._payload_for(self.path)
        if payload is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>not found</body></html>")
            return
        body, content_type, filename = payload
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def file_server():
    """Serve in-memory files: ``server.add('/a.mp4', b'...', 'video/mp4', 'a.mp4')``."""
    handler = type("Handler", (_Handler,), {"files": {}})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    class Server:
        base_url = f"http://127.0.0.1:{httpd.server_address[1]}"

        def add(self, path: str, body: bytes, content_type: str = "application/octet-stream",
                filename: str | None = None, *, head: bool = True) -> str:
            handler.files[path] = (body, content_type, filename)
            handler.support_head = head
            return self.base_url + path

        def stop(self) -> None:
            httpd.shutdown()
            httpd.server_close()

    server = Server()
    try:
        yield server
    finally:
        server.stop()
