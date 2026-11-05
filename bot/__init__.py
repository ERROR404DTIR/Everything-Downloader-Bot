"""Everything Downloader Bot — a Bale (بله) bot powered by yt-dlp and balethon."""

import asyncio
import warnings


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Ensure an asyncio event loop exists on the current thread.

    In Python 3.14+, `asyncio.get_event_loop()` no longer creates an event
    loop implicitly if none exists on the current thread, raising RuntimeError.
    `balethon` initializes sync support at module import time using
    `get_event_loop()`, which fails without an existing loop.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


# Guarantee event loop before any submodules (or balethon) are imported
ensure_event_loop()

__version__ = "1.0.0"
__all__ = ["__version__", "ensure_event_loop"]
