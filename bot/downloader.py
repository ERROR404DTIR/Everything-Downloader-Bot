"""The actual downloading engine.

Two kinds of sources are supported:

* **media sites** (YouTube, Instagram, Twitter/X, Aparat, SoundCloud, …) —
  handled by :mod:`yt_dlp`, so we get titles, thumbnails, formats and
  playlists for free;
* **direct file links** (``https://example.com/movie.mp4``, zip archives,
  PDFs, images, …) — handled with :mod:`aiohttp` streaming (and
  :mod:`requests` as a fallback probe), because yt-dlp would refuse them.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import unquote, urlparse

import aiohttp
import requests
import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from .config import Config
from .errors import (
    DownloadError,
    PlaylistNotAllowedError,
    TooLargeError,
    UnsupportedURLError,
)
from .jobs import JobCancelled
from .logger import get_logger
from .models import DownloadProgress, DownloadResult, FormatChoice, MediaInfo, RemoteInfo
from .utils import guess_extension, human_size, pretty_host, safe_filename

log = get_logger(__name__)

ProgressCallback = Callable[[DownloadProgress], Awaitable[None] | None]

#: Extensions we happily download without asking yt-dlp first.
DIRECT_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v", ".ts",
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
    ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz", ".apk", ".exe",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".srt",
}

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v", ".ts"}
_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_JUNK_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")

#: When a server does not tell us the size, we still stop at this point.
MAX_UNKNOWN_SIZE_STREAM = 4 * 1024 * 1024 * 1024


class _SilentLogger:
    """yt-dlp logger that routes messages into our own logger."""

    def debug(self, msg: str) -> None:  # noqa: D401 - yt-dlp protocol
        if msg.startswith("[debug] "):
            log.debug(msg)
        else:
            log.info(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.error("yt-dlp: %s", msg)


class _HookState:
    """Thread-safe-ish snapshot shared between yt-dlp threads and asyncio."""

    __slots__ = ("downloaded", "total", "speed", "eta", "status", "filename", "error")

    def __init__(self) -> None:
        self.downloaded = 0
        self.total: Optional[int] = None
        self.speed: Optional[float] = None
        self.eta: Optional[int] = None
        self.status = "starting"
        self.filename: Optional[str] = None
        self.error: Optional[BaseException] = None


class Downloader:
    """High level facade around yt-dlp + aiohttp."""

    def __init__(self, config: Config):
        self.config = config
        self.config.download_path.mkdir(parents=True, exist_ok=True)
        self._session: Optional[aiohttp.ClientSession] = None
        self.ffmpeg = self._detect_ffmpeg()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def _detect_ffmpeg(self) -> Optional[str]:
        if self.config.ffmpeg_location:
            candidate = Path(self.config.ffmpeg_location)
            if candidate.is_dir():
                candidate = candidate / "ffmpeg"
            if candidate.exists():
                return str(candidate)
            log.warning("ffmpeg_location در تنظیمات پیدا نشد: %s", candidate)
        return shutil.which("ffmpeg")

    @property
    def has_ffmpeg(self) -> bool:
        return bool(self.ffmpeg)

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120),
                headers={"User-Agent": self._user_agent()},
            )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "Downloader":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    @staticmethod
    def _user_agent() -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    # ------------------------------------------------------------------
    # analysis
    # ------------------------------------------------------------------
    async def analyze(self, url: str) -> MediaInfo:
        """Inspect a link and return metadata without downloading it."""
        url = (url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise UnsupportedURLError()
        if url.lower().startswith(("https://tapi.bale.ai", "https://ble.ir")):
            raise UnsupportedURLError("لینک‌های مربوط به خود بله قابل دانلود نیستند.")

        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in DIRECT_EXTENSIONS:
            remote = await self.probe_remote(url)
            if remote is not None and self._looks_downloadable(remote):
                return self._remote_to_info(url, remote)

        try:
            info = await asyncio.to_thread(self._analyze_with_ytdlp, url)
        except UnsupportedURLError:
            raise
        except Exception as exc:  # noqa: BLE001 - yt-dlp raises many types
            log.info("yt-dlp نتوانست لینک را تحلیل کند (%s) — تلاش برای دانلود مستقیم", exc)
            remote = await self.probe_remote(url)
            if remote is not None and self._looks_downloadable(remote):
                return self._remote_to_info(url, remote)
            raise UnsupportedURLError(detail=f"analyze failed: {exc}") from exc

        if info.extractor == "generic" and not info.is_playlist:
            # yt-dlp treated the link as a plain file; probing gives us the
            # real size/type and lets us use the faster streaming downloader.
            remote = await self.probe_remote(url)
            if remote is not None and self._looks_downloadable(remote):
                probed = self._remote_to_info(url, remote)
                if probed.kind == info.kind or info.kind == "file":
                    return probed
        return info

    def _analyze_with_ytdlp(self, url: str) -> MediaInfo:
        options = self._base_ytdlp_options()
        options.update(
            {
                "skip_download": True,
                "noplaylist": not self.config.allow_playlists,
                "extract_flat": "in_playlist",
                "playlistend": self.config.max_playlist_items,
            }
        )
        try:
            with yt_dlp.YoutubeDL(options) as ydl:  # type: ignore[arg-type]
                info = ydl.extract_info(url, download=False)
        except YtDlpDownloadError as exc:
            raise UnsupportedURLError(detail=str(exc)) from exc
        if not info:
            raise UnsupportedURLError(detail="yt-dlp returned no metadata")
        return self._info_from_ytdlp(url, info)

    def _info_from_ytdlp(self, url: str, info: Dict[str, Any]) -> MediaInfo:
        is_playlist = info.get("_type") == "playlist" or "entries" in info
        entries = info.get("entries") or []
        if is_playlist and not self.config.allow_playlists:
            raise PlaylistNotAllowedError()

        first = info
        if is_playlist:
            entries = [e for e in entries if e]
            if not entries:
                raise UnsupportedURLError("پلی‌لیست خالی است.")
            first = entries[0]

        media = MediaInfo(
            url=url,
            title=str(info.get("title") or first.get("title") or "بدون عنوان"),
            duration=info.get("duration") or first.get("duration"),
            uploader=info.get("uploader") or first.get("uploader"),
            thumbnail=first.get("thumbnail"),
            ext=first.get("ext"),
            extractor=str(info.get("extractor_key") or info.get("extractor") or "").lower(),
            is_playlist=is_playlist,
            entry_count=len(entries) if is_playlist else 0,
        )
        if is_playlist:
            media.kind = "playlist"
            return media

        media.filesize = self._best_filesize(info)
        media.kind = self._guess_kind(info)
        return media

    @staticmethod
    def _best_filesize(info: Dict[str, Any]) -> Optional[int]:
        for key in ("filesize", "filesize_approx"):
            value = info.get(key)
            if value:
                return int(value)
        formats = info.get("formats") or []
        sizes = [f.get("filesize") or f.get("filesize_approx") for f in formats]
        sizes = [int(s) for s in sizes if s]
        return max(sizes) if sizes else None

    @staticmethod
    def _guess_kind(info: Dict[str, Any]) -> str:
        ext = (info.get("ext") or "").lower()
        vcodec = info.get("vcodec")
        acodec = info.get("acodec")
        if ext in _IMAGE_EXTENSIONS:
            return "image"
        if ext in _AUDIO_EXTENSIONS and (vcodec in (None, "none")):
            return "audio"
        if vcodec and vcodec != "none":
            return "video"
        if acodec and acodec != "none":
            return "audio"
        if ext in _AUDIO_EXTENSIONS:
            return "audio"
        return "file"

    # ------------------------------------------------------------------
    # remote / direct files
    # ------------------------------------------------------------------
    async def probe_remote(self, url: str) -> Optional[RemoteInfo]:
        """HEAD (or ranged GET) a URL and return its basic metadata."""
        await self.start()
        assert self._session is not None
        headers = {"User-Agent": self._user_agent(), "Accept": "*/*"}
        try:
            async with self._session.head(url, allow_redirects=True, headers=headers) as response:
                if response.status < 400:
                    return self._remote_from_headers(url, response.headers)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.debug("HEAD failed for %s: %s", url, exc)

        # some servers reject HEAD — try a 1-byte ranged GET
        try:
            async with self._session.get(
                url, allow_redirects=True, headers={**headers, "Range": "bytes=0-0"}
            ) as response:
                if response.status < 400:
                    return self._remote_from_headers(url, response.headers)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.debug("ranged GET failed for %s: %s", url, exc)
        except Exception as exc:  # noqa: BLE001 - e.g. too many redirects
            log.debug("ranged GET crashed for %s: %s", url, exc)

        # last resort: requests, executed in a worker thread
        try:
            return await asyncio.to_thread(self._probe_with_requests, url)
        except Exception as exc:  # noqa: BLE001
            log.debug("requests probe failed for %s: %s", url, exc)
            return None

    def _probe_with_requests(self, url: str) -> Optional[RemoteInfo]:
        response = requests.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=30,
            headers={"User-Agent": self._user_agent()},
        )
        try:
            if response.status_code >= 400:
                return None
            return self._remote_from_headers(url, response.headers)
        finally:
            response.close()

    def _remote_from_headers(self, url: str, headers: Any) -> RemoteInfo:
        content_type = headers.get("Content-Type", "") or ""
        length = headers.get("Content-Length")
        try:
            size = int(length) if length and length.isdigit() else None
        except (TypeError, ValueError):  # pragma: no cover - defensive
            size = None
        filename = None
        disposition = headers.get("Content-Disposition") or ""
        match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", disposition, re.IGNORECASE)
        if match:
            filename = unquote(match.group(1).strip())
        if not filename:
            path_name = Path(unquote(urlparse(url).path)).name
            filename = path_name or None
        return RemoteInfo(
            url=url,
            size=size,
            content_type=content_type,
            filename=filename,
            supports_ranges="bytes" in (headers.get("Accept-Ranges") or "").lower(),
        )

    @staticmethod
    def _looks_downloadable(remote: RemoteInfo) -> bool:
        content_type = (remote.content_type or "").lower()
        if not content_type:
            return remote.size is not None
        if content_type.startswith(("text/html", "application/xhtml")):
            return False
        return True

    def _remote_to_info(self, url: str, remote: RemoteInfo) -> MediaInfo:
        content_type = (remote.content_type or "").lower()
        filename = remote.filename or ""
        ext = guess_extension(content_type, filename) or Path(urlparse(url).path).suffix.lower()
        if content_type.startswith("video/"):
            kind = "video"
        elif content_type.startswith("audio/"):
            kind = "audio"
        elif content_type.startswith("image/"):
            kind = "image"
        elif ext in _VIDEO_EXTENSIONS:
            kind = "video"
        elif ext in _AUDIO_EXTENSIONS:
            kind = "audio"
        elif ext in _IMAGE_EXTENSIONS:
            kind = "image"
        else:
            kind = "file"
        title = remote.filename or Path(unquote(urlparse(url).path)).name or pretty_host(url)
        return MediaInfo(
            url=url,
            title=title,
            kind=kind,
            filesize=remote.size,
            ext=ext.lstrip(".") or None,
            extractor="direct",
        )

    # ------------------------------------------------------------------
    # choices
    # ------------------------------------------------------------------
    def build_choices(self, info: MediaInfo) -> List[FormatChoice]:
        if info.kind == "audio" or info.is_playlist:
            return []
        if info.kind == "image" or info.kind == "file":
            return []
        choices = [FormatChoice("best", "بهترین کیفیت موجود", "video")]
        for height in (1080, 720, 480, 360):
            choices.append(FormatChoice(str(height), f"{height}p", "video", height))
        if self.has_ffmpeg:
            choices.append(FormatChoice("audio", "فقط صدا (MP3)", "audio"))
        else:
            choices.append(FormatChoice("audio", "فقط صدا", "audio"))
        return choices

    def default_choice(self, info: MediaInfo) -> FormatChoice:
        if info.kind == "audio":
            return FormatChoice("audio", "فقط صدا", "audio")
        return FormatChoice("best", "بهترین کیفیت موجود", "video")

    # ------------------------------------------------------------------
    # download
    # ------------------------------------------------------------------
    async def download(
        self,
        url: str,
        choice: FormatChoice,
        info: MediaInfo,
        progress: ProgressCallback | None = None,
        cancel_event: asyncio.Event | None = None,
        job_dir: Path | None = None,
    ) -> DownloadResult:
        """Download ``url`` and return paths + metadata of the produced files."""
        if job_dir is None:
            job_dir = self.config.download_path / f"job_{os.urandom(6).hex()}"
        job_dir = Path(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)

        if info.extractor in {"direct", "url", None} and info.kind in {"video", "audio", "image", "file"}:
            # direct link -> simple streaming download
            try:
                return await self._download_direct(url, info, progress, cancel_event, job_dir)
            except UnsupportedURLError:
                pass  # fall back to yt-dlp (e.g. a page that only *looks* direct)

        return await self._download_with_ytdlp(url, choice, info, progress, cancel_event, job_dir)

    async def _download_direct(
        self,
        url: str,
        info: MediaInfo,
        progress: ProgressCallback | None,
        cancel_event: asyncio.Event | None,
        job_dir: Path,
    ) -> DownloadResult:
        await self.start()
        assert self._session is not None
        remote = await self.probe_remote(url)
        if remote is None:
            raise DownloadError("اتصال به سرور مقصد ممکن نشد.")
        if not self._looks_downloadable(remote):
            raise UnsupportedURLError(detail="direct download refused: html content type")

        max_bytes = self.config.max_file_size_bytes
        if remote.size and remote.size > max_bytes:
            raise TooLargeError(remote.size, max_bytes)

        ext = guess_extension(remote.content_type, remote.filename or url) or ".bin"
        base_name = safe_filename(
            remote.filename or info.title or "download",
            fallback="download",
        )
        if not Path(base_name).suffix:
            base_name += ext
        target = job_dir / base_name
        part = target.with_suffix(target.suffix + ".part")

        headers = {"User-Agent": self._user_agent(), "Accept": "*/*"}
        downloaded = 0
        last_report = 0.0
        loop = asyncio.get_running_loop()
        async with self._session.get(url, headers=headers, allow_redirects=True) as response:
            if response.status >= 400:
                raise DownloadError(f"سرور مقصد خطای {response.status} برگرداند.")
            total = remote.size or (
                int(response.headers["Content-Length"])
                if response.headers.get("Content-Length", "").isdigit()
                else None
            )
            if total and total > max_bytes:
                raise TooLargeError(total, max_bytes)
            if total is None:
                # unknown size: never let a runaway stream fill the disk
                total = min(max_bytes, MAX_UNKNOWN_SIZE_STREAM)
            with open(part, "wb") as handle:
                async for chunk in response.content.iter_chunked(64 * 1024):
                    if cancel_event is not None and cancel_event.is_set():
                        raise JobCancelled()
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise TooLargeError(downloaded, max_bytes)
                    handle.write(chunk)
                    now = loop.time()
                    if progress and (now - last_report > 1.5):
                        last_report = now
                        await _maybe_await(
                            progress(
                                DownloadProgress(
                                    stage="download",
                                    filename=target.name,
                                    downloaded=downloaded,
                                    total=total,
                                )
                            )
                        )
        part.replace(target)
        if target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise DownloadError("فایل دریافت شده خالی است.")
        if progress:
            await _maybe_await(
                progress(
                    DownloadProgress(
                        stage="download",
                        filename=target.name,
                        downloaded=target.stat().st_size,
                        total=target.stat().st_size,
                    )
                )
            )
        return DownloadResult(
            files=[target],
            title=info.title or target.stem,
            source_url=url,
            kind=info.kind if info.kind in {"video", "audio", "image"} else "file",
            job_dir=job_dir,
        )

    async def _download_with_ytdlp(
        self,
        url: str,
        choice: FormatChoice,
        info: MediaInfo,
        progress: ProgressCallback | None,
        cancel_event: asyncio.Event | None,
        job_dir: Path,
    ) -> DownloadResult:
        state = _HookState()
        max_bytes = self.config.max_file_size_bytes
        options = self._base_ytdlp_options()
        options.update(self._format_options(choice))
        options.update(
            {
                "outtmpl": str(job_dir / "%(title).120B [%(id)s].%(ext)s"),
                "noplaylist": not self.config.allow_playlists,
                "playlistend": self.config.max_playlist_items,
                "progress_hooks": [lambda d: self._on_progress(d, state, cancel_event, max_bytes)],
                "postprocessor_hooks": [lambda d: self._on_postprocess(d, state)],
                "max_filesize": max_bytes,
            }
        )

        monitor_stop = asyncio.Event()

        async def monitor() -> None:
            last: tuple = ()
            while not monitor_stop.is_set():
                snapshot = (
                    state.downloaded,
                    state.total,
                    state.speed,
                    state.eta,
                    state.status,
                    state.filename,
                )
                if progress and snapshot != last:
                    last = snapshot
                    await _maybe_await(
                        progress(
                            DownloadProgress(
                                stage="convert" if state.status == "processing" else "download",
                                filename=state.filename,
                                downloaded=state.downloaded,
                                total=state.total,
                                speed=state.speed,
                                eta=state.eta,
                            )
                        )
                    )
                if state.error is not None:
                    break
                try:
                    await asyncio.wait_for(monitor_stop.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue

        monitor_task = asyncio.create_task(monitor())
        try:
            result = await asyncio.to_thread(self._run_ytdlp, url, options, state)
        finally:
            monitor_stop.set()
            await asyncio.gather(monitor_task, return_exceptions=True)

        if state.error is not None:
            error = state.error
            if isinstance(error, JobCancelled):
                raise JobCancelled()
            if isinstance(error, TooLargeError):
                raise error
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled()
        files = self._collect_files(job_dir)
        if not files:
            raise DownloadError("هیچ فایلی توسط دانلودر تولید نشد.")

        final = result or {}
        requested = final.get("requested_downloads") or []
        if requested:
            final = {**final, **{k: v for k, v in requested[0].items() if v is not None}}

        kind = info.kind if info.kind != "playlist" else "video"
        if final.get("vcodec") == "none":
            kind = "audio"
        elif final.get("ext") in _AUDIO_EXTENSIONS:
            kind = "audio"
        elif final.get("width") or final.get("vcodec"):
            kind = "video"

        return DownloadResult(
            files=files,
            title=str(final.get("title") or info.title or files[0].stem),
            source_url=url,
            duration=final.get("duration") or info.duration,
            width=final.get("width"),
            height=final.get("height"),
            kind=kind,
            thumbnail=info.thumbnail,
            uploader=info.uploader,
            job_dir=job_dir,
            is_playlist=bool(info.is_playlist),
        )

    def _run_ytdlp(self, url: str, options: Dict[str, Any], state: _HookState) -> Optional[Dict[str, Any]]:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:  # type: ignore[arg-type]
                return ydl.extract_info(url, download=True)
        except (JobCancelled, TooLargeError) as exc:
            state.error = exc
            return None
        except YtDlpDownloadError as exc:
            state.error = DownloadError(detail=str(exc))
            return None
        except Exception as exc:  # noqa: BLE001
            state.error = DownloadError(detail=str(exc))
            return None

    @staticmethod
    def _on_progress(
        data: Dict[str, Any],
        state: _HookState,
        cancel_event: asyncio.Event | None,
        max_bytes: int,
    ) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise JobCancelled()
        status = data.get("status")
        if status == "downloading":
            state.status = "downloading"
            state.downloaded = int(data.get("downloaded_bytes") or 0)
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            state.total = int(total) if total else None
            state.speed = data.get("speed")
            state.eta = data.get("eta")
            state.filename = os.path.basename(data.get("filename") or "") or None
            if state.downloaded > max_bytes:
                raise TooLargeError(state.downloaded, max_bytes)
        elif status == "finished":
            state.status = "processing"
            state.downloaded = int(data.get("downloaded_bytes") or state.downloaded)
            state.filename = os.path.basename(data.get("filename") or "") or state.filename
        elif status == "error":
            state.error = DownloadError(detail="yt-dlp reported an error")

    @staticmethod
    def _on_postprocess(data: Dict[str, Any], state: _HookState) -> None:
        if data.get("status") == "started":
            state.status = "processing"

    # ------------------------------------------------------------------
    # yt-dlp options
    # ------------------------------------------------------------------
    def _base_ytdlp_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _SilentLogger(),
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 4,
            "nocheckcertificate": False,
            "ignoreerrors": False,
            "no_color": True,
            "windowsfilenames": False,
            "trim_file_name": 150,
            "overwrites": True,
            "writethumbnail": False,
            "writesubtitles": False,
            "cachedir": False,
        }
        if self.ffmpeg:
            options["ffmpeg_location"] = self.ffmpeg
        if self.config.cookies_file:
            options["cookiefile"] = self.config.cookies_file
        if self.config.proxy:
            options["proxy"] = self.config.proxy
        options.update(self.config.ytdlp_options)
        return options

    def _format_options(self, choice: FormatChoice) -> Dict[str, Any]:
        if choice.kind == "audio":
            options: Dict[str, Any] = {"format": "bestaudio/best"}
            if self.has_ffmpeg:
                options["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ]
            return options

        height = choice.max_height
        if not self.has_ffmpeg:
            # keep a single file so no muxing is required
            if height:
                return {"format": f"best[height<={height}]/best"}
            return {"format": "best"}

        if height:
            selector = (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/bestvideo+bestaudio/best"
            )
        else:
            selector = "bestvideo*+bestaudio/best"
        return {"format": selector, "merge_output_format": "mp4"}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_files(job_dir: Path) -> List[Path]:
        files: List[Path] = []
        for path in sorted(Path(job_dir).iterdir()):
            if not path.is_file():
                continue
            if path.name.endswith(_JUNK_SUFFIXES):
                continue
            files.append(path)
        return files

    def cleanup(self, job_dir: Path | None) -> None:
        if job_dir is None:
            return
        job_dir = Path(job_dir)
        if not job_dir.exists():
            return
        if self.config.keep_downloaded_files:
            log.info("نگه‌داشتن فایل‌ها در %s (keep_downloaded_files=true)", job_dir)
            return
        shutil.rmtree(job_dir, ignore_errors=True)

    def describe(self, info: MediaInfo) -> str:
        """Human readable summary used in the «choose quality» prompt."""
        lines = [f"🎬 {info.title}"]
        if info.uploader and info.uploader != info.title:
            lines.append(f"👤 {info.uploader}")
        if info.duration:
            from .utils import human_duration

            lines.append(f"⏱ {human_duration(info.duration)}")
        if info.filesize:
            lines.append(f"📦 حجم تقریبی: {human_size(info.filesize)}")
        if info.is_playlist:
            lines.append(f"📚 {info.entry_count} مورد در پلی‌لیست")
        return "\n".join(lines)


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value
