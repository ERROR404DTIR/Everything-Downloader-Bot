"""Entry point: ``python main.py`` (or ``python -m bot.main``)."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from . import ensure_event_loop

ensure_event_loop()

from balethon import Client

from . import __version__
from .config import Config, ConfigError
from .handlers import BotHandlers, register
from .logger import get_logger, setup_logging

log = get_logger(__name__)


def build_client(config: Config) -> Client:
    """Create the balethon client pointed at the Bale Bot API."""
    client = Client(
        config.token,
        base_url=config.base_url,
        time_out=config.request_timeout,
        proxy=config.proxy,
    )
    return client


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="everything-downloader-bot",
        description="ربات دانلودر همه‌چیز برای پیام‌رسان بله (yt-dlp + balethon)",
    )
    parser.add_argument("-c", "--config", default=None, help="مسیر فایل config.json")
    parser.add_argument("--check", action="store_true", help="فقط صحت تنظیمات را بررسی کن و خارج شو")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        print(f"\n⛔ {exc}\n", file=sys.stderr)
        return 1

    setup_logging(config.log_level)
    if config.unknown_keys:
        log.warning("کلیدهای ناشناخته در config.json نادیده گرفته شدند: %s", ", ".join(config.unknown_keys))

    log.info("Everything Downloader Bot v%s", __version__)
    log.info("Bale API base url: %s", config.base_url)
    log.info("پوشهٔ دانلود: %s", config.download_path)

    if args.check:
        print("✅ config.json معتبر است.")
        return 0

    client = build_client(config)
    handlers = BotHandlers(client, config)
    register(client, handlers)

    try:
        client.run()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        log.info("خروج با Ctrl+C")
    except Exception:  # noqa: BLE001
        log.exception("ربات متوقف شد")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
