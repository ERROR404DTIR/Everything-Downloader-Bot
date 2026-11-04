"""Small shared helpers: formatting, file names, URLs."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

#: Matches http(s) links, optionally without scheme (``youtu.be/xyz``).
URL_RE = re.compile(
    r"(?P<url>(?:https?://|www\.)[^\s<>\"']+|[a-z0-9-]+\.[a-z]{2,}/[^\s<>\"']*)",
    re.IGNORECASE,
)

#: Characters that are not allowed in file names on common file systems.
_BAD_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def human_size(num_bytes: Optional[int | float]) -> str:
    """Return a human readable size such as ``12.4 MB``."""
    if num_bytes is None:
        return "نامشخص"
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "نامشخص"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def human_duration(seconds: Optional[int | float]) -> str:
    """Return ``1:02:03`` / ``4:05`` style durations."""
    if not seconds:
        return "نامشخص"
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return "نامشخص"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def extract_url(text: str) -> Optional[str]:
    """Extract the first link found in a message, or ``None``."""
    if not text:
        return None
    match = URL_RE.search(text.strip())
    if not match:
        return None
    url = match.group("url").rstrip(").,،؛!؟]}\u200c\u200f\u200e")
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_probably_url(text: str) -> bool:
    return extract_url(text) is not None


def pretty_host(url: str) -> str:
    """Return a short ``domain`` label for a URL."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:  # pragma: no cover - defensive
        return "لینک"
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host or "لینک"


def safe_filename(name: str, fallback: str = "file", max_length: int = 120) -> str:
    """Turn an arbitrary title into a file-system friendly name."""
    if not name:
        return fallback
    name = unicodedata.normalize("NFKC", str(name)).strip()
    name = _BAD_FILENAME_CHARS.sub("_", name)
    # collapse whitespace and dots that confuse some tools
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > max_length:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            keep = max_length - len(ext) - 1
            name = f"{stem[:keep]}.{ext}"
        else:
            name = name[:max_length]
    name = name.strip(" .")
    return name or fallback


def guess_extension(mime_type: Optional[str], url: Optional[str] = None) -> str:
    """Very small mime/url -> extension mapping (no external deps)."""
    mapping = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
        "video/x-matroska": ".mkv",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/ogg": ".ogg",
        "audio/opus": ".opus",
        "audio/wav": ".wav",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
        "application/zip": ".zip",
    }
    if mime_type:
        base = mime_type.split(";")[0].strip().lower()
        if base in mapping:
            return mapping[base]
    if url:
        suffix = Path(urlparse(url).path).suffix
        if suffix and len(suffix) <= 8 and re.fullmatch(r"\.[A-Za-z0-9]+", suffix):
            return suffix.lower()
    return ""


def shorten(text: str, limit: int = 64) -> str:
    """Trim long titles for captions/buttons."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def escape_markdown(text: str) -> str:
    """Escape Bale/Telegram markdown v1 special characters."""
    for char in ("_", "*", "`", "["):
        text = str(text).replace(char, f"\\{char}")
    return text
