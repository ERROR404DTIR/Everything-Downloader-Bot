"""Loading and validating ``config.json``.

The user only has to fill in ``token``; every other key has a sane default so a
minimal ``config.json`` looks like this::

    {"token": "123456789:abcd..."}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_NAME = "config.json"

#: Hard limit of the Bale Bot API for one uploaded file (both upload and
#: download from Bale servers is limited — see https://docs.bale.ai).
BALE_HARD_UPLOAD_LIMIT_MB = 50


class ConfigError(Exception):
    """Raised when ``config.json`` is missing or contains invalid values."""


@dataclass
class Config:
    # --- the only mandatory key -----------------------------------------
    token: str = ""

    # --- Bale API -------------------------------------------------------
    base_url: str = "https://tapi.bale.ai"
    request_timeout: int = 600  # seconds, used for uploads of big files
    proxy: Optional[str] = None

    # --- downloader -----------------------------------------------------
    download_dir: str = "downloads"
    max_file_size_mb: int = BALE_HARD_UPLOAD_LIMIT_MB
    max_concurrent_downloads: int = 3
    allow_playlists: bool = False
    max_playlist_items: int = 10
    cookies_file: Optional[str] = None
    ffmpeg_location: Optional[str] = None
    #: Extra raw options handed to yt-dlp (advanced users only).
    ytdlp_options: Dict[str, Any] = field(default_factory=dict)

    # --- misc -----------------------------------------------------------
    log_level: str = "INFO"
    keep_downloaded_files: bool = False
    #: Seconds a "choose quality" keyboard stays valid.
    job_ttl_seconds: int = 1800

    # ------------------------------------------------------------------
    @property
    def max_file_size_bytes(self) -> int:
        return int(self.max_file_size_mb) * 1024 * 1024

    @property
    def download_path(self) -> Path:
        return Path(os.path.expanduser(self.download_dir)).resolve()

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Config":
        if not isinstance(raw, dict):
            raise ConfigError("محتوای config.json باید یک آبجکت JSON باشد.")

        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        data = {key: value for key, value in raw.items() if key in known}
        config = cls(**data)

        # normalize / validate
        config.token = str(config.token or "").strip()
        config.base_url = str(config.base_url or cls.base_url).rstrip("/")
        config.max_file_size_mb = int(config.max_file_size_mb or BALE_HARD_UPLOAD_LIMIT_MB)
        config.max_concurrent_downloads = max(1, int(config.max_concurrent_downloads or 1))
        config.max_playlist_items = max(1, min(50, int(config.max_playlist_items or 1)))
        config.job_ttl_seconds = max(60, int(config.job_ttl_seconds or 1800))
        config.request_timeout = max(30, int(config.request_timeout or 600))
        if config.max_file_size_mb > BALE_HARD_UPLOAD_LIMIT_MB:
            # Bale rejects anything bigger anyway; keep the config honest.
            config.max_file_size_mb = BALE_HARD_UPLOAD_LIMIT_MB
        if not isinstance(config.ytdlp_options, dict):
            config.ytdlp_options = {}
        if config.cookies_file:
            config.cookies_file = os.path.expanduser(str(config.cookies_file))
        if config.ffmpeg_location:
            config.ffmpeg_location = os.path.expanduser(str(config.ffmpeg_location))
        if config.proxy:
            config.proxy = str(config.proxy).strip() or None

        config._unknown_keys = unknown  # type: ignore[attr-defined]
        config.validate_token()
        return config

    def validate_token(self) -> None:
        if not self.token:
            raise ConfigError(
                "توکن ربات خالی است. فایل config.json را باز کنید و مقدار «token» را "
                "با توکنی که از @botfather در بله گرفته‌اید پر کنید."
            )
        if self.token.lower() in {
            "your_token", "token", "put_your_token_here",
            "put_your_bot_token_here", "توکن",
        }:
            raise ConfigError(
                "مقدار «token» در config.json هنوز جای‌نگهدار (placeholder) است. "
                "توکن واقعی ربات خود را از @botfather در بله بگیرید و در این فایل قرار دهید."
            )
        if ":" not in self.token:
            raise ConfigError(
                "توکن وارد شده معتبر نیست. توکن‌های بله ساختاری شبیه "
                "«123456789:abcd...» دارند."
            )

    @property
    def unknown_keys(self) -> list:
        return list(getattr(self, "_unknown_keys", []))

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "Config":
        config_path = Path(path) if path else Path(DEFAULT_CONFIG_NAME)
        if not config_path.is_absolute():
            # look next to the repository root as well, so the bot can be
            # started from any working directory.
            candidates = [
                Path.cwd() / config_path,
                Path(__file__).resolve().parent.parent / config_path,
            ]
            config_path = next((p for p in candidates if p.is_file()), candidates[0])

        if not config_path.is_file():
            raise ConfigError(
                f"فایل تنظیمات پیدا نشد: {config_path}\n"
                "یک نسخه از config.json بسازید و توکن ربات را داخل آن قرار دهید."
            )
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config.json یک JSON معتبر نیست: {exc}") from exc
        except OSError as exc:  # pragma: no cover - filesystem dependent
            raise ConfigError(f"خواندن config.json ممکن نشد: {exc}") from exc
        return cls.from_dict(raw)
