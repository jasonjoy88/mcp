"""Multica REST API client.

Mirrors the Go version's ``internal/multica/client.go``.
Uses httpx for async HTTP requests.
"""

from .client import MulticaAPIError, MulticaClient  # noqa: F401

__all__ = ["MulticaClient", "MulticaAPIError"]
