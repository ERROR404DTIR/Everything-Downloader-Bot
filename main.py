#!/usr/bin/env python3
"""Convenience launcher so the bot can be started with ``python main.py``.

The real logic lives in the :mod:`bot` package.
"""

from bot.main import main

if __name__ == "__main__":
    raise SystemExit(main())
