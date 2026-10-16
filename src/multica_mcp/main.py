"""Main entry point for multica-mcp.

Mirrors the Go version's ``main.go``.

Supports two MCP transports:
- ``stdio`` (default): standard input/output, for IDE integration.
- ``http``: SSE-based HTTP server, for remote deployment.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from .app import UseCase
from .config import Config, load
from .logging_setup import setup as setup_logging
from .mcp import MCPServer
from .middleware import LoginThrottle
from .multica import MulticaClient
from .version import MULTICA_API, VERSION

logger = logging.getLogger(__name__)


def main() -> None:
    """Synchronous entry point (used by the CLI script)."""
    try:
        asyncio.run(_main_async())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


async def _main_async() -> None:
    # 1. Load configuration
    try:
        cfg = load()
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    # 2. Set up logging
    setup_logging(cfg.log_level)
    logger.info(
        "starting multica-mcp",
        extra={
            "version": VERSION,
            "multica_api": MULTICA_API,
            "transport": cfg.mcp_transport,
            "read_only": cfg.read_only,
        },
    )

    # 3. Create Multica client
    client = MulticaClient(
        base_url=cfg.multica_base_url,
        token=cfg.multica_token,
        client_version=VERSION,
    )

    # 4. Resolve workspace scope
    await _resolve_workspace(client, cfg)

    # 5. Build use case and MCP server
    use_case = UseCase(client, read_only=cfg.read_only)
    mcp_server = MCPServer(use_case, read_only=cfg.read_only)

    # 6. Run transport
    try:
        if cfg.mcp_transport == "http":
            await _run_http(mcp_server, cfg)
        else:
            await _run_stdio(mcp_server)
    finally:
        await client.aclose()


# ---- workspace resolution ------------------------------------------------


async def _resolve_workspace(client: MulticaClient, cfg: Config) -> None:
    """Set the workspace scope on the client.

    Priority:
    1. Explicit slug (MULTICA_WORKSPACE_SLUG)
    2. Explicit ID (MULTICA_WORKSPACE_ID)
    3. Auto-detect: if there's exactly one workspace, use it
    """
    slug = cfg.multica_workspace_slug.strip()
    ws_id = cfg.multica_workspace_id.strip()

    if slug:
        client.set_workspace_scope(slug=slug)
        logger.info("workspace scope from slug", extra={"slug": slug})
        return

    if not ws_id:
        ws_id = await _auto_detect_workspace(client)

    if not ws_id:
        print(
            "MULTICA_WORKSPACE_ID or MULTICA_WORKSPACE_SLUG is required, "
            "or a single workspace must exist",
            file=sys.stderr,
        )
        sys.exit(1)

    client.set_workspace_scope(workspace_id=ws_id)
    logger.info("workspace scope from id")


async def _auto_detect_workspace(client: MulticaClient) -> str:
    """Try to auto-detect a single workspace.

    Returns the workspace ID if exactly one exists, else "".
    """
    try:
        workspaces = await client.list_workspaces()
    except Exception as exc:
        logger.warning("failed to list workspaces for auto-detection",
                       extra={"error": str(exc)})
        return ""

    if len(workspaces) == 1:
        ws = workspaces[0]
        logger.info(
            "auto-detected single workspace",
            extra={"workspace_id": ws.id, "name": ws.name},
        )
        return ws.id

    if len(workspaces) > 1:
        print("multiple workspaces found; set MULTICA_WORKSPACE_ID or "
              "MULTICA_WORKSPACE_SLUG to one of:", file=sys.stderr)
        for ws in workspaces:
            slug = ws.slug or "(no slug)"
            print(f"  {ws.id} ({ws.name}) slug={slug}", file=sys.stderr)

    return ""


# ---- stdio transport -----------------------------------------------------


async def _run_stdio(mcp_server: MCPServer) -> None:
    """Run the MCP server over stdin/stdout."""
    from mcp.server.stdio import stdio_server

    server = mcp_server.server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# ---- http / sse transport ------------------------------------------------


async def _run_http(mcp_server: MCPServer, cfg: Config) -> None:
    """Run the MCP server as an HTTP (SSE) service."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route

    sse = SseServerTransport("/mcp/")

    server = mcp_server.server

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send  # type: ignore[attr-defined]
        ) as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
        return None  # type: ignore[return-value]

    routes = [
        Route("/mcp", endpoint=handle_sse),
        Mount("/mcp", app=sse.handle_post_message),  # type: ignore[arg-type]
    ]

    app = Starlette(routes=routes, debug=False)

    # Wrap with API key + throttle if configured
    if cfg.mcp_api_key:
        throttle = LoginThrottle(
            max_failures=5,
            window=60.0,
            ban_duration=900.0,
        )
        app = throttle.wrap_app(cfg.mcp_api_key, app)
        logger.info(
            "API key authentication enabled",
            extra={"max_failures": 5, "ban_duration": "15m"},
        )

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=cfg.http_port,
        log_level=cfg.log_level,
    )
    server_inst = uvicorn.Server(config)

    logger.info("starting HTTP MCP server", extra={"addr": f":{cfg.http_port}"})

    # Graceful shutdown on SIGINT / SIGTERM
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("shutdown signal received")
        stop_event.set()
        server_inst.should_exit = True

    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler for all signals
        pass

    await server_inst.serve()


if __name__ == "__main__":
    main()
