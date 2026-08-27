# -*- coding: utf-8 -*-
"""
MCP server exposed as part of the Odoo HTTP server.
GET /mcp/sse — SSE stream (client connects here, receives session id).
POST /mcp/messages — JSON-RPC (client sends requests with session id).
No extra process: installing the module is enough.

IMPORTANT:
- When Odoo has multiple databases, add ?db=<dbname> to the URL.
- Use the URL that works for /mcp/health in your setup. If http://host:port/mcp/health works
  (no /odoo), use that base for SSE too: http://host:port/mcp/sse?db=mydb
  If your deployment only exposes Odoo under /odoo, then /odoo/mcp/... may be handled by the
  web frontend (controller/action) and show "Missing Action" — in that case use the root path.

When using mcp-remote (Cursor/Claude), add: --transport sse-only

If an API key is configured in Settings, clients must send it in the request:
  Authorization: Bearer <key>   or   X-API-Key: <key>
"""
import json
import logging
import secrets
import time
import threading
import uuid

from odoo import http, registry, SUPERUSER_ID
from odoo.api import Environment
from odoo.http import request

from . import mcp_backend

_logger = logging.getLogger(__name__)

# Sentinel: when _dispatch_jsonrpc returns (resp, MCP_REQUEST_ENV_RESTORE), caller must restore request.env.
# Second element is the previous request.env, or MCP_REQUEST_ENV_RESTORE_NONE meaning "request.env was not set".
MCP_REQUEST_ENV_RESTORE_NONE = object()

MCP_API_KEY_PARAM = "rag_odoo_mcp_server.api_key"
MCP_API_KEY_USER_PARAM = "rag_odoo_mcp_server.api_key_user"
MCP_API_KEY_ADMIN_PARAM = "rag_odoo_mcp_server.api_key_admin"
MCP_REQUIRE_API_KEY_PARAM = "rag_odoo_mcp_server.require_api_key"
MCP_AUTH_METHOD_PARAM = "rag_odoo_mcp_server.auth_method"
MCP_ODOO_USER_LOGIN_PARAM = "rag_odoo_mcp_server.odoo_user_login"
MCP_ODOO_USER_PASSWORD_PARAM = "rag_odoo_mcp_server.odoo_user_password"
MCP_ODOO_USER_ALLOW_WRITE_PARAM = "rag_odoo_mcp_server.odoo_user_allow_write"
MCP_DEFAULT_COMPANY_PARAM = "rag_odoo_mcp_server.default_company_id"
MCP_CLIENT_DESCRIPTION_PARAM = "rag_odoo_mcp_server.mcp_client_description"
MCP_DASHBOARD_ONLY_PARAM = "rag_odoo_mcp_server.dashboard_only"

# The only tools the connected LLM may use when "Generate dashboard only" is on.
MCP_DASHBOARD_ONLY_TOOLS = frozenset({
    "dashboard_list", "dashboard_get", "dashboard_get_schema_help",
    "dashboard_create", "dashboard_update",
    "dashboard_add_widget", "dashboard_remove_widget", "dashboard_delete",
})


# Header and Bearer token can carry database name so you don't need ?db= or odoo.conf.
# Bearer format: "Bearer <db>:<api_key>" or "Bearer <api_key>". Header: X-Odoo-Database: <db>
MCP_DB_HEADER = "X-Odoo-Database"


def _get_db_from_bearer_token():
    """If Authorization is Bearer db:key, return (db, key); else return (None, token_or_none)."""
    auth = (request.httprequest.headers.get("Authorization") or "").strip()
    if not auth.startswith("Bearer "):
        return None, None
    token = auth[7:].strip()
    if ":" in token:
        db, key = token.split(":", 1)
        db, key = db.strip(), key.strip()
        return (db or None), (key or None)
    return None, (token or None)


# Path segments directly under /mcp that are real routes, never database names.
_MCP_RESERVED_PATH_SEGMENTS = frozenset({"sse", "messages", "health", "oauth", "ping"})


def _parse_db_segment_from_path(path):
    """Pure parse of the db-name segment embedded in a *path-based* MCP URL.

    Recognises (with an optional leading ``/odoo``):
      - ``/mcp/<db>`` and ``/mcp/<db>/...``           (streamable + oauth sub-routes)
      - ``/mcp/<db>/.well-known/...``                 (RFC 8414 path-suffix form)
      - ``/.well-known/oauth-*/mcp/<db>``             (RFC 9728 / 8414 path-insert form)

    Returns the raw segment (UNvalidated) or None. Reserved sub-routes such as
    ``/mcp/sse`` or ``/mcp/oauth/...`` are never treated as a database.
    """
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "odoo":
        parts = parts[1:]
    if not parts:
        return None
    # /.well-known/oauth-protected-resource/mcp/<db>  (and oauth-authorization-server)
    if parts[0] == ".well-known" and len(parts) >= 4 and parts[2] == "mcp":
        return parts[3]
    # /mcp/<db>[/...]
    if parts[0] == "mcp" and len(parts) >= 2:
        seg = parts[1]
        if seg in _MCP_RESERVED_PATH_SEGMENTS:
            return None
        return seg
    return None


def _mcp_db_from_path(path):
    """Return the db from a path-based MCP URL, validated against the served db list.

    Validation matters on a multi-database server with no dbfilter: db_filter does
    not restrict anything there, so we confirm the segment is a real database before
    trusting it (otherwise ``/mcp/typo`` would look like a database).
    """
    cand = _parse_db_segment_from_path(path)
    if not cand:
        return None
    try:
        served = http.db_list(force=True)
    except Exception:
        served = []
    return cand if cand in served else None


def _get_db_name():
    """Database name from query, header X-Odoo-Database, Bearer db:key, URL path, session, or env."""
    db = request.httprequest.args.get("db")
    if db:
        return db
    db = (request.httprequest.headers.get(MCP_DB_HEADER) or "").strip()
    if db:
        return db
    db, _ = _get_db_from_bearer_token()
    if db:
        return db
    # Path-based OAuth/streamable: the database rides inside the URL path
    # (/mcp/<db>, /.well-known/oauth-*/mcp/<db>) so it survives the whole discovery
    # chain on a shared hostname with many databases and no dbfilter.
    db = _mcp_db_from_path(request.httprequest.path or "")
    if db:
        return db
    if getattr(request, "session", None) and getattr(request.session, "db", None):
        return request.session.db
    env = getattr(request, "env", None)
    if env and getattr(env, "cr", None) and getattr(env.cr, "dbname", None):
        return request.env.cr.dbname
    return None


def _ensure_mcp_session_db():
    """Bind session to db from query, header, or Bearer token so dispatch uses the correct database."""
    db = _get_db_name()
    if db and hasattr(request, "session"):
        request.session.db = db


def _get_request_api_key_from_token():
    """Return API key from Bearer token (either 'key' or 'db:key' format)."""
    _, key = _get_db_from_bearer_token()
    return key


def _mcp_require_db():
    """Return None or a 400 JSON response if db is missing."""
    if _get_db_name() is not None:
        return None
    return request.make_response(
        json.dumps({
            "error": "Missing database",
            "message": "Pass the database by: ?db= name in URL, header X-Odoo-Database: name, or Bearer token db:api_key.",
        }),
        status=400,
        headers=[
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*"),
        ],
    )


def _get_require_api_key():
    """Return True if MCP should require an API key for this database."""
    db = _get_db_name()
    try:
        if db:
            reg = registry(db)
            with reg.cursor() as cr:
                env = Environment(cr, SUPERUSER_ID, {})
                val = env["ir.config_parameter"].get_param(MCP_REQUIRE_API_KEY_PARAM)
                return _parse_require_api_key(val)
        # No db in request: read from current env (e.g. single-DB or env already set)
        val = request.env["ir.config_parameter"].sudo().get_param(MCP_REQUIRE_API_KEY_PARAM)
        return _parse_require_api_key(val)
    except Exception as e:
        _logger.warning("MCP require_api_key read failed (fail secure): %s", e)
        return True


def _parse_require_api_key(val):
    """Parse require_api_key from ir.config_parameter (string or bool)."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = (str(val).strip()).lower()
    return s in ("true", "1", "yes")


def _get_configured_api_keys():
    """Return (user_key, admin_key, legacy_key) for the request's database. Any can be None if not set.
    legacy_key is the old single API key (rag_odoo_mcp_server.api_key); accepted for backward compatibility as admin.
    """
    db = _get_db_name()
    try:
        if db:
            reg = registry(db)
            with reg.cursor() as cr:
                env = Environment(cr, SUPERUSER_ID, {})
                user_key = (env["ir.config_parameter"].get_param(MCP_API_KEY_USER_PARAM) or "").strip() or None
                admin_key = (env["ir.config_parameter"].get_param(MCP_API_KEY_ADMIN_PARAM) or "").strip() or None
                legacy_key = (env["ir.config_parameter"].get_param(MCP_API_KEY_PARAM) or "").strip() or None
                return user_key, admin_key, legacy_key
        user_key = (request.env["ir.config_parameter"].sudo().get_param(MCP_API_KEY_USER_PARAM) or "").strip() or None
        admin_key = (request.env["ir.config_parameter"].sudo().get_param(MCP_API_KEY_ADMIN_PARAM) or "").strip() or None
        legacy_key = (request.env["ir.config_parameter"].sudo().get_param(MCP_API_KEY_PARAM) or "").strip() or None
        return user_key, admin_key, legacy_key
    except Exception as e:
        _logger.debug("Could not read MCP API keys: %s", e)
        return None, None, None


def _get_request_api_key():
    """Extract API key: Bearer (supports db:key format), X-API-Key header, or api_key query param."""
    key = _get_request_api_key_from_token()
    if key:
        return key
    key = (request.httprequest.headers.get("X-API-Key") or "").strip()
    if key:
        return key
    key = (request.httprequest.args.get("api_key") or "").strip()
    return key or None


def _mcp_api_key_required():
    """If "require API key" is on, check the request has a valid User or Admin token.
    Set request.mcp_allow_write = True only when Admin token is used; else False.
    Return None or a 403 response.
    We use 403 (not 401) so Odoo/proxies do not redirect to the login page (which returns HTML and
    breaks MCP clients that expect JSON/SSE).
    """
    request.mcp_allow_write = False
    if not _get_require_api_key():
        return None
    user_key, admin_key, legacy_key = _get_configured_api_keys()
    if not user_key and not admin_key and not legacy_key:
        return request.make_response(
            json.dumps({
                "error": "Forbidden",
                "message": "API key required but no token configured. Generate a User or Admin token in Settings → RAG Odoo MCP Server.",
            }),
            status=403,
            headers=[
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store, no-cache"),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
    provided = _get_request_api_key()
    if not provided:
        return request.make_response(
            json.dumps({"error": "Forbidden", "message": "Invalid or missing API key"}),
            status=403,
            headers=[
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store, no-cache"),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
    if admin_key and secrets.compare_digest(admin_key, provided):
        request.mcp_allow_write = True
        return None
    if user_key and secrets.compare_digest(user_key, provided):
        request.mcp_allow_write = False
        return None
    # Backward compatibility: accept legacy single API key (treated as admin)
    if legacy_key and secrets.compare_digest(legacy_key, provided):
        request.mcp_allow_write = True
        return None
    return request.make_response(
        json.dumps({"error": "Forbidden", "message": "Invalid or missing API key"}),
        status=403,
        headers=[
            ("Content-Type", "application/json"),
            ("Cache-Control", "no-store, no-cache"),
            ("Access-Control-Allow-Origin", "*"),
        ],
    )

def _get_auth_method(db=None):
    """Return 'token' (default), 'odoo_user', or 'user_api_key' from ir.config_parameter."""
    try:
        if db is None:
            db = _get_db_name()
        if db:
            reg = registry(db)
            with reg.cursor() as cr:
                env = Environment(cr, SUPERUSER_ID, {})
                val = (env["ir.config_parameter"].get_param(MCP_AUTH_METHOD_PARAM) or "").strip()
                return val or "token"
        val = (request.env["ir.config_parameter"].sudo().get_param(MCP_AUTH_METHOD_PARAM) or "").strip()
        return val or "token"
    except Exception as e:
        _logger.warning("MCP auth_method read failed: %s", e)
        return "token"


def _get_request_odoo_user_credentials():
    """Pull (login, password) that the client sent with the MCP request.
    Accepts:
      - HTTP Basic Auth (Authorization: Basic base64(login:password))
      - Headers X-Odoo-Login / X-Odoo-Password
      - Query params odoo_login / odoo_password
    Returns (login, password) with either/both possibly empty.
    """
    import base64
    auth = (request.httprequest.headers.get("Authorization") or "").strip()
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:].strip()).decode("utf-8", errors="replace")
            if ":" in decoded:
                login, password = decoded.split(":", 1)
                return login.strip(), password
        except Exception as e:
            _logger.debug("MCP basic-auth decode failed: %s", e)
    login = (request.httprequest.headers.get("X-Odoo-Login") or "").strip()
    password = request.httprequest.headers.get("X-Odoo-Password") or ""
    if login or password:
        return login, password
    login = (request.httprequest.args.get("odoo_login") or "").strip()
    password = request.httprequest.args.get("odoo_password") or ""
    return login, password


def _authenticate_odoo_user(db):
    """Authenticate against the configured Odoo user credentials.
    Returns (uid, allow_write) on success, or a 403 Response on failure.
    When credentials are provided on the request (Basic auth / headers / query), those are used;
    otherwise the configured credentials from ir.config_parameter are used. In both cases the
    'allow write' flag comes from ir.config_parameter (server-side policy).
    """
    request.mcp_allow_write = False
    if not db:
        return request.make_response(
            json.dumps({"error": "Missing database"}),
            status=400,
            headers=[("Content-Type", "application/json")],
        )
    try:
        reg = registry(db)
        with reg.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            stored_login = (env["ir.config_parameter"].get_param(MCP_ODOO_USER_LOGIN_PARAM) or "").strip()
            stored_password = env["ir.config_parameter"].get_param(MCP_ODOO_USER_PASSWORD_PARAM) or ""
            allow_write_param = env["ir.config_parameter"].get_param(MCP_ODOO_USER_ALLOW_WRITE_PARAM)
            allow_write = str(allow_write_param or "").strip().lower() in ("true", "1", "yes")
    except Exception as e:
        _logger.exception("MCP odoo_user auth: failed to read config params: %s", e)
        return request.make_response(
            json.dumps({"error": "Server error", "message": "Could not read MCP config."}),
            status=500,
            headers=[("Content-Type", "application/json")],
        )

    req_login, req_password = _get_request_odoo_user_credentials()
    login = req_login or stored_login
    password = req_password or stored_password

    if not login or not password:
        return request.make_response(
            json.dumps({
                "error": "Forbidden",
                "message": "Odoo User authentication is enabled but no credentials are configured or provided. "
                           "Configure them in Settings → RAG Odoo MCP Server, or send HTTP Basic auth.",
            }),
            status=403,
            headers=[
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store, no-cache"),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )

    try:
        # Odoo 17: _login is a classmethod taking positional (db, login, password, user_agent_env)
        # and returns user.id directly. Call on registry (no env) since this route is auth='none'
        # and request.env may not be populated for the target db.
        uid = reg["res.users"]._login(db, login, password, {"interactive": False})
    except Exception as e:
        _logger.warning("MCP odoo_user authentication failed for login=%r: %s", login, e)
        return request.make_response(
            json.dumps({"error": "Forbidden", "message": "Invalid Odoo user credentials."}),
            status=403,
            headers=[
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store, no-cache"),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
    if isinstance(uid, dict):
        uid = uid.get("uid")
    if not uid:
        return request.make_response(
            json.dumps({"error": "Forbidden", "message": "Invalid Odoo user credentials."}),
            status=403,
            headers=[
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store, no-cache"),
                ("Access-Control-Allow-Origin", "*"),
            ],
        )
    request.mcp_allow_write = bool(allow_write)
    _logger.info(
        "MCP odoo_user auth OK: db=%s uid=%s allow_write=%s",
        db, uid, request.mcp_allow_write,
    )
    return uid, bool(allow_write)


def _authenticate_user_api_key(db):
    """Authenticate using a native per-user Odoo API key.

    The connecting client sends a standard Odoo API key (the kind any user can
    create in Preferences → Account Security → New API Key). We resolve it to a
    user via Odoo's own ``res.users.apikeys._check_credentials`` and run all MCP
    tools as that user, so the LLM has exactly that user's access rights — no
    more, no less.

    Returns (uid, allow_write) on success, or an HTTP error response on failure.
    Write tools are allowed (allow_write=True): the user's own ORM access rights
    are the real boundary, and Odoo raises AccessError on anything they can't do.
    """
    request.mcp_allow_write = False
    if not db:
        return request.make_response(
            json.dumps({"error": "Missing database"}),
            status=400,
            headers=[("Content-Type", "application/json")],
        )
    key = _get_request_api_key()
    if not key:
        return request.make_response(
            json.dumps({
                "error": "Unauthorized",
                "message": "Per-User API Key authentication is enabled, but no API key was provided. "
                           "Send your Odoo API key as 'Authorization: Bearer <db>:<key>' (or a plain "
                           "'Bearer <key>'), or in the 'X-API-Key' header, or '?api_key=' query param. "
                           "Create a key in Odoo → Preferences → Account Security → New API Key.",
            }),
            status=401,
            headers=[("Content-Type", "application/json"),
                     ("WWW-Authenticate", "Bearer"),
                     ("Cache-Control", "no-store, no-cache"),
                     ("Access-Control-Allow-Origin", "*")],
        )
    try:
        reg = registry(db)
        with reg.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            # Native Odoo check: matches global-scope keys (scope NULL, what the
            # Account Security UI creates) as well as 'rpc'-scope keys, and only
            # active users.
            uid = env["res.users.apikeys"].sudo()._check_credentials(scope="rpc", key=key)
    except Exception as e:
        _logger.exception("MCP per-user API key authentication error")
        return request.make_response(
            json.dumps({"error": "Internal error", "message": "Authentication error: %s" % e}),
            status=500,
            headers=[("Content-Type", "application/json"), ("Access-Control-Allow-Origin", "*")],
        )
    if not uid:
        return request.make_response(
            json.dumps({
                "error": "Unauthorized",
                "message": "Invalid, expired, or revoked API key. Create a new key in "
                           "Odoo → Preferences → Account Security → New API Key.",
            }),
            status=401,
            headers=[("Content-Type", "application/json"),
                     ("WWW-Authenticate", "Bearer"),
                     ("Cache-Control", "no-store, no-cache"),
                     ("Access-Control-Allow-Origin", "*")],
        )
    request.mcp_allow_write = True
    _logger.info("MCP user_api_key auth OK: db=%s uid=%s", db, uid)
    return uid, True


# Sessions and queued response messages live in the database (mcp_session,
# mcp_message). Multi-worker deployments (Odoo SH, Odoo with --workers > 0
# behind nginx, etc.) cannot share Python in-memory state across worker
# processes: the SSE GET and the matching POST may land on different workers,
# so the POST worker would never find a session_id created in another worker
# and would respond "Unknown or expired session". Storing both in Postgres
# fixes this without any infra change.
_tables_ensured = set()
_tables_ensured_lock = threading.Lock()

MCP_PROTOCOL_VERSION = "2025-11-25"
MCP_SESSION_STALE_SECONDS = 3600
MCP_SSE_POLL_SECONDS = 0.25
MCP_SSE_KEEPALIVE_SECONDS = 25
MCP_SSE_TOUCH_SECONDS = 30


def _get_allow_write(cr):
    """Return True if the current request is authorized for write tools (Admin token was used)."""
    return getattr(request, "mcp_allow_write", False)


def _ensure_mcp_tables(db):
    """Create mcp_session / mcp_message tables on first use (idempotent, per-process cached)."""
    with _tables_ensured_lock:
        if db in _tables_ensured:
            return
    try:
        reg = registry(db)
        with reg.cursor() as cr:
            cr.execute("""
                CREATE TABLE IF NOT EXISTS mcp_session (
                    session_id varchar PRIMARY KEY,
                    db_name varchar NOT NULL,
                    created_at timestamp NOT NULL DEFAULT (now() at time zone 'UTC'),
                    last_seen_at timestamp NOT NULL DEFAULT (now() at time zone 'UTC')
                );
                CREATE TABLE IF NOT EXISTS mcp_message (
                    id bigserial PRIMARY KEY,
                    session_id varchar NOT NULL,
                    payload text NOT NULL,
                    created_at timestamp NOT NULL DEFAULT (now() at time zone 'UTC')
                );
                CREATE INDEX IF NOT EXISTS mcp_message_session_idx
                    ON mcp_message(session_id, id);
                CREATE INDEX IF NOT EXISTS mcp_session_last_seen_idx
                    ON mcp_session(last_seen_at);
            """)
        with _tables_ensured_lock:
            _tables_ensured.add(db)
    except Exception:
        _logger.exception("MCP failed to ensure session tables for db=%s", db)
        raise


def _create_session(db):
    """Insert a new session row in the DB and return its id. Visible to all workers after commit."""
    _ensure_mcp_tables(db)
    session_id = str(uuid.uuid4())
    reg = registry(db)
    with reg.cursor() as cr:
        cr.execute(
            "INSERT INTO mcp_session(session_id, db_name) VALUES (%s, %s)",
            (session_id, db),
        )
        # Opportunistic cleanup of stale sessions left behind by crashed workers.
        cr.execute(
            "DELETE FROM mcp_message WHERE session_id IN ("
            "  SELECT session_id FROM mcp_session"
            "  WHERE last_seen_at < (now() at time zone 'UTC') - (%s || ' seconds')::interval"
            ")",
            (MCP_SESSION_STALE_SECONDS,),
        )
        cr.execute(
            "DELETE FROM mcp_session"
            " WHERE last_seen_at < (now() at time zone 'UTC') - (%s || ' seconds')::interval",
            (MCP_SESSION_STALE_SECONDS,),
        )
    return session_id


def _drop_session(db, session_id):
    """Remove session and any pending messages."""
    if not db or not session_id:
        return
    try:
        reg = registry(db)
        with reg.cursor() as cr:
            cr.execute("DELETE FROM mcp_message WHERE session_id = %s", (session_id,))
            cr.execute("DELETE FROM mcp_session WHERE session_id = %s", (session_id,))
    except Exception:
        _logger.exception("MCP failed to drop session %s", session_id)


def _session_exists_and_touch(db, session_id):
    """Verify the session is known to the DB; refresh its last_seen_at. Returns True/False."""
    if not db or not session_id:
        return False
    try:
        _ensure_mcp_tables(db)
        reg = registry(db)
        with reg.cursor() as cr:
            cr.execute(
                "UPDATE mcp_session SET last_seen_at = (now() at time zone 'UTC')"
                " WHERE session_id = %s RETURNING 1",
                (session_id,),
            )
            return cr.fetchone() is not None
    except Exception:
        _logger.exception("MCP failed to check session %s", session_id)
        return False


def _touch_session(db, session_id):
    """Refresh last_seen_at so the cleanup query won't expire this session."""
    try:
        reg = registry(db)
        with reg.cursor() as cr:
            cr.execute(
                "UPDATE mcp_session SET last_seen_at = (now() at time zone 'UTC')"
                " WHERE session_id = %s",
                (session_id,),
            )
    except Exception:
        _logger.exception("MCP failed to touch session %s", session_id)


def _push_message(db, session_id, payload):
    """Append a JSON-RPC response payload (string) to the session's queue."""
    if not isinstance(payload, str):
        payload = json.dumps(payload)
    reg = registry(db)
    with reg.cursor() as cr:
        cr.execute(
            "INSERT INTO mcp_message(session_id, payload) VALUES (%s, %s)",
            (session_id, payload),
        )


def _pop_messages(db, session_id, limit=100):
    """Atomically take pending payloads for this session (FIFO)."""
    reg = registry(db)
    with reg.cursor() as cr:
        cr.execute(
            "DELETE FROM mcp_message WHERE id IN ("
            "  SELECT id FROM mcp_message WHERE session_id = %s ORDER BY id LIMIT %s"
            ") RETURNING payload",
            (session_id, limit),
        )
        return [row[0] for row in cr.fetchall()]


def _is_dashboard_only(env):
    """Return True if the 'Generate dashboard only' setting is enabled."""
    try:
        val = env["ir.config_parameter"].sudo().get_param(MCP_DASHBOARD_ONLY_PARAM)
    except Exception as e:
        _logger.warning("MCP dashboard_only read failed (defaulting to off): %s", e)
        return False
    if val is None:
        return False
    return str(val).strip().lower() in ("true", "1", "yes")


def _get_default_company_id(env):
    """Read the configured 'Default MCP Company' id from ir.config_parameter, or None."""
    try:
        val = env["ir.config_parameter"].sudo().get_param(MCP_DEFAULT_COMPANY_PARAM)
    except Exception:
        return None
    if val:
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return None


def _apply_default_company(env):
    """Return env bound to the configured default company, or env unchanged.

    Applying the company at the environment level (rather than injecting a company_id
    kwarg) is universal and safe: it only changes ORM context, so every tool honours it
    and no tool receives an unexpected argument.
    """
    company_id = _get_default_company_id(env)
    if not company_id:
        return env
    try:
        company = env["res.company"].sudo().browse(company_id)
        if company.exists():
            return env.with_company(company_id)
    except Exception as e:
        _logger.warning("MCP default company apply failed (id=%s): %s", company_id, e)
    return env


def _dispatch_jsonrpc(body, cr, uid=None):
    """Handle a single JSON-RPC request. Returns response dict or None for notifications.
    When uid is provided (Odoo User authentication), tool calls run under that uid's ACLs;
    otherwise they run as SUPERUSER_ID.
    """
    try:
        data = json.loads(body) if isinstance(body, (str, bytes)) else body
    except Exception as e:
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error: %s" % e}}
    req_id = data.get("id")
    method = data.get("method")
    params = data.get("params") or {}

    if method == "initialize":
        env = Environment(cr, uid or SUPERUSER_ID, {})
        server_info = {"name": "rag-odoo-mcp-server", "version": "0.1"}
        description = (env["ir.config_parameter"].sudo().get_param(MCP_CLIENT_DESCRIPTION_PARAM) or "").strip()
        if description:
            server_info["description"] = description
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": server_info,
            },
        }

    if method == "tools/list":
        tools = mcp_backend.TOOL_DEFINITIONS
        env_check = Environment(cr, uid or SUPERUSER_ID, {})
        # "Generate dashboard only" — restrict to dashboard tools regardless of token type.
        if _is_dashboard_only(env_check):
            tools = [t for t in tools if t["name"] in MCP_DASHBOARD_ONLY_TOOLS]
        # CRM Manager feature flag — hide lead-gen / CRM / mailing tools when off.
        if not mcp_backend.is_crm_manager_enabled(env_check):
            tools = [t for t in tools if t["name"] not in mcp_backend.MCP_CRM_MANAGER_TOOLS]
        # Access Manager feature flag — hide access-rules tools when off.
        if not mcp_backend.is_access_manager_enabled(env_check):
            tools = [t for t in tools if t["name"] not in mcp_backend.MCP_ACCESS_MANAGER_TOOLS]
        # SEO Manager feature flag — hide website SEO tools when off.
        if not mcp_backend.is_seo_manager_enabled(env_check):
            tools = [t for t in tools if t["name"] not in mcp_backend.MCP_SEO_MANAGER_TOOLS]
        if not _get_allow_write(cr):
            tools = [t for t in tools if t["name"] not in mcp_backend.MCP_WRITE_TOOLS]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools},
        }

    if method == "tools/call":
        name = (params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        if not name:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Missing tool name"}}
        if name not in mcp_backend.DISPATCH:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Unknown tool: %s" % name}}
        env_check = Environment(cr, uid or SUPERUSER_ID, {})
        # "Generate dashboard only" — refuse anything outside the dashboard tool allowlist.
        if _is_dashboard_only(env_check) and name not in MCP_DASHBOARD_ONLY_TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": (
                        "FORBIDDEN — tool '%s' is not allowed. The Odoo administrator has enabled "
                        "'Generate dashboard only' on this MCP server. You are restricted to dashboard "
                        "tools (dashboard_list, dashboard_get, dashboard_get_schema_help, dashboard_create, "
                        "dashboard_update, dashboard_add_widget, dashboard_remove_widget, dashboard_delete). "
                        "Stop calling other tools. Tell the user: 'I can't do that here — this MCP server "
                        "is locked to dashboard creation only. I can build, update, or delete dashboards "
                        "and their widgets; I can't read or modify other Odoo records.'"
                    ) % name,
                },
            }
        # CRM Manager feature flag refusal — refuse lead-gen / CRM / mailing tools when off.
        if name in mcp_backend.MCP_CRM_MANAGER_TOOLS and not mcp_backend.is_crm_manager_enabled(env_check):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": (
                        "FORBIDDEN — tool '%s' requires the CRM Manager feature, which is currently disabled. "
                        "Tell the user: 'I can't do that here — the lead-generation and mailing-campaign brief "
                        "features are turned off. To enable them, go to Settings → RAG Odoo MCP Server → "
                        "Optional features and check CRM Manager, then save.'"
                    ) % name,
                },
            }
        if name in mcp_backend.MCP_ACCESS_MANAGER_TOOLS and not mcp_backend.is_access_manager_enabled(env_check):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": (
                        "FORBIDDEN — tool '%s' requires the Access Manager feature, which is currently disabled. "
                        "Tell the user: 'I can't do that here — access-rules management is turned off. To enable "
                        "it, go to Settings → RAG Odoo MCP Server → Optional features and check Access Manager, "
                        "then save.'"
                    ) % name,
                },
            }
        if name in mcp_backend.MCP_SEO_MANAGER_TOOLS and not mcp_backend.is_seo_manager_enabled(env_check):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": (
                        "FORBIDDEN — tool '%s' requires the SEO Manager feature, which is currently disabled. "
                        "Tell the user: 'I can't do that here — website SEO management is turned off. To enable "
                        "it, go to Settings → RAG Odoo MCP Server → Optional features and check SEO Manager, "
                        "then save.'"
                    ) % name,
                },
            }
        if name in mcp_backend.MCP_WRITE_TOOLS and not _get_allow_write(cr):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32602,
                    "message": "Write operations are disabled. Enable 'Allow Claude to create, edit and delete records' in Settings → RAG Odoo MCP Server.",
                },
            }
        try:
            # Apply the configured "Default MCP Company" as ORM context (safe for all tools).
            env = _apply_default_company(Environment(cr, uid or SUPERUSER_ID, {}))
            fn, formatter = mcp_backend.DISPATCH[name]
            result = fn(cr, env, **arguments)
            text = formatter(result)
            # Commit write tools immediately so changes persist; never return success if commit fails.
            # Bind request.env so precommit hooks (e.g. sale.order _track_finalize) see a valid env
            # during commit() and when the cursor context manager exits (it also calls commit()).
            # Return (response, old_request_env) so caller can restore request.env after the with block.
            if name in mcp_backend.MCP_WRITE_TOOLS:
                try:
                    old_request_env = getattr(request, "env", None)
                    request.env = env
                    try:
                        cr.commit()
                    except Exception as commit_err:
                        if old_request_env is not None:
                            request.env = old_request_env
                        elif hasattr(request, "env"):
                            del request.env
                        _logger.exception("MCP commit failed after %s", name)
                        return (
                            {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32603,
                                    "message": "Tool succeeded but commit failed; changes were not saved: %s" % commit_err,
                                },
                            },
                            None,
                        )
                    # Leave request.env set until cursor __exit__ runs; return old env so caller restores.
                    return (
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {"content": [{"type": "text", "text": text}]},
                        },
                        old_request_env if old_request_env is not None else MCP_REQUEST_ENV_RESTORE_NONE,
                    )
                except Exception as commit_err:
                    if old_request_env is not None:
                        request.env = old_request_env
                    elif hasattr(request, "env"):
                        del request.env
                    _logger.exception("MCP commit failed after %s", name)
                    return (
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32603,
                                "message": "Tool succeeded but commit failed; changes were not saved: %s" % commit_err,
                            },
                        },
                        None,
                    )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        except Exception as e:
            msg = str(e)
            # Help LLM recover from selection field errors (e.g. product.template.type)
            if "Wrong value for" in msg and "type" in msg.lower():
                msg = "%s Use odoo_search_read on that model with fields=[\"type\"] to see valid type values (e.g. consu, service)." % msg
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": msg},
            }

    if method == "notifications/initialized":
        return None

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found: %s" % method}}


# Sentinel used by the Streamable HTTP handler to restore request.env after dispatch,
# distinguishing "request.env was never set" from "request.env was set to something".
_MCP_ENV_UNSET = object()


def _streamable_cors_headers(extra=None):
    """CORS + method/allow headers shared by every /mcp Streamable HTTP response.

    We expose Mcp-Session-Id / MCP-Protocol-Version so browser-based MCP clients can
    read them, and accept the auth + db routing headers on the request side.
    """
    headers = [
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS"),
        ("Access-Control-Allow-Headers",
         "Content-Type, Authorization, X-API-Key, X-Odoo-Database, X-Odoo-Company, "
         "Mcp-Session-Id, MCP-Protocol-Version"),
        ("Access-Control-Expose-Headers", "Mcp-Session-Id, MCP-Protocol-Version"),
    ]
    if extra:
        headers.extend(extra)
    return headers


def _get_raw_bearer_token():
    """Return the raw token from 'Authorization: Bearer <token>', else None."""
    auth = (request.httprequest.headers.get("Authorization") or "").strip()
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    return None


def _validate_oauth_bearer(db):
    """If the request carries a valid OAuth 2.1 access token, return its user id, else None.

    OAuth tokens are opaque base64url strings (no colon); a 'Bearer db:key' value is the
    legacy API-key format, not an OAuth token, so we skip it and let the API-key path handle it.
    """
    token = _get_raw_bearer_token()
    if not token or not db or ":" in token:
        return None
    try:
        reg = registry(db)
        with reg.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            return env["rag_odoo_mcp_server.oauth_token"].validate_access_token(token)
    except Exception:
        _logger.exception("MCP OAuth access-token validation failed")
        return None


def _request_has_any_credential():
    """True if the request supplied any auth material (Authorization, X-API-Key, or ?api_key)."""
    if (request.httprequest.headers.get("Authorization") or "").strip():
        return True
    if (request.httprequest.headers.get("X-API-Key") or "").strip():
        return True
    if (request.httprequest.args.get("api_key") or "").strip():
        return True
    return False


def _oauth_challenge_response():
    """401 with a WWW-Authenticate resource-metadata hint so a native MCP client starts OAuth.

    For a path-based connector (``/mcp/<db>``) the resource-metadata URL keeps the db in
    its path (``/.well-known/oauth-protected-resource/mcp/<db>``) so the whole discovery
    chain resolves the database without ``?db=`` — the fix for shared multi-db hosts.
    """
    from .mcp_oauth import _base_url
    base = _base_url()
    path_db = _mcp_db_from_path(request.httprequest.path or "")
    if path_db:
        metadata_url = "%s/.well-known/oauth-protected-resource/mcp/%s" % (base, path_db)
    else:
        metadata_url = "%s/.well-known/oauth-protected-resource" % base
    return request.make_response(
        json.dumps({"error": "unauthorized",
                    "error_description": "Authentication required. Use OAuth or an API key."}),
        status=401,
        headers=[
            ("Content-Type", "application/json"),
            ("WWW-Authenticate", 'Bearer resource_metadata="%s"' % metadata_url),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Expose-Headers", "WWW-Authenticate"),
        ],
    )


class McpController(http.Controller):

    # auth='none' so routes match even when no database is set in session (multi-db without db in odoo.conf).
    # Register both /mcp/... and /odoo/mcp/... so it works with or without /odoo mount.
    @http.route(["/mcp/sse", "/odoo/mcp/sse"], type="http", auth="none", csrf=False, save_session=False, methods=["GET"])
    def mcp_sse(self, **kw):
        """SSE endpoint. Connect here; receives session endpoint event, then message events.
        Authentication is enforced on /mcp/messages/ (the POST side) rather than on the initial
        GET — some MCP clients (mcp-remote) can't forward auth headers on the SSE GET.
        """
        _ensure_mcp_session_db()
        missing_db = _mcp_require_db()
        if missing_db:
            return missing_db
        # Resolve the actual database name (query, header, bearer token, or session) so the
        # session row goes into the right Postgres DB. If we just passed the query-string db
        # to the messages URL, single-DB deployments would lose track of it after a restart.
        db = _get_db_name()
        session_id = _create_session(db)
        path = (request.httprequest.path or "").rstrip("/")
        # When hit at /odoo/mcp/sse, client must POST to /odoo/mcp/messages/
        prefix = "/odoo" if path.startswith("/odoo/") else ""
        messages_uri = "%s/mcp/messages/?session_id=%s" % (prefix, session_id)
        url_db = request.httprequest.args.get("db")
        if url_db:
            messages_uri += "&db=%s" % url_db

        def stream():
            yield ("event: endpoint\ndata: %s\n\n" % messages_uri).encode("utf-8")
            now = time.monotonic()
            last_keepalive = now
            last_touch = now
            try:
                while True:
                    payloads = _pop_messages(db, session_id)
                    for payload in payloads:
                        yield ("event: message\ndata: %s\n\n" % payload).encode("utf-8")
                    now = time.monotonic()
                    if payloads:
                        last_keepalive = now
                    elif now - last_keepalive > MCP_SSE_KEEPALIVE_SECONDS:
                        yield b": keepalive\n\n"
                        last_keepalive = now
                    if now - last_touch > MCP_SSE_TOUCH_SECONDS:
                        _touch_session(db, session_id)
                        last_touch = now
                    time.sleep(MCP_SSE_POLL_SECONDS)
            finally:
                _drop_session(db, session_id)

        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
        response = request.make_response(stream(), headers=list(headers.items()))
        response.headers["Content-Type"] = "text/event-stream"
        if hasattr(response, "content_type"):
            response.content_type = "text/event-stream"
        return response

    @http.route(["/mcp/messages/", "/odoo/mcp/messages/"], type="http", auth="none", csrf=False,
                methods=["POST", "OPTIONS"], save_session=False)
    def mcp_messages(self, **kw):
        """JSON-RPC POST endpoint. session_id from query param (matching official SDK)."""
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=[
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "POST, OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, mcp-session-id, Authorization, X-API-Key, X-Odoo-Database"),
            ])
        _ensure_mcp_session_db()
        missing_db = _mcp_require_db()
        if missing_db:
            return missing_db
        db = _get_db_name()
        auth_method = _get_auth_method(db)
        mcp_uid = None
        if auth_method == "oauth":
            # OAuth mode: accept a valid OAuth access token (a native client may still POST
            # here), otherwise challenge so it starts the login flow.
            oauth_uid = _validate_oauth_bearer(db)
            if oauth_uid is None:
                return _oauth_challenge_response()
            mcp_uid = oauth_uid
            request.mcp_allow_write = True
        elif auth_method == "odoo_user":
            auth_result = _authenticate_odoo_user(db)
            if not isinstance(auth_result, tuple):
                # Auth failed: got a Response back
                return auth_result
            mcp_uid, _allow_write = auth_result
            _logger.info(
                "MCP /messages auth=odoo_user uid=%s allow_write=%s db=%s",
                mcp_uid, getattr(request, "mcp_allow_write", False), db,
            )
        elif auth_method == "user_api_key":
            auth_result = _authenticate_user_api_key(db)
            if not isinstance(auth_result, tuple):
                # Auth failed: got a Response back
                return auth_result
            mcp_uid, _allow_write = auth_result
            _logger.info(
                "MCP /messages auth=user_api_key uid=%s allow_write=%s db=%s",
                mcp_uid, getattr(request, "mcp_allow_write", False), db,
            )
        else:
            unauth = _mcp_api_key_required()
            if unauth:
                return unauth
            _logger.info(
                "MCP /messages auth=token allow_write=%s db=%s",
                getattr(request, "mcp_allow_write", False), db,
            )
        session_id = (
            request.httprequest.args.get("session_id")
            or request.httprequest.args.get("sessionId")
            or request.httprequest.headers.get("mcp-session-id")
        )
        if not session_id:
            return request.make_response(
                json.dumps({"error": "Missing sessionId"}), status=400,
                headers=[("Content-Type", "application/json")],
            )
        if not db:
            return request.make_response(
                json.dumps({"error": "Missing database", "message": "Add ?db=<database_name> to the URL."}),
                status=400, headers=[("Content-Type", "application/json")],
            )
        if not _session_exists_and_touch(db, session_id):
            return request.make_response(
                json.dumps({"error": "Unknown or expired session"}), status=400,
                headers=[("Content-Type", "application/json")],
            )
        body = request.httprequest.get_data(as_text=True)
        request_env_to_restore = None
        resp = None
        try:
            reg = registry(db)
            with reg.cursor() as cr:
                out = _dispatch_jsonrpc(body, cr, uid=mcp_uid)
                if isinstance(out, tuple):
                    resp, request_env_to_restore = out
                else:
                    resp = out
        except Exception as e:
            _logger.exception("MCP dispatch error")
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        finally:
            if request_env_to_restore is MCP_REQUEST_ENV_RESTORE_NONE:
                if hasattr(request, "env"):
                    del request.env
            elif request_env_to_restore is not None:
                request.env = request_env_to_restore
        if resp is not None:
            try:
                _push_message(db, session_id, json.dumps(resp))
            except Exception:
                _logger.exception("MCP failed to enqueue response for session %s", session_id)
        return request.make_response("", status=202, headers=[
            ("Content-Type", "application/json"),
            ("Access-Control-Allow-Origin", "*"),
        ])

    @http.route(["/mcp", "/mcp/", "/odoo/mcp", "/odoo/mcp/",
                 "/mcp/<db>", "/odoo/mcp/<db>"], type="http", auth="none", csrf=False,
                methods=["POST", "GET", "DELETE", "OPTIONS"], save_session=False)
    def mcp_streamable(self, db=None, **kw):
        """MCP **Streamable HTTP** transport — a single endpoint, no SSE bridge.

        Modern MCP clients (Claude desktop/web "custom connector", Cursor, etc.) talk to
        ONE URL over plain HTTP and do not need mcp-remote. Each POST carries a JSON-RPC
        message; we authenticate it, dispatch it through the same backend the legacy
        /mcp/messages route uses, and return the JSON-RPC reply as application/json.

        Design notes:
          - Fully STATELESS. Every request is authenticated on its own (OAuth Bearer,
            per-user API key, token, or Odoo user). The URL by itself grants nothing.
          - Responses are plain application/json, so no reverse-proxy buffering concerns
            and no dependence on a long-lived streaming connection.
          - The legacy /mcp/sse + /mcp/messages routes are untouched, so existing
            mcp-remote users keep working.

        Connect from Claude: Settings -> Connectors -> Add custom connector ->
            https://<host>/mcp?db=<database>
        With OAuth (native connector) the user logs in with their Odoo account and no
        static header is needed; otherwise set Authorization: Bearer <api_key or db:key>.
        """
        method = request.httprequest.method
        if method == "OPTIONS":
            return request.make_response("", headers=_streamable_cors_headers())

        _ensure_mcp_session_db()
        missing_db = _mcp_require_db()
        if missing_db:
            return missing_db
        db = _get_db_name()

        # A standalone GET is the optional server->client notification stream. This
        # server is request/response only, so tell the client it isn't offered (405 is
        # explicitly allowed by the spec; compliant clients continue without it).
        if method == "GET":
            return request.make_response(
                json.dumps({
                    "error": "Method Not Allowed",
                    "message": "This MCP endpoint is request/response only; no server-initiated SSE stream.",
                }),
                status=405,
                headers=_streamable_cors_headers([
                    ("Content-Type", "application/json"),
                    ("Allow", "POST, DELETE, OPTIONS"),
                ]),
            )

        # Authenticate EVERY request (including initialize). Order of precedence:
        #   1) a valid OAuth 2.1 access token (native connector) -> run as that Odoo user;
        #   2) otherwise the configured API-key / Odoo-user auth (header, ?api_key, Bearer db:key);
        #   3) if NO credential was supplied at all, answer 401 with a resource-metadata hint
        #      so a native MCP client begins the OAuth login flow.
        mcp_uid = None  # None = SUPERUSER_ID (token mode default)
        oauth_uid = _validate_oauth_bearer(db)
        if oauth_uid is not None:
            mcp_uid = oauth_uid
            # The user's own ORM access rights are the real boundary (Odoo raises AccessError
            # on anything they can't do), so write tools are allowed under OAuth.
            request.mcp_allow_write = True
        else:
            auth_method = _get_auth_method(db)
            if auth_method == "oauth":
                # OAuth is the selected (and only) method: no valid token -> challenge so the
                # native client starts the login flow. Do not accept API keys here.
                return _oauth_challenge_response()
            if auth_method == "odoo_user":
                result = _authenticate_odoo_user(db)
            elif auth_method == "user_api_key":
                result = _authenticate_user_api_key(db)
            else:
                err = _mcp_api_key_required()
                result = err if err is not None else (None, getattr(request, "mcp_allow_write", False))
            if isinstance(result, tuple):
                mcp_uid, allow_write = result
                request.mcp_allow_write = allow_write
            elif not _request_has_any_credential():
                return _oauth_challenge_response()
            else:
                # A credential was supplied but rejected -> return the original error.
                return result

        if method == "DELETE":
            # Stateless — no session to tear down, but honour the verb cleanly.
            return request.make_response("", status=200, headers=_streamable_cors_headers())

        # POST — the JSON-RPC message (single object, or a batch array).
        body = request.httprequest.get_data(as_text=True)

        try:
            parsed = json.loads(body) if body else {}
        except Exception as e:
            return request.make_response(
                json.dumps({"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32700, "message": "Parse error: %s" % e}}),
                status=400,
                headers=_streamable_cors_headers([("Content-Type", "application/json")]),
            )

        # Restore request.env after dispatch. Write tools set request.env internally so
        # their commit/precommit hooks see a valid env; we always put it back to what it
        # was on entry (or remove it if it was never set).
        original_env = getattr(request, "env", _MCP_ENV_UNSET)
        payload = None
        is_empty = True
        try:
            reg = registry(db)
            with reg.cursor() as cr:
                if isinstance(parsed, list):
                    responses = []
                    for item in parsed:
                        out = _dispatch_jsonrpc(item, cr, uid=mcp_uid)
                        r = out[0] if isinstance(out, tuple) else out
                        if r is not None:
                            responses.append(r)
                    payload = responses
                    is_empty = not responses
                else:
                    out = _dispatch_jsonrpc(parsed, cr, uid=mcp_uid)
                    payload = out[0] if isinstance(out, tuple) else out
                    is_empty = payload is None
        except Exception as e:
            _logger.exception("MCP streamable dispatch error")
            return request.make_response(
                json.dumps({"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32603, "message": str(e)}}),
                status=500,
                headers=_streamable_cors_headers([("Content-Type", "application/json")]),
            )
        finally:
            if original_env is _MCP_ENV_UNSET:
                if hasattr(request, "env"):
                    del request.env
            else:
                request.env = original_env

        # Notifications / responses carry no reply → 202 Accepted, empty body (per spec).
        if is_empty:
            return request.make_response("", status=202, headers=_streamable_cors_headers())

        return request.make_response(
            json.dumps(payload),
            status=200,
            headers=_streamable_cors_headers([
                ("Content-Type", "application/json"),
                ("Cache-Control", "no-store"),
            ]),
        )

    @http.route(["/mcp/health", "/odoo/mcp/health"], type="http", auth="none", csrf=False, methods=["GET"])
    def mcp_health(self, **kw):
        """Health check."""
        _ensure_mcp_session_db()
        missing_db = _mcp_require_db()
        if missing_db:
            return missing_db
        db = _get_db_name()
        auth_method = _get_auth_method(db)
        if auth_method == "oauth":
            oauth_uid = _validate_oauth_bearer(db)
            if oauth_uid is None:
                return _oauth_challenge_response()
        elif auth_method == "odoo_user":
            auth_result = _authenticate_odoo_user(db)
            if not isinstance(auth_result, tuple):
                return auth_result
        elif auth_method == "user_api_key":
            auth_result = _authenticate_user_api_key(db)
            if not isinstance(auth_result, tuple):
                return auth_result
        else:
            unauth = _mcp_api_key_required()
            if unauth:
                return unauth
        return request.make_response(
            json.dumps({"status": "ok", "server": "rag-odoo-mcp-server"}),
            headers=[("Content-Type", "application/json"), ("Access-Control-Allow-Origin", "*")],
        )
