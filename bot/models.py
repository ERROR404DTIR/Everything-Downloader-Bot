"""Plain data containers shared by the downloader, handlers and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# downloader
# ---------------------------------------------------------------------------
@dataclass
class MediaInfo:
    """Metadata returned by yt-dlp before an actual download."""

    url: str
    title: str = "بدون عنوان"
    kind: str = "video"          # video | audio | image | file | playlist
    duration: Optional[int] = None
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    filesize: Optional[int] = None
    ext: Optional[str] = None
    entry_count: int = 0
    is_playlist: bool = False
    extractor: Optional[str] = None

    @property
    def is_direct_file(self) -> bool:
        """True when the link is a plain file URL we stream ourselves."""
        return self.extractor == "direct"


@dataclass
class FormatChoice:
    """One quality option the user can pick from the inline keyboard."""

    key: str                       # best | 1080 | 720 | 480 | 360 | audio
    label: str
    kind: str = "video"            # video | audio
    max_height: Optional[int] = None


@dataclass
class DownloadProgress:
    """A single progress tick, produced by yt-dlp hooks or aiohttp streams."""

    stage: str = "download"        # download | convert | upload
    filename: Optional[str] = None
    downloaded: int = 0
    total: Optional[int] = None
    speed: Optional[float] = None  # bytes / second
    eta: Optional[int] = None      # seconds

    @property
    def percent(self) -> Optional[float]:
        if not self.total:
            return None
        return max(0.0, min(100.0, self.downloaded * 100.0 / self.total))


@dataclass
class DownloadResult:
    """Everything the sender needs in order to deliver the file(s)."""

    files: List[Path] = field(default_factory=list)
    title: str = "بدون عنوان"
    source_url: Optional[str] = None
    duration: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    kind: str = "file"             # video | audio | image | file
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    job_dir: Optional[Path] = None
    is_playlist: bool = False


# ---------------------------------------------------------------------------
# remote probing
# ---------------------------------------------------------------------------
@dataclass
class RemoteInfo:
    url: str
    size: Optional[int] = None
    content_type: Optional[str] = None
    filename: Optional[str] = None
    supports_ranges: bool = False
