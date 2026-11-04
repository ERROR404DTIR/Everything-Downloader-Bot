"""All user-facing Persian texts and keyboards live here."""

from __future__ import annotations

from typing import Iterable, List, Optional

from balethon import objects

from .jobs import DownloadJob
from .models import FormatChoice, MediaInfo
from .utils import human_duration, human_size, shorten

# ---------------------------------------------------------------------------
# reply keyboard buttons
# ---------------------------------------------------------------------------
BTN_HELP = "📖 راهنما"
BTN_ABOUT = "ℹ️ دربارهٔ ربات"

TEXT_WELCOME = (
    "سلام {name} 👋\n"
    "به «همه‌چیز دانلودر» خوش آمدید!\n\n"
    "لطفاً لینک چیزی که می‌خواهید دانلود شود را وارد کنید.\n"
    "🔗 لینک ویدیو از یوتیوب، اینستاگرام، آپارات، توییتر و ده‌ها سایت دیگر\n"
    "📄 یا لینک مستقیم یک فایل (mp4، mp3، pdf، zip و…)\n\n"
    "⚠️ سقف حجم هر فایلِ قابل ارسال در بله {limit} مگابایت است."
)

TEXT_WELCOME_AGAIN = (
    "دوباره خوش آمدید {name} 👋\n"
    "لینک موردنظر را بفرستید تا برایتان دانلود کنم."
)

TEXT_HELP = (
    "📖 راهنمای استفاده\n\n"
    "۱) لینک موردنظر را بفرستید.\n"
    "۲) ربات لینک را بررسی می‌کند و اگر چند کیفیت موجود باشد، گزینه‌ها را نشان می‌دهد.\n"
    "۳) کیفیت را انتخاب کنید؛ فایل دانلود و برای شما ارسال می‌شود.\n\n"
    "دستورها:\n"
    "/start شروع دوباره\n"
    "/help همین راهنما\n"
    "/about دربارهٔ ربات\n"
    "/cancel لغو کار در حال انجام\n\n"
    "نکته‌ها:\n"
    "• پشتیبانی از یوتیوب، اینستاگرام، تیک‌تاک، توییتر/X، آپارات، ساندکلود، "
    "لینک‌های مستقیم و بسیاری از سایت‌های دیگر.\n"
    "• سقف حجم هر فایل برای ارسال در بله {limit} مگابایت است.\n"
    "• اگر فایلی برای ربات بفرستید (تا ۲۰ مگابایت)، آن را با نام اصلی "
    "به‌صورت سند برایتان برمی‌گردانم.\n"
    "• دانلود ویدیوهای خصوصی یا دارای محدودیت سنی پشتیبانی نمی‌شود."
)

TEXT_ABOUT = (
    "ℹ️ همه‌چیز دانلودر\n\n"
    "یک ربات ساده و سریع برای دانلود از اینترنت؛ ساخته‌شده با yt-dlp و "
    "کتابخانهٔ balethon روی پیام‌رسان بله.\n\n"
    "⚙️ نسخه: {version}\n"
    "📥 حداکثر حجم فایل: {limit} مگابایت\n"
    "🎛 ffmpeg: {ffmpeg}"
)

TEXT_ANALYZING = "🔍 لینک در حال بررسی است…"
TEXT_STARTING_DOWNLOAD = "⏳ شروع دانلود…"
TEXT_UPLOADING = "📤 دانلود انجام شد؛ فایل در حال ارسال است…"
TEXT_CANCELLED = "❌ عملیات لغو شد."
TEXT_NOTHING_TO_CANCEL = "کاری برای لغو وجود ندارد."
TEXT_NOT_A_LINK = (
    "🤔 این پیام یک لینک قابل دانلود نیست.\n"
    "یک لینک (مثلاً لینک ویدیوی یوتیوب یا لینک مستقیم یک فایل) بفرستید."
)
TEXT_UNKNOWN_COMMAND = "دستور ناشناخته است. برای دیدن راهنما /help را بفرستید."
TEXT_EMPTY_MESSAGE = (
    "برای شروع یک لینک بفرستید 🔗\n"
    "مثال: https://www.youtube.com/watch?v=…"
)
TEXT_JOB_EXPIRED = "⌛ این گزینه منقضی شده است. لطفاً لینک را دوباره بفرستید."
TEXT_QUALITY_GONE = "این گزینه دیگر در دسترس نیست."
TEXT_BUSY = "⏳ هنوز کار قبلی شما تمام نشده است. کمی صبر کنید یا /cancel را بفرستید."
TEXT_FILE_UNSUPPORTED = "این نوع فایل برای دریافت از بله پشتیبانی نمی‌شود."
TEXT_FILE_TOO_BIG_FOR_BALE = (
    "⚠️ فایل شما {size} حجم دارد؛ بله اجازهٔ دریافت فایل‌های بزرگ‌تر از ۲۰ مگابایت "
    "را به ربات‌ها نمی‌دهد."
)
TEXT_FILE_RECEIVED = "📥 فایل دریافت شد؛ در حال ارسال دوباره به‌صورت سند…"
TEXT_FILE_SENT = "✅ فایل شما به‌صورت سند ارسال شد."
TEXT_DONE = "✅ انجام شد."
TEXT_PLAYLIST_DISABLED = (
    "📚 این لینک یک پلی‌لیست است و دانلود پلی‌لیست در حال حاضر غیرفعال است.\n"
    "لینک یک ویدیوی تکی را بفرستید."
)
TEXT_UPLOAD_FAILED = (
    "❌ ارسال فایل به بله ناموفق بود.\n"
    "احتمالاً حجم فایل بیش از حد مجاز است. با کیفیت پایین‌تر امتحان کنید."
)
TEXT_GENERIC_ERROR = (
    "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.\n"
    "اگر مشکل ادامه داشت کمی بعد امتحان کنید."
)


def welcome(name: str | None, limit_mb: int) -> str:
    display = (name or "").strip() or "دوست عزیز"
    return TEXT_WELCOME.format(name=display, limit=limit_mb)


def welcome_again(name: str | None, limit_mb: int) -> str:
    display = (name or "").strip() or "دوست عزیز"
    return TEXT_WELCOME_AGAIN.format(name=display, limit=limit_mb)


def help_text(limit_mb: int) -> str:
    return TEXT_HELP.format(limit=limit_mb)


def about_text(version: str, limit_mb: int, ffmpeg: Optional[str]) -> str:
    return TEXT_ABOUT.format(
        version=version,
        limit=limit_mb,
        ffmpeg="موجود ✅" if ffmpeg else "نصب نشده (کیفیت‌های ترکیبی محدود)",
    )


def info_line(label: str, value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return f"{label} {value}"


def media_summary(info: MediaInfo) -> str:
    """Title + metadata shown above the quality keyboard."""
    lines = [f"🎬 {shorten(info.title, 90)}"]
    if info.uploader:
        lines.append(f"👤 {shorten(info.uploader, 60)}")
    if info.duration:
        lines.append(f"⏱ {human_duration(info.duration)}")
    if info.filesize:
        lines.append(f"📦 حجم تقریبی: {human_size(info.filesize)}")
    if info.is_playlist:
        lines.append(f"📚 {info.entry_count} مورد در پلی‌لیست")
    return "\n".join(lines)


def quality_prompt(info: MediaInfo, limit_mb: int) -> str:
    return (
        "✅ لینک با موفقیت بررسی شد:\n\n"
        f"{media_summary(info)}\n\n"
        f"کیفیت موردنظر را انتخاب کنید (سقف ارسال: {limit_mb} مگابایت):"
    )


def direct_prompt(info: MediaInfo) -> str:
    return f"✅ لینک بررسی شد:\n{media_summary(info)}\n\n⏳ دانلود آغاز شد…"


def quality_keyboard(job: DownloadJob, choices: Iterable[FormatChoice]) -> objects.InlineKeyboard:
    """Build the inline keyboard with one button per quality + cancel."""
    buttons: List[objects.InlineKeyboardButton] = []
    rows: List[List[objects.InlineKeyboardButton]] = []
    for choice in choices:
        buttons.append(
            objects.InlineKeyboardButton(choice.label, callback_data=f"dl:{job.id}:{choice.key}")
        )
    # two buttons per row
    for index in range(0, len(buttons), 2):
        rows.append(buttons[index:index + 2])
    rows.append([objects.InlineKeyboardButton("❌ لغو", callback_data=f"cancel:{job.id}")])
    keyboard = objects.InlineKeyboard()
    for row in rows:
        keyboard.add_row(*row)
    return keyboard


def cancel_only_keyboard(job: DownloadJob) -> objects.InlineKeyboard:
    keyboard = objects.InlineKeyboard()
    keyboard.add_row(objects.InlineKeyboardButton("❌ لغو", callback_data=f"cancel:{job.id}"))
    return keyboard


def progress_bar(percent: Optional[float], width: int = 10) -> str:
    if percent is None:
        return "▱" * width
    filled = int(round(percent / 100 * width))
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)


def progress_text(
    title: str,
    percent: Optional[float],
    downloaded: int,
    total: Optional[int],
    speed: Optional[float],
    eta: Optional[int],
    stage: str = "download",
) -> str:
    if stage == "convert":
        return f"⚙️ در حال تبدیل/آماده‌سازی فایل…\n🎬 {shorten(title, 70)}"
    if stage == "upload":
        return f"📤 فایل در حال ارسال به بله…\n🎬 {shorten(title, 70)}"

    lines = ["⏳ در حال دانلود…", f"🎬 {shorten(title, 70)}"]
    if total:
        lines.append(f"{progress_bar(percent)}  {percent or 0:.0f}%")
        lines.append(f"📦 {human_size(downloaded)} از {human_size(total)}")
    else:
        lines.append(f"📦 دریافت‌شده: {human_size(downloaded)}")
    extras = []
    if speed:
        extras.append(f"⚡ {human_size(speed)}/s")
    if eta:
        extras.append(f"⏱ {human_duration(eta)}")
    if extras:
        lines.append(" • ".join(extras))
    return "\n".join(lines)


def final_text(result_title: str, files_count: int, total_size: int) -> str:
    return (
        "✅ دانلود انجام شد.\n"
        f"🎬 {shorten(result_title, 70)}\n"
        f"📦 {human_size(total_size)}"
        + (f" ({files_count} فایل)" if files_count > 1 else "")
    )


def file_caption(title: str, size_bytes: int, source_url: Optional[str] = None) -> str:
    caption = f"🎬 {shorten(title, 80)}\n📦 {human_size(size_bytes)}"
    return caption


def error_text(error: Exception, fallback: str = TEXT_GENERIC_ERROR) -> str:
    from .errors import BotError

    if isinstance(error, BotError):
        return error.to_user()
    return fallback
