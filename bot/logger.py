"""Logging helpers."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure a readable console logger once per process."""
    global _CONFIGURED
    numeric = getattr(logging, str(level).upper(), logging.INFO)
    if _CONFIGURED:
        logging.getLogger().setLevel(numeric)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(numeric)
    root.addHandler(handler)
    # httpx is very chatty about every single API call
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
