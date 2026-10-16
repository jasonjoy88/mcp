"""Logging setup.

Mirrors the Go version's ``internal/logging`` package.
Uses JSON-formatted logs on stderr, matching slog JSON output.
"""

from __future__ import annotations

import logging
import sys

try:
    from pythonjsonlogger import jsonlogger

    _HAS_JSON_LOGGER = True
except ImportError:  # pragma: no cover
    _HAS_JSON_LOGGER = False


def setup(level: str = "info") -> None:
    """Configure the root logger with JSON output on stderr.

    Args:
        level: One of ``debug``, ``info``, ``warn``, ``error`` (case-insensitive).
    """
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    log_level = level_map.get(level.lower(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Avoid adding duplicate handlers if setup is called twice
    if root.handlers:
        for h in root.handlers:
            h.setLevel(log_level)
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(log_level)

    formatter: logging.Formatter
    if _HAS_JSON_LOGGER:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "time"},
        )
    else:  # pragma: no cover - fallback for environments without python-json-logger
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Convenience helper to get a named logger."""
    return logging.getLogger(name)
