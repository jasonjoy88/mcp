"""HTTP middleware for multica-mcp.

Mirrors the Go version's ``internal/middleware`` package.
"""

from .throttle import LoginThrottle  # noqa: F401

__all__ = ["LoginThrottle"]
