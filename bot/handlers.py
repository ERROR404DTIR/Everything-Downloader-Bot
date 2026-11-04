"""All bot handlers (commands, links, files, inline buttons).

balethon dispatches every update to the **first** matching handler, so instead
of registering many ``on_message`` handlers we register exactly one and route
the update ourselves. That keeps the behaviour predictable.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from balethon import Client, objects

from . import __version__, ui
from .config import Config
from .downloader import Downloader
from .errors import (
    BotError,
    PlaylistNotAllowedError,
    TooLargeError,
    UnsupportedURLError,
)
from .jobs import DownloadJob, JobCancelled, JobStore, UserLocks
from .logger import get_logger
from .models import DownloadProgress, FormatChoice
from .sender import FileSender
from .utils import extract_url, human_size, safe_filename

log = get_logger(__name__)

#: Bale refuses to let a bot download files bigger than this from its servers.
BALE_DOWNLOAD_LIMIT = 20 * 1024 * 1024

COMMANDS = {"/start", "/help", "/about", "/cancel", "/download", "/dl"}


class BotHandlers:
    """Shared state + every handler of the bot."""

    def __init__(self, client: Client, config: Config):
        self.client = client
        self.config = config
        self.downloader = Downloader(config)
        self.sender = FileSender(client, config.max_file_size_bytes)
        self.jobs = JobStore(ttl_seconds=config.job_ttl_seconds)
        self.locks = UserLocks(limit=config.max_concurrent_downloads)
        self._active_jobs: dict = {}  # user_id -> DownloadJob currently running
        self._incoming_dir = config.download_path / "_incoming"
        self._incoming_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @property
    def limit_mb(self) -> int:
        return self.config.max_file_size_mb

    @staticmethod
    def display_name(message: objects.Message) -> str:
        author = getattr(message, "author", None)
        return getattr(author, "first_name", None) or "دوست عزیز"

    @staticmethod
    def user_id_of(message: objects.Message) -> int:
        author = getattr(message, "author", None)
        return getattr(author, "id", None) or message.chat.id

    async def send(self, chat_id: int, text: str, **kwargs) -> Optional[objects.Message]:
        try:
            return await self.client.send_message(chat_id, text, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("send_message failed: %s", exc, exc_info=exc)
            return None

    async def typing(self, chat_id: int) -> None:
        try:
            await self.client.send_chat_action(chat_id, "typing")
        except Exception as exc:  # noqa: BLE001 - cosmetic only
            log.debug("send_chat_action failed: %s", exc)

    async def _edit(self, message: Optional[objects.Message], text: str, **kwargs) -> None:
        if message is None:
            return
        try:
            await message.edit_text(text, **kwargs)
        except Exception as exc:  # noqa: BLE001 - e.g. "message is not modified"
            log.warning("edit_message_text failed (%s) — sending a new message", exc)
            await self.send(message.chat.id, text, **kwargs)

    def _main_keyboard(self) -> objects.ReplyKeyboard:
        return objects.ReplyKeyboard(
            [ui.BTN_HELP, ui.BTN_ABOUT], resize=True, one_time=False
        )

    # ------------------------------------------------------------------
    # /start & co
    # ------------------------------------------------------------------
    async def on_start(self, message: objects.Message) -> None:
        self.jobs.purge()
        await self.send(
            message.chat.id,
            ui.welcome(self.display_name(message), self.limit_mb),
            reply_markup=self._main_keyboard(),
        )

    async def on_help(self, message: objects.Message) -> None:
        await self.send(
            message.chat.id,
            ui.help_text(self.limit_mb),
            reply_markup=self._main_keyboard(),
        )

    async def on_about(self, message: objects.Message) -> None:
        await self.send(
            message.chat.id,
            ui.about_text(__version__, self.limit_mb, self.downloader.ffmpeg),
            reply_markup=self._main_keyboard(),
        )

    async def on_cancel(self, message: objects.Message) -> None:
        user_id = self.user_id_of(message)
        active = self._active_jobs.get(user_id)
        if active is not None:
            active.cancel()
            await self.send(message.chat.id, ui.TEXT_CANCELLED)
            return
        job = self.jobs.latest_for_user(user_id)
        if job is None or job.status in {"finished", "cancelled"}:
            await self.send(message.chat.id, ui.TEXT_NOTHING_TO_CANCEL)
            return
        job.cancel()
        self.jobs.pop(job.id)
        await self.send(message.chat.id, ui.TEXT_CANCELLED)

    async def handle_command(self, message: objects.Message, command: str) -> None:
        if command == "/start":
            await self.on_start(message)
        elif command == "/help":
            await self.on_help(message)
        elif command == "/about":
            await self.on_about(message)
        elif command == "/cancel":
            await self.on_cancel(message)
        elif command in {"/download", "/dl"}:
            text = (message.text or "")
            url = extract_url(text.split(maxsplit=1)[1]) if len(text.split(maxsplit=1)) > 1 else None
            if url:
                await self.handle_url(message, url, self.user_id_of(message))
            else:
                await self.send(
                    message.chat.id,
                    "لینک را بعد از دستور بنویسید. مثال:\n/download https://example.com/file.mp4",
                )
        else:
            await self.send(message.chat.id, ui.TEXT_UNKNOWN_COMMAND)

    # ------------------------------------------------------------------
    # the single message router
    # ------------------------------------------------------------------
    async def on_message(self, message: objects.Message) -> None:
        try:
            if message.text:
                await self.on_text(message)
            elif _attachment_of(message) is not None:
                await self.on_file(message)
        except JobCancelled:
            pass
        except Exception as exc:  # noqa: BLE001
            log.exception("on_message failed")
            await self.send(message.chat.id, ui.error_text(exc))

    async def on_text(self, message: objects.Message) -> None:
        text = (message.text or "").strip()
        chat_id = message.chat.id

        if not text:
            await self.send(chat_id, ui.TEXT_EMPTY_MESSAGE)
            return

        if text.startswith("/"):
            head = text.split()[0].split("@")[0].lower()
            if head in COMMANDS:
                url = extract_url(text)
                if url is None:
                    await self.handle_command(message, head)
                    return
                # a deep link like "/start https://…" is treated as a link
            elif not extract_url(text):
                await self.send(chat_id, ui.TEXT_UNKNOWN_COMMAND)
                return

        if text == ui.BTN_HELP:
            await self.on_help(message)
            return
        if text == ui.BTN_ABOUT:
            await self.on_about(message)
            return

        url = extract_url(text)
        if url is None:
            await self.send(chat_id, ui.TEXT_NOT_A_LINK)
            return

        await self.handle_url(message, url, self.user_id_of(message))

    # ------------------------------------------------------------------
    # the core flow
    # ------------------------------------------------------------------
    async def handle_url(self, message: objects.Message, url: str, user_id: int) -> None:
        chat_id = message.chat.id
        status = await self.send(chat_id, ui.TEXT_ANALYZING)
        await self.typing(chat_id)

        try:
            info = await self.downloader.analyze(url)
        except PlaylistNotAllowedError:
            await self._edit(status, ui.TEXT_PLAYLIST_DISABLED)
            return
        except UnsupportedURLError as exc:
            log.info("unsupported link %s (%s)", url, exc)
            await self._edit(
                status,
                "❌ این لینک پشتیبانی نمی‌شود یا فایلی برای دانلود ندارد.\n"
                "لینک دیگری امتحان کنید یا /help را بفرستید.",
            )
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("analyze failed")
            await self._edit(status, ui.error_text(exc))
            return

        if info.is_playlist and not self.config.allow_playlists:
            await self._edit(status, ui.TEXT_PLAYLIST_DISABLED)
            return

        oversized = bool(info.filesize and info.filesize > self.config.max_file_size_bytes)
        if oversized and info.kind != "video":
            await self._edit(
                status,
                "⚠️ حجم این فایل از سقف مجاز بله بیشتر است:\n"
                f"📦 {human_size(info.filesize)} > {self.limit_mb} مگابایت",
            )
            return

        choices = self.downloader.build_choices(info)
        job = self.jobs.add(DownloadJob.new(user_id, chat_id, url, info, choices))

        if not choices:
            # exactly one possible output (audio / image / direct file)
            await self._edit(status, ui.direct_prompt(info), reply_markup=ui.cancel_only_keyboard(job))
            await self.run_job(job, self.downloader.default_choice(info), progress_message=status)
            return

        prompt = ui.quality_prompt(info, self.limit_mb)
        if oversized:
            prompt = (
                f"⚠️ حجم تقریبی بهترین کیفیت {human_size(info.filesize)} است و از سقف "
                f"{self.limit_mb} مگابایتی بله بیشتر است.\n"
                "یک کیفیت پایین‌تر انتخاب کنید:\n\n" + prompt
            )
        keyboard = ui.quality_keyboard(job, choices)
        if status is not None:
            await self._edit(status, prompt, reply_markup=keyboard)
            job.message_id = status.id
        else:
            sent = await self.send(chat_id, prompt, reply_markup=keyboard)
            job.message_id = sent.id if sent else None

    # ------------------------------------------------------------------
    # inline keyboard: quality choice / cancel
    # ------------------------------------------------------------------
    async def on_callback(self, callback_query: objects.CallbackQuery) -> None:
        try:
            await self._on_callback(callback_query)
        except Exception:  # noqa: BLE001
            log.exception("on_callback failed")
            await self._answer(callback_query, "خطایی رخ داد. دوباره تلاش کنید.", alert=True)

    async def _on_callback(self, callback_query: objects.CallbackQuery) -> None:
        parts = (callback_query.data or "").split(":")
        action = parts[0] if parts else ""

        if action == "cancel":
            job = self.jobs.pop(parts[1]) if len(parts) > 1 else None
            if job is not None:
                job.cancel()
            else:
                # the job may already be running -> stop the live download too
                author = getattr(callback_query, "author", None)
                running = self._active_jobs.get(getattr(author, "id", None))
                if running is not None:
                    running.cancel()
            await self._answer(callback_query, ui.TEXT_CANCELLED)
            await self._edit(callback_query.message, ui.TEXT_CANCELLED)
            return

        if action != "dl" or len(parts) < 3:
            await self._answer(callback_query, ui.TEXT_UNKNOWN_COMMAND, alert=True)
            return

        job = self.jobs.pop(parts[1])
        if job is None:
            await self._answer(callback_query, ui.TEXT_JOB_EXPIRED, alert=True)
            return

        choice = next((c for c in job.choices if c.key == parts[2]), None)
        if choice is None:
            await self._answer(callback_query, ui.TEXT_QUALITY_GONE, alert=True)
            return

        await self._answer(callback_query, "⏳ شروع دانلود…")
        job.message_id = callback_query.message.id if callback_query.message else None
        await self._edit(
            callback_query.message, f"⏳ دانلود با کیفیت «{choice.label}» آغاز شد…"
        )
        await self.run_job(job, choice, progress_message=callback_query.message)

    async def _answer(
        self, callback_query: objects.CallbackQuery, text: str, alert: bool = False
    ) -> None:
        try:
            await callback_query.answer(text, show_alert=alert)
        except Exception as exc:  # noqa: BLE001 - cosmetic
            log.debug("answer_callback_query failed: %s", exc)

    # ------------------------------------------------------------------
    # running one download job
    # ------------------------------------------------------------------
    async def run_job(
        self,
        job: DownloadJob,
        choice: FormatChoice,
        progress_message: Optional[objects.Message] = None,
    ) -> None:
        chat_id = job.chat_id
        if not self.locks.try_acquire(job.user_id):
            await self._fail(chat_id, progress_message, ui.TEXT_BUSY)
            return

        job_dir = self.config.download_path / f"job_{job.id}"
        last_update = 0.0
        last_percent = -5.0

        async def on_progress(progress: DownloadProgress) -> None:
            nonlocal progress_message, last_update, last_percent
            if job.is_cancelled:
                raise JobCancelled()
            now = time.monotonic()
            percent = progress.percent
            if percent is not None:
                if now - last_update < 4 and abs(percent - last_percent) < 10:
                    return
                last_percent = percent
            elif now - last_update < 4:
                return
            last_update = now
            text = ui.progress_text(
                job.info.title,
                percent,
                progress.downloaded,
                progress.total,
                progress.speed,
                progress.eta,
                stage=progress.stage,
            )
            if progress_message is not None:
                await self._edit(progress_message, text)
            else:
                progress_message = await self.send(chat_id, text)

        active_job = self._active_jobs.get(job.user_id)
        if active_job is not None:
            await self._fail(chat_id, progress_message, ui.TEXT_BUSY)
            self.locks.release(job.user_id)
            return

        self._active_jobs[job.user_id] = job
        job.status = "running"
        result = None
        try:
            await self.typing(chat_id)
            result = await self.downloader.download(
                job.url,
                choice,
                job.info,
                progress=on_progress,
                cancel_event=job.cancel_event,
                job_dir=job_dir,
            )
        except JobCancelled:
            job.status = "cancelled"
            await self._fail(chat_id, progress_message, ui.TEXT_CANCELLED)
            return
        except TooLargeError as exc:
            job.status = "finished"
            await self._fail(
                chat_id,
                progress_message,
                "⚠️ حجم فایل از سقف مجاز بله بیشتر است.\n"
                f"📦 {human_size(exc.size)} > {self.limit_mb} مگابایت\n\n"
                "کیفیت پایین‌تری انتخاب کنید.",
            )
            return
        except BotError as exc:
            job.status = "finished"
            await self._fail(chat_id, progress_message, f"❌ {exc.to_user()}")
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("download failed")
            job.status = "finished"
            await self._fail(chat_id, progress_message, ui.error_text(exc))
            return
        finally:
            self._active_jobs.pop(job.user_id, None)
            self.locks.release(job.user_id)
            if result is None:
                self.downloader.cleanup(job_dir)

        # ---- upload phase ---------------------------------------------
        job.status = "finished"
        total_size = sum(p.stat().st_size for p in result.files if p.exists())
        await self._edit(
            progress_message,
            ui.progress_text(
                result.title, None, total_size, total_size, None, None, stage="upload"
            ),
        )
        try:
            sent = await self.sender.send_result(chat_id, result)
        except TooLargeError as exc:
            await self._fail(
                chat_id,
                progress_message,
                "⚠️ فایل دانلود شد اما برای ارسال در بله بزرگ است.\n"
                f"📦 {human_size(exc.size)} > {self.limit_mb} مگابایت\n\n"
                "با کیفیت پایین‌تر امتحان کنید.",
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("upload failed: %s", exc)
            await self._fail(chat_id, progress_message, ui.TEXT_UPLOAD_FAILED)
        else:
            text = ui.final_text(result.title, sent, total_size)
            await self._edit(progress_message, text)
            if progress_message is None:
                await self.send(chat_id, text)
        finally:
            self.downloader.cleanup(result.job_dir)

    async def _fail(
        self, chat_id: int, progress_message: Optional[objects.Message], text: str
    ) -> None:
        if progress_message is not None:
            await self._edit(progress_message, text)
        # errors must never be silent: always deliver a fresh message too
        await self.send(chat_id, text)

    # ------------------------------------------------------------------
    # files uploaded *to* the bot
    # ------------------------------------------------------------------
    async def on_file(self, message: objects.Message) -> None:
        """The user sent a file/photo/audio/video: bounce it back as a document."""
        chat_id = message.chat.id
        attachment = _attachment_of(message)
        if attachment is None:
            await self.send(chat_id, ui.TEXT_FILE_UNSUPPORTED)
            return

        size = getattr(attachment, "size", None)
        if size and size > BALE_DOWNLOAD_LIMIT:
            await self.send(chat_id, ui.TEXT_FILE_TOO_BIG_FOR_BALE.format(size=human_size(size)))
            return

        await self.send(chat_id, ui.TEXT_FILE_RECEIVED)
        await self.typing(chat_id)
        incoming_path: Optional[Path] = None
        try:
            name = (
                getattr(attachment, "name", None)
                or getattr(attachment, "title", None)
                or f"file_{message.id}"
            )
            data = await self.client.download(attachment.id)
            incoming_path = self._incoming_dir / f"{message.id}_{safe_filename(name, fallback='file')}"
            incoming_path.write_bytes(data)
            await self.sender.resend_incoming_file(
                chat_id, incoming_path, filename=name, reply_to_message_id=message.id
            )
            await self.send(chat_id, ui.TEXT_FILE_SENT)
        except Exception:  # noqa: BLE001
            log.exception("incoming file failed")
            await self.send(chat_id, "❌ دریافت فایل ناموفق بود. دوباره تلاش کنید.")
        finally:
            if incoming_path is not None:
                incoming_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    async def on_error(self, error: Exception) -> None:
        if isinstance(error, JobCancelled):
            return
        log.error("dispatcher error: %s", error, exc_info=error)


def _attachment_of(message: objects.Message):
    """Return the media object of an incoming message (largest photo first)."""
    if message.document:
        return message.document
    if message.video:
        return message.video
    if message.audio:
        return message.audio
    if message.animation:
        return message.animation
    if message.voice:
        return message.voice
    if message.photo:
        try:
            return message.photo[-1]
        except (IndexError, TypeError):
            return message.photo
    return None


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------
def register(client: Client, handlers: BotHandlers) -> None:
    """Attach every handler to the balethon client."""

    @client.on_initialize()
    async def _ready(client: Client) -> None:
        log.info("ربات با موفقیت متصل شد: @%s", getattr(client.user, "username", "?"))

    @client.on_shutdown()
    async def _bye(client: Client) -> None:
        await handlers.downloader.close()
        log.info("ربات متوقف شد.")

    @client.on_error()
    async def _on_error(error: Exception) -> None:
        await handlers.on_error(error)

    @client.on_message()
    async def _message(message: objects.Message) -> None:
        await handlers.on_message(message)

    @client.on_callback_query()
    async def _callback(callback_query: objects.CallbackQuery) -> None:
        await handlers.on_callback(callback_query)
