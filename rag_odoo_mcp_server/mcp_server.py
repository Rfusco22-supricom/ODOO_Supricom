#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG Odoo MCP Server - Network-accessible MCP server that queries the Odoo instance PostgreSQL.

Runs as an HTTP server using SSE (Server-Sent Events) transport, similar to the Innova
License Manager MCP server. Tools allow listing tables, describing schema, and running
read-only SQL against the Odoo database.

Run (from project root or with PYTHONPATH including addons path):
    pip install "mcp[sse]" starlette uvicorn psycopg2-binary
    python -m rag_odoo_mcp_server.mcp_server --host 0.0.0.0 --port 8000

Or with env vars for DB (defaults work when running on same host as Odoo/PostgreSQL):
    set PGHOST=localhost
    set PGPORT=5432
    set PGUSER=odoo
    set PGPASSWORD=odoo
    set PGDATABASE=odoo
    python -m rag_odoo_mcp_server.mcp_server --port 8000

Claude Desktop / Cursor: add to MCP config:
    "rag-odoo": { "url": "http://<host>:8000/sse" }
"""

import argparse
import asyncio
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import RealDictCursor
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration - PostgreSQL (Odoo DB). Env vars override Odoo config file.
# ---------------------------------------------------------------------------
PG_CONFIG = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": int(os.environ.get("PGPORT", "5432")),
    "user": os.environ.get("PGUSER", "odoo"),
    "password": os.environ.get("PGPASSWORD", ""),
    "dbname": os.environ.get("PGDATABASE", "odoo"),
}

# MCP server bind (host/port). Overridden from Odoo Settings (ir_config_parameter) after DB connect.
MCP_BIND = {
    "host": os.environ.get("MCP_HOST", "0.0.0.0"),
    "port": int(os.environ.get("MCP_PORT", "8000")),
}


def _load_config_from_db(conn) -> None:
    """Load rag_odoo_mcp_server.* from ir_config_parameter and override PG_CONFIG and MCP_BIND."""
    global PG_CONFIG, MCP_BIND
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT key, value FROM ir_config_parameter WHERE key LIKE %s",
                ("rag_odoo_mcp_server.%",),
            )
            rows = cur.fetchall()
    except Exception as e:
        print(f"[WARNING] Could not load config from Odoo DB: {e}", file=sys.stderr)
        return
    params = {k: (v or "").strip() for k, v in rows}
    # MCP server bind
    if params.get("rag_odoo_mcp_server.mcp_host"):
        MCP_BIND["host"] = params["rag_odoo_mcp_server.mcp_host"]
    if params.get("rag_odoo_mcp_server.mcp_port"):
        try:
            MCP_BIND["port"] = int(params["rag_odoo_mcp_server.mcp_port"])
        except (TypeError, ValueError):
            pass
    # Database override (optional)
    if params.get("rag_odoo_mcp_server.db_host"):
        PG_CONFIG["host"] = params["rag_odoo_mcp_server.db_host"]
    if params.get("rag_odoo_mcp_server.db_port"):
        try:
            PG_CONFIG["port"] = int(params["rag_odoo_mcp_server.db_port"])
        except (TypeError, ValueError):
            pass
    if params.get("rag_odoo_mcp_server.db_user"):
        PG_CONFIG["user"] = params["rag_odoo_mcp_server.db_user"]
    if params.get("rag_odoo_mcp_server.db_password"):
        PG_CONFIG["password"] = params["rag_odoo_mcp_server.db_password"]
    if params.get("rag_odoo_mcp_server.db_name"):
        PG_CONFIG["dbname"] = params["rag_odoo_mcp_server.db_name"]
    if rows:
        print(f"[OK] Loaded config from Odoo (ir_config_parameter): host={MCP_BIND['host']} port={MCP_BIND['port']}", file=sys.stderr)


def _load_odoo_config(config_path: Optional[str] = None) -> None:
    """Optionally load PostgreSQL settings from Odoo config file (db_host, db_port, db_user, db_password, db_name)."""
    path = config_path or os.environ.get("ODOO_RC")
    if not path or not os.path.isfile(path):
        return
    try:
        from configparser import ConfigParser
        cfg = ConfigParser()
        cfg.read(path)
        if "options" in cfg:
            opt = cfg["options"]
            if opt.get("db_host"):
                PG_CONFIG["host"] = opt["db_host"]
            if opt.get("db_port"):
                PG_CONFIG["port"] = int(opt["db_port"])
            if opt.get("db_user"):
                PG_CONFIG["user"] = opt["db_user"]
            if opt.get("db_password"):
                PG_CONFIG["password"] = opt["db_password"]
            if opt.get("db_name"):
                PG_CONFIG["dbname"] = opt["db_name"]
            print(f"[OK] Loaded DB config from {path}", file=sys.stderr)
    except Exception as e:
        print(f"[WARNING] Could not load Odoo config from {path}: {e}", file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# Backend - PostgreSQL (Odoo) query logic
# ═══════════════════════════════════════════════════════════════════════════

class OdooPostgresBackend:
    """Query Odoo's PostgreSQL database. All DB calls are sync; run in executor from async."""

    def __init__(self):
        self._conn = None

    def connect(self) -> bool:
        if not PSYCOPG_AVAILABLE:
            print("[ERROR] psycopg2 not installed. pip install psycopg2-binary", file=sys.stderr)
            return False
        try:
            self._conn = psycopg2.connect(
                host=PG_CONFIG["host"],
                port=PG_CONFIG["port"],
                user=PG_CONFIG["user"],
                password=PG_CONFIG["password"],
                dbname=PG_CONFIG["dbname"],
                connect_timeout=10,
            )
            self._conn.autocommit = True
            # Load MCP host/port and optional DB overrides from Odoo Settings (ir_config_parameter)
            _load_config_from_db(self._conn)
            cur = self._conn.cursor()
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            cur.close()
            print(f"[OK] PostgreSQL (Odoo DB) at {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}", file=sys.stderr)
            print(f"     {version[:80]}...", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[WARNING] PostgreSQL connection failed: {e}", file=sys.stderr)
            return False

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _ensure_conn(self):
        if not self._conn or self._conn.closed:
            raise RuntimeError("Not connected to PostgreSQL. Reconnect and retry.")

    def list_tables(self, schema: str = "public") -> List[Dict[str, Any]]:
        """List tables in schema (default public). Returns table names and row counts optional."""
        self._ensure_conn()
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT c.relname AS table_name,
                       pg_size_pretty(pg_total_relation_size(c.oid)) AS size
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relkind = 'r'
                ORDER BY c.relname
            """, (schema,))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def describe_table(self, table_name: str, schema: str = "public") -> List[Dict[str, Any]]:
        """Return columns for a table: name, type, nullable, default."""
        self._ensure_conn()
        safe_schema = schema or "public"
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.attname AS column_name,
                       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                       NOT a.attnotnull AS nullable,
                       pg_get_expr(d.adbin, d.adrelid) AS default_expr
                FROM pg_attribute a
                LEFT JOIN pg_attrdef d ON a.attrelid = d.adrelid AND a.attnum = d.adnum
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = %s AND c.relname = %s
                  AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
            """, (safe_schema, table_name))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_table_row_count(self, table_name: str, schema: str = "public") -> int:
        """Return approximate or exact row count for a table."""
        self._ensure_conn()
        with self._conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    sql.Identifier(schema or "public"),
                    sql.Identifier(table_name),
                )
            )
            return cur.fetchone()[0]

    def run_readonly_query(self, query: str, max_rows: int = 500) -> Dict[str, Any]:
        """
        Run a read-only SQL query. Only SELECT is allowed; others raise.
        Returns rows as list of dicts and row count.
        """
        self._ensure_conn()
        q = query.strip()
        if not q.upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed. Got: " + q[:50])
        # Block obvious write patterns even in SELECT (e.g. SELECT ... INTO)
        if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE)\b", q, re.I):
            raise ValueError("Query must be read-only (SELECT only).")
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q)
            rows = cur.fetchmany(max_rows)
            columns = [d[0] for d in cur.description] if cur.description else []
        # Convert to list of dicts
        result = [dict(zip(columns, row)) for row in rows]
        for r in result:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif isinstance(v, (bytes, bytearray)):
                    r[k] = v.decode("utf-8", errors="replace")
        return {"row_count": len(result), "columns": columns, "rows": result}

    def get_odoo_models_info(self) -> List[Dict[str, Any]]:
        """List Odoo ORM models (from ir.model) with model name and description."""
        self._ensure_conn()
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT model, name, info
                FROM ir_model
                WHERE model IS NOT NULL AND model != ''
                ORDER BY model
                LIMIT 500
            """)
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_table_schema_pg(self, table_name: str, schema: str = "public") -> Dict[str, Any]:
        """Return full PG info for a table: columns, indexes, constraints (summary)."""
        self._ensure_conn()
        cols = self.describe_table(table_name, schema or "public")
        with self._conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = %s AND tablename = %s
            """, (schema or "public", table_name))
            indexes = [dict(r) for r in cur.fetchall()]
        return {"table": table_name, "schema": schema or "public", "columns": cols, "indexes": indexes}


# Run sync backend methods in thread pool for async handlers
def _run_sync(sync_fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, lambda: sync_fn(*args, **kwargs))


# ═══════════════════════════════════════════════════════════════════════════
# MCP tool definitions
# ═══════════════════════════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    types.Tool(
        name="list_tables",
        description="List all tables in the PostgreSQL schema (default: public). Returns table names and approximate size. Use this to discover Odoo tables.",
        inputSchema={
            "type": "object",
            "properties": {
                "schema": {"type": "string", "default": "public", "description": "Schema name (default: public)"},
            },
        },
    ),
    types.Tool(
        name="describe_table",
        description="Get column definitions for a table: column name, data type, nullable, default. Use after list_tables to inspect a specific table.",
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table name (e.g. res_partner, sale_order)"},
                "schema": {"type": "string", "default": "public"},
            },
            "required": ["table_name"],
        },
    ),
    types.Tool(
        name="get_table_row_count",
        description="Get the exact row count for a table. Useful to know table size before querying.",
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "schema": {"type": "string", "default": "public"},
            },
            "required": ["table_name"],
        },
    ),
    types.Tool(
        name="run_readonly_query",
        description="Run a read-only SQL query (SELECT only) against the Odoo PostgreSQL database. Use describe_table and list_tables first to build correct queries. Returns up to max_rows rows.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Single SELECT SQL statement"},
                "max_rows": {"type": "integer", "default": 500, "maximum": 2000, "description": "Max rows to return"},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_odoo_models_info",
        description="List Odoo ORM models from ir_model (model name, description). Helps map Odoo models to database tables (e.g. res.partner -> res_partner).",
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="get_table_schema_pg",
        description="Get full table schema: columns and indexes. Use for detailed inspection of a table.",
        inputSchema={
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "schema": {"type": "string", "default": "public"},
            },
            "required": ["table_name"],
        },
    ),
]


def _format_list_tables(result: List[Dict]) -> str:
    lines = [f"Tables in schema (total: {len(result)}):", ""]
    for r in result:
        lines.append(f"  - {r['table_name']}  ({r.get('size', '?')})")
    return "\n".join(lines)


def _format_describe(result: List[Dict]) -> str:
    if not result:
        return "No columns found (table or schema may not exist)."
    lines = ["Column | Type | Nullable | Default", "------ | ---- | -------- | -------"]
    for r in result:
        lines.append(f"{r['column_name']} | {r['data_type']} | {r['nullable']} | {r.get('default_expr') or ''}")
    return "\n".join(lines)


def _format_run_query(result: Dict) -> str:
    rows = result.get("rows", [])
    cols = result.get("columns", [])
    count = result.get("row_count", 0)
    if not cols:
        return f"No columns (empty result). Row count: {count}"
    header = " | ".join(cols)
    sep = "-" * min(80, len(header))
    lines = [f"Rows returned: {count}", f"Columns: {cols}", "", header, sep]
    for r in rows[:100]:  # cap display
        line = " | ".join(str(r.get(c, "")) for c in cols)
        lines.append(line)
    if len(rows) > 100:
        lines.append(f"... and {len(rows) - 100} more rows")
    return "\n".join(lines)


def _format_odoo_models(result: List[Dict]) -> str:
    lines = [f"Odoo models (ir_model) — {len(result)} entries:", ""]
    for r in result[:80]:
        lines.append(f"  - {r.get('model', '')}  |  {r.get('name', '') or ''}")
    if len(result) > 80:
        lines.append(f"  ... and {len(result) - 80} more")
    return "\n".join(lines)


def _format_schema_pg(result: Dict) -> str:
    lines = [f"Table: {result.get('schema', 'public')}.{result.get('table', '')}", ""]
    lines.append("Columns:")
    for c in result.get("columns", []):
        lines.append(f"  - {c['column_name']}: {c['data_type']} (nullable={c['nullable']})")
    lines.append("")
    lines.append("Indexes:")
    for ix in result.get("indexes", []):
        lines.append(f"  - {ix.get('indexname', '')}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# SSE server wiring
# ═══════════════════════════════════════════════════════════════════════════

def create_app(backend: OdooPostgresBackend) -> Starlette:
    """Build the Starlette ASGI app with MCP SSE transport."""

    mcp_server = Server("rag-odoo-postgres")
    sse_transport = SseServerTransport("/messages/")

    @mcp_server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        return TOOL_DEFINITIONS

    @mcp_server.call_tool()
    async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
        dispatch = {
            "list_tables": (backend.list_tables, _format_list_tables),
            "describe_table": (backend.describe_table, _format_describe),
            "get_table_row_count": (backend.get_table_row_count, lambda x: f"Row count: {x}"),
            "run_readonly_query": (backend.run_readonly_query, _format_run_query),
            "get_odoo_models_info": (backend.get_odoo_models_info, _format_odoo_models),
            "get_table_schema_pg": (backend.get_table_schema_pg, _format_schema_pg),
        }
        if name not in dispatch:
            raise ValueError(f"Unknown tool: {name}")

        method, formatter = dispatch[name]
        try:
            result = await _run_sync(method, **arguments)

            if formatter is None:
                text = json.dumps(result, indent=2, default=str)
            else:
                text = formatter(result)
            return [types.TextContent(type="text", text=text)]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {e}")]

    async def handle_sse(request: Request):
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_server.run(streams[0], streams[1], mcp_server.create_initialization_options())
        return Response()

    async def health(request: Request):
        ok = backend._conn is not None and not backend._conn.closed
        status = "ok" if ok else "disconnected"
        return Response(
            json.dumps({
                "status": status,
                "database": PG_CONFIG["dbname"],
                "host": PG_CONFIG["host"],
            }),
            media_type="application/json",
        )

    return Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=sse_transport.handle_post_message),
            Route("/health", endpoint=health, methods=["GET"]),
        ],
        middleware=[
            Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="RAG Odoo MCP Server — query Odoo instance PostgreSQL via MCP (SSE)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Listen port (default: 8000)",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to Odoo config file (e.g. odoo.conf) to read db_host, db_port, db_user, db_password, db_name",
    )
    args = parser.parse_args()

    # CLI args override env for host/port (Odoo Settings can override again after DB connect)
    MCP_BIND["host"] = args.host
    MCP_BIND["port"] = args.port

    _load_odoo_config(args.config)

    if not PSYCOPG_AVAILABLE:
        print("[FATAL] psycopg2 is required. Install: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    backend = OdooPostgresBackend()
    if not backend.connect():
        print("[FATAL] Cannot connect to PostgreSQL (Odoo DB). Check PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE.", file=sys.stderr)
        sys.exit(1)

    app = create_app(backend)
    # Use host/port from Odoo Settings (ir_config_parameter) if loaded; else CLI args
    host = MCP_BIND["host"]
    port = MCP_BIND["port"]
    print(f"[OK] RAG Odoo MCP Server starting on http://{host}:{port}", file=sys.stderr)
    print(f"[OK] SSE endpoint: http://{host}:{port}/sse", file=sys.stderr)
    print(f"[OK] Health check: http://{host}:{port}/health", file=sys.stderr)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
