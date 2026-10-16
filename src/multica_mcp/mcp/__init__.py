"""MCP server for multica-mcp.

Mirrors the Go version's ``internal/mcp/server.go``.
"""

from .server import MCPServer  # noqa: F401

__all__ = ["MCPServer"]
