"""Handlers wired to a fake balethon client (no network to Bale needed)."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from balethon import objects

from bot.handlers import BotHandlers


# ---------------------------------------------------------------------------
# fake client / message factories
# ---------------------------------------------------------------------------
class FakeClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.edits: list[dict] = []
        self.documents: list[dict] = []
        self.videos: list[dict] = []
        self.audios: list[dict] = []
        self.photos: list[dict] = []
        self.actions: list[tuple] = []
        self.callback_answers: list[tuple] = []
        self.downloads: list[str] = []
        self.download_payload = b""
        self._next_id = 100
        self.fail_send_video: Optional[Exception] = None

    # -- api methods used by the bot --------------------------------
    async def send_message(self, chat_id, text, reply_markup=None, reply_to_message_id=None):
        self._next_id += 1
        self.messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup,
             "reply_to_message_id": reply_to_message_id}
        )
        message = objects.Message.wrap(
            {
                "message_id": self._next_id,
                "date": 1700000000,
                "chat": {"id": chat_id, "type": "private"},
                "text": text,
            }
        )
        message.bind(self)
        return message

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text,
                           "reply_markup": reply_markup})

    async def send_chat_action(self, chat_id, action="typing"):
        self.actions.append((chat_id, action))
        return True

    async def answer_callback_query(self, callback_query_id, text, show_alert=False):
        self.callback_answers.append((callback_query_id, text, show_alert))
        return True

    async def download(self, file_id: str):
        self.downloads.append(file_id)
        return self.download_payload

    async def send_document(self, chat_id, document, caption=None, reply_markup=None,
                            reply_to_message_id=None):
        self.documents.append(self._record(chat_id, document, caption))
        return self._sent(chat_id, caption)

    async def send_video(self, chat_id, video, duration=None, width=None, height=None,
                         caption=None, reply_markup=None, reply_to_message_id=None):
        if self.fail_send_video is not None:
            raise self.fail_send_video
        self.videos.append(self._record(chat_id, video, caption))
        return self._sent(chat_id, caption)

    async def send_audio(self, chat_id, audio, caption=None, duration=None, title=None,
                         reply_markup=None, reply_to_message_id=None):
        self.audios.append(self._record(chat_id, audio, caption))
        return self._sent(chat_id, caption)

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None,
                         reply_to_message_id=None):
        self.photos.append(self._record(chat_id, photo, caption))
        return self._sent(chat_id, caption)

    # -- helpers ----------------------------------------------------
    @staticmethod
    def _record(chat_id, media, caption):
        if hasattr(media, "read"):
            data = media.read()
            name = getattr(media, "name", None)
        else:
            data, name = media, None
        return {"chat_id": chat_id, "data": data, "name": name, "caption": caption}

    def _sent(self, chat_id, caption):
        message = objects.Message.wrap(
            {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": chat_id, "type": "private"},
                "caption": caption,
            }
        )
        message.bind(self)
        return message

    # -- inspection --------------------------------------------------
    @property
    def last_text(self) -> str:
        assert self.messages, "no message was sent"
        return self.messages[-1]["text"]

    @property
    def last_edit(self) -> str:
        assert self.edits, "no edit was made"
        return self.edits[-1]["text"]

    @property
    def last_keyboard(self):
        for source in (self.edits, self.messages):
            if source and source[-1].get("reply_markup") is not None:
                return source[-1]["reply_markup"]
        return None


def make_message(text: str = "", chat_id: int = 555, user_id: int = 42, **extra) -> objects.Message:
    raw: dict[str, Any] = {
        "message_id": 7,
        "date": 1700000000,
        "chat": {"id": chat_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "علی"},
    }
    if text:
        raw["text"] = text
    raw.update(extra)
    message = objects.Message.wrap(raw)
    return message


@pytest.fixture
def fake_client():
    return FakeClient()


@pytest.fixture
def handlers(fake_client, config, tmp_path):
    config.download_dir = str(tmp_path / "downloads")
    config.keep_downloaded_files = False
    bot_handlers = BotHandlers(fake_client, config)
    message = make_message("/start")
    message.bind(fake_client)
    return bot_handlers


def bind(message: objects.Message, client: FakeClient) -> objects.Message:
    message.bind(client)
    return message


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
class TestCommands:
    async def test_start_greets_in_persian(self, handlers, fake_client):
        await handlers.on_start(bind(make_message("/start"), fake_client))
        text = fake_client.last_text
        assert "به «همه‌چیز دانلودر» خوش آمدید" in text
        assert "لطفاً لینک چیزی که می‌خواهید دانلود شود را وارد کنید" in text
        assert fake_client.messages[-1]["reply_markup"] is not None

    async def test_help(self, handlers, fake_client):
        await handlers.on_help(bind(make_message("/help"), fake_client))
        assert "راهنمای استفاده" in fake_client.last_text

    async def test_about(self, handlers, fake_client):
        await handlers.on_about(bind(make_message("/about"), fake_client))
        assert "همه‌چیز دانلودر" in fake_client.last_text

    async def test_unknown_command(self, handlers, fake_client):
        await handlers.on_text(bind(make_message("/nonsense"), fake_client))
        assert "ناشناخته" in fake_client.last_text

    async def test_cancel_without_job(self, handlers, fake_client):
        await handlers.on_text(bind(make_message("/cancel"), fake_client))
        assert "کاری برای لغو وجود ندارد" in fake_client.last_text

    async def test_reply_keyboard_buttons(self, handlers, fake_client):
        await handlers.on_text(bind(make_message("📖 راهنما"), fake_client))
        assert "راهنمای استفاده" in fake_client.last_text

    async def test_plain_text_is_not_a_link(self, handlers, fake_client):
        await handlers.on_text(bind(make_message("سلام"), fake_client))
        assert "لینک قابل دانلود نیست" in fake_client.last_text


# ---------------------------------------------------------------------------
# link → download flows
# ---------------------------------------------------------------------------
class TestFileFlow:
    async def test_direct_pdf_is_downloaded_and_sent(self, handlers, fake_client, file_server):
        body = b"%PDF-1.4 hello" * 200
        url = file_server.add("/x/report.pdf", body, "application/pdf", "report.pdf")

        await handlers.handle_url(bind(make_message(url), fake_client), url, 42)

        assert len(fake_client.documents) == 1
        sent = fake_client.documents[0]
        assert sent["data"] == body
        assert "report.pdf" in sent["caption"]

    async def test_html_page_is_rejected(self, handlers, fake_client, file_server):
        url = file_server.add("/page", b"<html></html>", "text/html")
        await handlers.handle_url(bind(make_message(url), fake_client), url, 42)
        assert "پشتیبانی نمی‌شود" in fake_client.last_edit

    async def test_oversized_file_is_refused_cleanly(self, handlers, fake_client, file_server):
        body = b"x" * (3 * 1024 * 1024)  # config limit = 2 MB
        url = file_server.add("/huge.zip", body, "application/zip", "huge.zip")
        await handlers.handle_url(bind(make_message(url), fake_client), url, 42)
        assert "بیشتر" in fake_client.last_edit
        assert fake_client.documents == []


class TestVideoFlow:
    async def test_quality_keyboard_then_callback(self, handlers, fake_client, file_server):
        body = b"\x00" * 4096
        url = file_server.add("/movie.mp4", body, "video/mp4", "movie.mp4")

        message = bind(make_message(url), fake_client)
        await handlers.handle_url(message, url, 42)

        keyboard = fake_client.last_keyboard
        assert keyboard is not None
        rows = keyboard.inline_keyboard
        callbacks = [b.callback_data for row in rows for b in row]
        assert any(cb.startswith("dl:") for cb in callbacks)
        assert any(cb.startswith("cancel:") for cb in callbacks)
        assert "کیفیت" in fake_client.last_edit

        job = handlers.jobs.latest_for_user(42)
        callback = objects.CallbackQuery.wrap(
            {
                "id": "cb-1",
                "from": {"id": 42, "is_bot": False, "first_name": "علی"},
                "message": {
                    "message_id": fake_client.edits[-1]["message_id"],
                    "date": 1700000000,
                    "chat": {"id": 555, "type": "private"},
                    "text": "prompt",
                },
                "chat_instance": "ci",
                "data": f"dl:{job.id}:best",
            }
        )
        callback.bind(fake_client)

        await handlers.on_callback(callback)

        assert fake_client.callback_answers
        assert len(fake_client.videos) == 1
        assert fake_client.videos[0]["data"] == body
        assert "دانلود انجام شد" in fake_client.last_edit

    async def test_cancel_button(self, handlers, fake_client, file_server):
        url = file_server.add("/movie2.mp4", b"\x00" * 2048, "video/mp4", "m.mp4")
        await handlers.handle_url(bind(make_message(url), fake_client), url, 42)
        job = handlers.jobs.latest_for_user(42)

        callback = objects.CallbackQuery.wrap(
            {
                "id": "cb-2",
                "from": {"id": 42, "is_bot": False, "first_name": "علی"},
                "message": {"message_id": 1, "date": 1700000000,
                            "chat": {"id": 555, "type": "private"}, "text": "x"},
                "chat_instance": "ci",
                "data": f"cancel:{job.id}",
            }
        )
        callback.bind(fake_client)
        await handlers.on_callback(callback)

        assert "لغو" in fake_client.last_edit
        assert handlers.jobs.get(job.id) is None
        assert fake_client.videos == []

    async def test_expired_job_shows_alert(self, handlers, fake_client):
        callback = objects.CallbackQuery.wrap(
            {
                "id": "cb-3",
                "from": {"id": 42, "is_bot": False, "first_name": "علی"},
                "message": {"message_id": 1, "date": 1700000000,
                            "chat": {"id": 555, "type": "private"}, "text": "x"},
                "chat_instance": "ci",
                "data": "dl:doesnotexist:best",
            }
        )
        callback.bind(fake_client)
        await handlers.on_callback(callback)
        assert fake_client.callback_answers[-1][2] is True  # show_alert
        assert "منقضی" in fake_client.callback_answers[-1][1]


# ---------------------------------------------------------------------------
# files uploaded to the bot
# ---------------------------------------------------------------------------
class TestIncomingFile:
    async def test_document_is_bounced_back(self, handlers, fake_client):
        fake_client.download_payload = b"hello file"
        message = make_message(
            document={
                "file_id": "file-1",
                "file_name": "note.txt",
                "file_size": 10,
                "mime_type": "text/plain",
            }
        )
        message.bind(fake_client)

        await handlers.on_message(message)

        assert fake_client.downloads == ["file-1"]
        assert len(fake_client.documents) == 1
        assert fake_client.documents[0]["data"] == b"hello file"
        assert "note.txt" in fake_client.documents[0]["caption"]

    async def test_oversized_incoming_file(self, handlers, fake_client):
        message = make_message(
            document={"file_id": "f2", "file_name": "big.zip", "file_size": 30 * 1024 * 1024}
        )
        message.bind(fake_client)
        await handlers.on_message(message)
        assert "۲۰ مگابایت" in fake_client.last_text
        assert fake_client.downloads == []


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------
class TestCancelRunningJob:
    async def test_slash_cancel_interrupts_running_download(self, handlers, fake_client, monkeypatch):
        from bot.models import DownloadResult, MediaInfo

        async def slow_download(*args, cancel_event=None, **kwargs):
            # sit here until the job is cancelled through the event
            for _ in range(100):
                if cancel_event is not None and cancel_event.is_set():
                    from bot.jobs import JobCancelled

                    raise JobCancelled()
                await asyncio.sleep(0.02)
            return DownloadResult(files=[])

        async def fake_analyze(url):
            # "file" kind has no quality choices -> the download starts right away
            return MediaInfo(url=url, title="slow file", kind="file")

        monkeypatch.setattr(handlers.downloader, "analyze", fake_analyze)
        monkeypatch.setattr(handlers.downloader, "download", slow_download)

        message = bind(make_message("https://example.com/video"), fake_client)
        task = asyncio.create_task(handlers.handle_url(message, "https://example.com/video", 42))
        for _ in range(50):
            if 42 in handlers._active_jobs:
                break
            await asyncio.sleep(0.02)
        assert 42 in handlers._active_jobs, [m["text"] for m in fake_client.messages]

        await handlers.on_cancel(bind(make_message("/cancel"), fake_client))
        await asyncio.wait_for(task, timeout=5)

        assert any("لغو" in m["text"] for m in fake_client.messages)
        assert 42 not in handlers._active_jobs
        assert handlers.locks.active_count(42) == 0


class TestConcurrencyLimit:
    async def test_second_download_is_rejected_while_busy(self, handlers, fake_client, monkeypatch):
        from bot.jobs import DownloadJob
        from bot.models import DownloadResult, FormatChoice, MediaInfo

        started = asyncio.Event()
        release = asyncio.Event()

        async def blocking_download(*args, **kwargs):
            started.set()
            await release.wait()
            return DownloadResult(files=[])

        monkeypatch.setattr(handlers.downloader, "download", blocking_download)
        handlers.locks.limit = 1
        info = MediaInfo(url="https://example.com/1", title="v", kind="video")
        choice = FormatChoice("best", "behtarin")

        first_job = DownloadJob.new(42, 555, "https://example.com/1", info)
        first = asyncio.create_task(handlers.run_job(first_job, choice))
        await asyncio.wait_for(started.wait(), timeout=5)

        second_job = DownloadJob.new(42, 555, "https://example.com/2", info)
        await handlers.run_job(second_job, choice)
        assert any("تمام نشده" in m["text"] for m in fake_client.messages)

        release.set()
        await asyncio.wait_for(first, timeout=5)
        assert handlers.locks.active_count(42) == 0


class TestMisc:
    async def test_message_without_text_or_media_is_ignored(self, handlers, fake_client):
        message = make_message("")
        message.text = ""
        message.bind(fake_client)
        await handlers.on_message(message)
        assert fake_client.messages == []  # stickers/contacts etc. are not spammed

    async def test_whitespace_text_asks_for_a_link(self, handlers, fake_client):
        message = make_message("   ")
        message.bind(fake_client)
        await handlers.on_message(message)
        assert "لینک" in fake_client.last_text

    async def test_playlist_disabled(self, handlers, fake_client, monkeypatch):
        from bot.models import MediaInfo

        async def fake_analyze(url):
            return MediaInfo(url=url, title="pl", kind="playlist", is_playlist=True)

        monkeypatch.setattr(handlers.downloader, "analyze", fake_analyze)
        await handlers.handle_url(bind(make_message("https://youtube.com/playlist?list=x"), fake_client),
                                  "https://youtube.com/playlist?list=x", 42)
        assert "پلی‌لیست" in fake_client.last_edit

    async def test_unsupported_error_path(self, handlers, fake_client, monkeypatch):
        from bot.errors import UnsupportedURLError

        async def boom(url):
            raise UnsupportedURLError()

        monkeypatch.setattr(handlers.downloader, "analyze", boom)
        await handlers.handle_url(bind(make_message("https://example.com"), fake_client),
                                  "https://example.com", 42)
        assert "پشتیبانی نمی‌شود" in fake_client.last_edit

    async def test_download_command_with_link(self, handlers, fake_client, file_server):
        url = file_server.add("/dl.txt", b"abc", "text/plain", "dl.txt")
        await handlers.on_text(bind(make_message(f"/download {url}"), fake_client))
        assert len(fake_client.documents) == 1

    async def test_download_command_without_link(self, handlers, fake_client):
        await handlers.on_text(bind(make_message("/download"), fake_client))
        assert "لینک را بعد از دستور" in fake_client.last_text
