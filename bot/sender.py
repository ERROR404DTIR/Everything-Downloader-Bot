"""Delivering downloaded files back to the Bale chat.

Bale (like Telegram) decides how a file is displayed from the **method** used,
not only from the extension, so we pick ``sendVideo`` / ``sendAudio`` /
``sendPhoto`` / ``sendDocument`` based on the produced media type.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from balethon import Client
from balethon import objects

from .errors import TooLargeError
from .logger import get_logger
from .models import DownloadResult
from .utils import human_size, shorten

log = get_logger(__name__)

_VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".ts"}
_AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

#: Files bigger than this are never sent with a preview-ish method.
PREVIEW_METHOD_LIMIT = 20 * 1024 * 1024


class FileSender:
    def __init__(self, client: Client, max_file_size_bytes: int):
        self.client = client
        self.max_file_size_bytes = max_file_size_bytes

    # ------------------------------------------------------------------
    def method_for(self, path: Path, result: DownloadResult) -> str:
        suffix = path.suffix.lower()
        size = path.stat().st_size if path.exists() else 0
        if size > PREVIEW_METHOD_LIMIT:
            return "document"
        if result.kind == "image" or suffix in _IMAGE_EXT:
            return "photo"
        if result.kind == "audio" or suffix in _AUDIO_EXT:
            return "audio"
        if result.kind == "video" and suffix in _VIDEO_EXT:
            return "video"
        return "document"

    def _check_size(self, path: Path) -> None:
        size = path.stat().st_size
        if size > self.max_file_size_bytes:
            raise TooLargeError(size, self.max_file_size_bytes)
        if size == 0:
            raise TooLargeError(0, self.max_file_size_bytes)

    # ------------------------------------------------------------------
    async def send_result(
        self,
        chat_id: int,
        result: DownloadResult,
        reply_to_message_id: Optional[int] = None,
    ) -> int:
        """Send every file of ``result`` and return how many succeeded."""
        sent = 0
        for path in result.files:
            path = Path(path)
            self._check_size(path)
            caption = self._caption(path, result)
            method = self.method_for(path, result)
            await self._send_with_fallback(
                chat_id, path, method, caption, result, reply_to_message_id
            )
            sent += 1
            if len(result.files) > 1:
                # be gentle with the API when a playlist produced many files
                await asyncio.sleep(1)
        return sent

    async def _send_with_fallback(
        self,
        chat_id: int,
        path: Path,
        method: str,
        caption: str,
        result: DownloadResult,
        reply_to_message_id: Optional[int],
    ) -> objects.Message:
        try:
            return await self._send(chat_id, path, method, caption, result, reply_to_message_id)
        except Exception as exc:  # noqa: BLE001 - we retry as a plain document
            if method == "document":
                raise
            log.warning("ارسال به‌صورت %s ناموفق بود (%s) — تلاش دوباره به‌صورت سند", method, exc)
            return await self._send(chat_id, path, "document", caption, result, reply_to_message_id)

    async def _send(
        self,
        chat_id: int,
        path: Path,
        method: str,
        caption: str,
        result: DownloadResult,
        reply_to_message_id: Optional[int],
    ) -> objects.Message:
        with open(path, "rb") as handle:
            if method == "video":
                return await self.client.send_video(
                    chat_id,
                    handle,
                    duration=result.duration,
                    width=result.width,
                    height=result.height,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )
            if method == "audio":
                return await self.client.send_audio(
                    chat_id,
                    handle,
                    caption=caption,
                    duration=result.duration,
                    title=shorten(result.title, 60),
                    reply_to_message_id=reply_to_message_id,
                )
            if method == "photo":
                return await self.client.send_photo(
                    chat_id,
                    handle,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                )
            return await self.client.send_document(
                chat_id,
                handle,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
            )

    # ------------------------------------------------------------------
    @staticmethod
    def _caption(path: Path, result: DownloadResult) -> str:
        size = path.stat().st_size
        lines = [f"🎬 {shorten(result.title or path.stem, 90)}"]
        if result.uploader:
            lines.append(f"👤 {shorten(result.uploader, 60)}")
        lines.append(f"📦 {human_size(size)}")
        if result.source_url and not result.is_playlist:
            lines.append(f"🔗 {result.source_url}")
        caption = "\n".join(lines)
        # Bale allows 1024 characters for captions; keep a safety margin.
        return caption[:1000]

    async def resend_incoming_file(
        self,
        chat_id: int,
        path: Path,
        filename: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> objects.Message:
        """Send a file the user uploaded to us back as a document."""
        filename = filename or path.name
        with open(path, "rb") as handle:
            return await self.client.send_document(
                chat_id,
                handle,
                caption=f"📄 {shorten(filename, 90)}\n📦 {human_size(path.stat().st_size)}",
                reply_to_message_id=reply_to_message_id,
            )
