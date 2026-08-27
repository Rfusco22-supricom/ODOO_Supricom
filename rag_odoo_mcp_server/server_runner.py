# -*- coding: utf-8 -*-
"""
Start the RAG Odoo MCP server in a background thread when the module is loaded.
Uses Odoo's DB config so installing the module is enough (single-process mode only).
"""

import logging
import threading

_logger = logging.getLogger(__name__)

_mcp_thread = None
_mcp_started = False


def _run_mcp_server():
    """Run uvicorn in the current thread (called from the daemon thread)."""
    try:
        import odoo.tools.config as config

        # Import MCP server components and inject Odoo DB config
        from . import mcp_server as mcp_mod

        # Set PG_CONFIG from Odoo's config so we connect to the same DB
        if getattr(config, "db_host", None):
            mcp_mod.PG_CONFIG["host"] = config.db_host
        if getattr(config, "db_port", None):
            try:
                mcp_mod.PG_CONFIG["port"] = int(config.db_port)
            except (TypeError, ValueError):
                pass
        if getattr(config, "db_user", None):
            mcp_mod.PG_CONFIG["user"] = config.db_user
        if getattr(config, "db_password", None):
            mcp_mod.PG_CONFIG["password"] = config.db_password
        if getattr(config, "db_name", None):
            mcp_mod.PG_CONFIG["dbname"] = config.db_name

        backend = mcp_mod.OdooPostgresBackend()
        if not backend.connect():
            _logger.warning("RAG Odoo MCP server: PostgreSQL connection failed; MCP server not started.")
            return

        app = mcp_mod.create_app(backend)
        host = mcp_mod.MCP_BIND["host"]
        port = mcp_mod.MCP_BIND["port"]
        _logger.info("RAG Odoo MCP server starting on http://%s:%s (SSE: /sse)", host, port)
        mcp_mod.uvicorn.run(app, host=host, port=port, log_level="warning")
    except Exception as e:
        _logger.exception("RAG Odoo MCP server thread failed: %s", e)


def start_mcp_server():
    """Start the MCP server in a daemon thread if not already started. Call from module __init__."""
    global _mcp_thread, _mcp_started
    if _mcp_started:
        return
    try:
        import odoo.tools.config as config
    except ImportError:
        return
    workers = getattr(config, "workers", 0) or 0
    if workers != 0:
        _logger.info(
            "RAG Odoo MCP server: not started (workers=%s). "
            "Run Odoo with --workers=0 or start the MCP server manually.",
            workers,
        )
        return
    try:
        # Lazy import so optional deps only required when actually starting
        import uvicorn  # noqa: F401
        from mcp.server.sse import SseServerTransport  # noqa: F401
    except ImportError as e:
        _logger.warning(
            "RAG Odoo MCP server not started: missing dependencies (%s). "
            "Install: pip install -r rag_odoo_mcp_server/requirements-mcp.txt",
            e,
        )
        return
    _mcp_started = True
    _mcp_thread = threading.Thread(target=_run_mcp_server, name="rag-odoo-mcp-server", daemon=True)
    _mcp_thread.start()
