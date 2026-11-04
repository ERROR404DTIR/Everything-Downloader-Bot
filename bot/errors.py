"""Errors raised by the bot.

Every user visible message is Persian, because the bot itself speaks Persian.
"""

from __future__ import annotations


class BotError(Exception):
    """Base class for errors that carry a message we may show to the user."""

    user_message = "متأسفانه مشکلی پیش آمد. لطفاً دوباره تلاش کنید."

    def __init__(self, message: str | None = None, *, detail: str | None = None):
        self.detail = detail
        super().__init__(message or detail or self.user_message)

    def to_user(self) -> str:
        return str(self) if str(self) else self.user_message


class DownloadError(BotError):
    user_message = (
        "❌ دانلود ناموفق بود.\n"
        "مطمئن شوید لینک درست و عمومی است و دوباره تلاش کنید."
    )


class TooLargeError(BotError):
    user_message = (
        "⚠️ حجم فایل بیشتر از حد مجاز بله است.\n"
        "کیفیت پایین‌تری انتخاب کنید یا لینک دیگری بفرستید."
    )

    def __init__(self, size: int | None = None, limit: int | None = None):
        self.size = size
        self.limit = limit
        super().__init__(None, detail=f"file too large: {size} > {limit}")


class UnsupportedURLError(BotError):
    user_message = "❌ این لینک پشتیبانی نمی‌شود یا به فایل قابل دانلود اشاره نمی‌کند."


class PlaylistNotAllowedError(BotError):
    user_message = "این لینک یک پلی‌لیست است و در حال حاضر دانلود پلی‌لیست غیرفعال شده است."
