# -*- coding: utf-8 -*-
"""
Patch Odoo's request handling so session.db is set from ?db=, X-Odoo-Database header,
or Bearer db:key token BEFORE the Application chooses between _serve_db and _serve_nodb.
In Odoo 17, that choice is made in Application.__call__ using request.db, which is set
in Request._post_init() by _get_session_and_dbname(). So we must patch _get_session_and_dbname
to inject the db from query/header/token; otherwise requests to /mcp/sse?db=xxx get 404
because request.db is None and Odoo uses _serve_nodb() whose routing map has no MCP routes.
"""
import logging

_logger = logging.getLogger(__name__)

_APPLIED = False


def _mcp_db_from_request(request):
    """Extract database name from query, X-Odoo-Database header, or Bearer db:key."""
    if not getattr(request, "httprequest", None):
        return None
    db = request.httprequest.args.get("db")
    if db:
        return db
    db = (request.httprequest.headers.get("X-Odoo-Database") or "").strip()
    if db:
        return db
    auth = (request.httprequest.headers.get("Authorization") or "").strip()
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if ":" in token:
            return token.split(":", 1)[0].strip() or None
    return None


# Path segments directly under /mcp that are real routes, never database names.
_MCP_RESERVED_PATH_SEGMENTS = frozenset({"sse", "messages", "health", "oauth", "ping"})


def _mcp_db_from_path(httprequest):
    """Resolve the database from a *path-based* MCP URL, validated against served dbs.

    This is what makes OAuth work on a shared hostname with many databases and no
    dbfilter: the database rides inside the path (``/mcp/<db>`` and the discovery
    URLs ``/.well-known/oauth-*/mcp/<db>``), so we can bind ``session.db`` before
    routing even though there is no ``?db=`` and no monodb fallback.
    """
    if not httprequest:
        return None
    path = getattr(httprequest, "path", "") or ""
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "odoo":
        parts = parts[1:]
    cand = None
    # /.well-known/oauth-*/mcp/<db>
    if parts and parts[0] == ".well-known" and len(parts) >= 4 and parts[2] == "mcp":
        cand = parts[3]
    # /mcp/<db>[/...]
    elif parts and parts[0] == "mcp" and len(parts) >= 2:
        seg = parts[1]
        if seg not in _MCP_RESERVED_PATH_SEGMENTS:
            cand = seg
    if not cand:
        return None
    try:
        import odoo
        from odoo.http import db_filter
        if cand in db_filter(odoo.service.db.list_dbs(force=True)):
            return cand
    except Exception:
        pass
    return None


def _mcp_default_db():
    """Fallback database when a request names none.

    OAuth discovery endpoints (/.well-known/oauth-*) are fetched by the client with no
    ?db=, so on a multi-database server they would land on the no-db router (which only
    knows base/web routes) and 404. To make the native OAuth connector work, resolve to
    the single served database, or the server's configured db_name. Returns None when the
    choice is ambiguous (several databases and no configured default), preserving the
    normal multi-database database-selector behaviour.
    """
    try:
        import odoo
        from odoo.http import db_filter
        dbs = db_filter(odoo.service.db.list_dbs(force=True))
        if len(dbs) == 1:
            return dbs[0]
    except Exception:
        pass
    try:
        import odoo
        configured = (odoo.tools.config.get("db_name") or "").split(",")[0].strip()
        if configured:
            return configured
    except Exception:
        pass
    return None


def apply_patch():
    """Set session.db from URL/header/token inside _get_session_and_dbname so request.db
    is set before Application.__call__ branches to _serve_db vs _serve_nodb."""
    global _APPLIED
    if _APPLIED:
        return
    try:
        import odoo.http as http
        # Request is the class that has _get_session_and_dbname (Odoo 17)
        Request = getattr(http, "Request", None)
        if not Request or not hasattr(Request, "_get_session_and_dbname"):
            _logger.warning(
                "rag_odoo_mcp_server: Request._get_session_and_dbname not found, "
                "multi-db MCP may return 404. Use --db-filter=^yourdb$ or set db in session."
            )
            _APPLIED = True
            return

        _get_session_and_dbname_orig = Request._get_session_and_dbname
        if getattr(_get_session_and_dbname_orig, "_mcp_patched", False):
            _APPLIED = True
            return

        try:
            from odoo.http import db_filter
        except Exception:
            db_filter = None

        def _get_session_and_dbname_patched(self):
            session, dbname = _get_session_and_dbname_orig(self)
            # Inject db from query/header/token so that when Odoo has not set session.db
            # (e.g. first request with ?db=), we use it and the branch in __call__ uses _serve_db.
            db_from_request = _mcp_db_from_request(self)
            if db_from_request and session is not None:
                session.db = db_from_request
                dbname = db_from_request
            elif not dbname and session is not None:
                # No db named anywhere (e.g. OAuth /.well-known/* fetched without ?db=).
                # Try the path-based db first (/mcp/<db>, /.well-known/oauth-*/mcp/<db>) so
                # the discovery chain resolves on a shared multi-db host with no dbfilter;
                # then fall back to the single served / configured database so custom-module
                # routes resolve instead of 404-ing on the no-db router. Guard with
                # db_filter so we never bind a database this host isn't allowed to serve.
                candidate = _mcp_db_from_path(self.httprequest) or _mcp_default_db()
                if candidate:
                    host = self.httprequest.environ.get("HTTP_HOST", "")
                    if db_filter is None or db_filter([candidate], host=host):
                        session.db = candidate
                        dbname = candidate
            return session, dbname

        _get_session_and_dbname_patched._mcp_patched = True
        Request._get_session_and_dbname = _get_session_and_dbname_patched
        _APPLIED = True
        _logger.info("rag_odoo_mcp_server: patched _get_session_and_dbname for db from query/header/token")
    except Exception as e:
        _logger.warning("rag_odoo_mcp_server: could not patch _get_session_and_dbname: %s", e)
        _APPLIED = True
