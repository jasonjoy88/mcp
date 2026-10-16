"""Configuration loading from environment variables.

Mirrors the Go version's ``internal/config`` package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""

    multica_base_url: str
    multica_token: str
    multica_workspace_id: str = ""
    multica_workspace_slug: str = ""
    mcp_transport: str = "stdio"
    log_level: str = "info"
    http_port: int = 8080
    read_only: bool = False
    mcp_api_key: str = ""


def _get_env(key: str, fallback: str = "") -> str:
    value = os.getenv(key, "")
    return value if value else fallback


def _get_env_int(key: str, fallback: int) -> int:
    value = _get_env(key, "")
    if not value:
        return fallback
    try:
        return int(value)
    except ValueError:
        return fallback


def _get_env_bool(key: str, fallback: bool) -> bool:
    value = _get_env(key, "")
    if not value:
        return fallback
    return value.lower() in ("1", "true", "yes", "on")


def load() -> Config:
    """Load configuration from environment variables.

    Raises:
        ValueError: if required variables are missing or invalid.
    """
    base_url = _get_env("MULTICA_BASE_URL", "")
    if not base_url:
        raise ValueError("MULTICA_BASE_URL is required")

    token = _get_env("MULTICA_TOKEN", "")
    if not token:
        raise ValueError("MULTICA_TOKEN is required")

    transport = _get_env("MCP_TRANSPORT", "stdio")
    if transport not in ("stdio", "http"):
        raise ValueError(f"MCP_TRANSPORT must be 'stdio' or 'http', got {transport!r}")

    return Config(
        multica_base_url=base_url.rstrip("/"),
        multica_token=token,
        multica_workspace_id=_get_env("MULTICA_WORKSPACE_ID", ""),
        multica_workspace_slug=_get_env("MULTICA_WORKSPACE_SLUG", ""),
        mcp_transport=transport,
        log_level=_get_env("LOG_LEVEL", "info"),
        http_port=_get_env_int("MCP_HTTP_PORT", 8080),
        read_only=_get_env_bool("MULTICA_READ_ONLY", False),
        mcp_api_key=_get_env("MCP_API_KEY", ""),
    )
