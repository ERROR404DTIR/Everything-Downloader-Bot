"""End-to-end smoke test against a *fake* Bale Bot API server.

This verifies the parts we cannot unit test otherwise: the ``base_url``
override of balethon, real multipart file uploads and the getUpdates loop.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from balethon import Client

from bot.handlers import BotHandlers, register

TOKEN = "123456789:fakeTokenForTheTestServer"


class FakeBaleAPI:
    """Minimal implementation of the Bale Bot API used by the bot."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []
        self.uploaded_files: list[bytes] = []
        self.sent_messages: list[dict] = []
        self.edited_messages: list[dict] = []
        self.updates: list[dict] = []
        self._update_id = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _read_body(self) -> bytes:
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def do_GET(self):  # noqa: N802
                self._handle("GET", b"")

            def do_POST(self):  # noqa: N802
                self._handle("POST", self._read_body())

            def _handle(self, method: str, body: bytes):
                parsed = urlparse(self.path)
                path = parsed.path
                if not path.startswith(f"/bot{TOKEN}/"):
                    self._json(404, {"ok": False, "error_code": 404, "description": "wrong token"})
                    return
                name = path.rsplit("/", 1)[-1]
                content_type = self.headers.get("Content-Type", "")

                payload: dict = {}
                if "multipart/form-data" in content_type:
                    outer.uploaded_files.append(body)
                    for key in (b'name="chat_id"', b'name="caption"'):
                        if key in body:
                            start = body.index(key) + len(key) + len(b'\r\n\r\n')
                            payload[key.decode().split('"')[1]] = body[start:start + 300].decode(
                                "utf-8", "ignore"
                            )
                elif body:
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError:
                        payload = {k: v[0] for k, v in parse_qs(body.decode()).items()}
                payload.update({k: v[0] for k, v in parse_qs(parsed.query).items()})
                payload["__method__"] = method

                outer.requests.append((name, {k: v for k, v in payload.items() if k != "__method__"}))
                self._route(name, payload)

            def _route(self, name: str, payload: dict):
                if name == "getMe":
                    self._json(200, {"ok": True, "result": {
                        "id": 1, "is_bot": True, "first_name": "Downloader",
                        "username": "everything_downloader_test_bot"}})
                elif name == "deleteWebhook":
                    self._json(200, {"ok": True, "result": True})
                elif name == "getUpdates":
                    update = outer.updates.pop(0) if outer.updates else None
                    if update is None:
                        self._json(200, {"ok": True, "result": []})
                        return
                    outer._update_id += 1
                    update["update_id"] = outer._update_id
                    self._json(200, {"ok": True, "result": [update]})
                elif name == "sendMessage":
                    outer.sent_messages.append(payload)
                    self._message(payload.get("text"))
                elif name == "editMessageText":
                    outer.edited_messages.append(payload)
                    self._message(payload.get("text"))
                elif name in {"sendDocument", "sendVideo", "sendAudio", "sendPhoto"}:
                    self._message(payload.get("caption"))
                elif name in {"sendChatAction", "answerCallbackQuery", "deleteMessage"}:
                    self._json(200, {"ok": True, "result": True})
                elif name == "getFile":
                    self._json(200, {"ok": True, "result": {
                        "file_id": "f", "file_size": 3, "file_path": "files/f"}})
                else:
                    self._json(200, {"ok": True, "result": True})

            def _message(self, text):
                self._json(200, {"ok": True, "result": {
                    "message_id": 1000 + len(outer.sent_messages),
                    "date": 1700000000,
                    "chat": {"id": 555, "type": "private"},
                    "text": text,
                }})

            def _json(self, code: int, data: dict):
                raw = json.dumps(data, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    # -- helpers --------------------------------------------------------
    def queue_text_message(self, text: str, chat_id: int = 555, user_id: int = 42):
        self.updates.append({
            "message": {
                "message_id": len(self.updates) + 1,
                "date": 1700000000,
                "from": {"id": user_id, "is_bot": False, "first_name": "علی"},
                "chat": {"id": chat_id, "type": "private"},
                "text": text,
            }
        })

    def methods(self) -> list[str]:
        return [name for name, _ in self.requests]

    def last_sent_text(self) -> str:
        return self.sent_messages[-1].get("text", "")


@pytest.fixture
def fake_api():
    api = FakeBaleAPI().start()
    try:
        yield api
    finally:
        api.stop()


async def run_bot_until(api: FakeBaleAPI, predicate, client: Client, handlers=None,
                        timeout: float = 20.0):
    await client.connect()
    polling = asyncio.create_task(client.start_polling())
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate():
                return
            await asyncio.sleep(0.1)
        raise AssertionError(
            f"condition not met in time; methods={api.methods()} texts={api.sent_messages}"
        )
    finally:
        polling.cancel()
        with pytest.raises(BaseException):
            await polling
        await client.disconnect()
        if handlers is not None:
            await handlers.downloader.close()


class TestBaleIntegration:
    async def test_start_command_reaches_bale_api(self, fake_api):
        fake_api.queue_text_message("/start")
        client = Client(TOKEN, base_url=fake_api.base_url)
        handlers = BotHandlers(client, _config_for(fake_api))
        register(client, handlers)

        await run_bot_until(
            fake_api,
            lambda: any("همه‌چیز دانلودر" in (m.get("text") or "") for m in fake_api.sent_messages),
            client,
            handlers,
        )

        assert "getMe" in fake_api.methods()
        assert "deleteWebhook" in fake_api.methods()
        welcome = fake_api.sent_messages[0]
        assert welcome["chat_id"] == "555" or welcome["chat_id"] == 555
        assert "همه‌چیز دانلودر" in welcome["text"]
        assert welcome.get("reply_markup")

    async def test_link_update_downloads_and_uploads_document(self, fake_api, file_server):
        body = b"%PDF-1.4 uploaded through the Bale API" * 50
        url = file_server.add("/api/report.pdf", body, "application/pdf", "report.pdf")
        fake_api.queue_text_message(url)

        client = Client(TOKEN, base_url=fake_api.base_url)
        handlers = BotHandlers(client, _config_for(fake_api))
        register(client, handlers)

        await run_bot_until(fake_api, lambda: bool(fake_api.uploaded_files), client, handlers)

        assert "sendDocument" in fake_api.methods()
        assert "sendChatAction" in fake_api.methods()
        uploaded = fake_api.uploaded_files[0]
        assert body[:40] in uploaded
        assert b'report.pdf' in uploaded or b"report" in uploaded


def _config_for(api: FakeBaleAPI):
    from bot.config import Config
    from pathlib import Path
    import tempfile

    return Config.from_dict(
        {
            "token": TOKEN,
            "base_url": api.base_url,
            "download_dir": str(Path(tempfile.mkdtemp(prefix="dl_test_")) / "downloads"),
            "max_file_size_mb": 5,
            "keep_downloaded_files": False,
            "log_level": "DEBUG",
        }
    )
