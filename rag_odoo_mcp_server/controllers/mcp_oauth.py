# -*- coding: utf-8 -*-
"""
OAuth 2.1 Authorization Server for the MCP Streamable HTTP transport.

Implements just enough of the MCP Authorization spec for a native Claude
"custom connector" (and other MCP clients) to authenticate without mcp-remote
and without a static header:

  1. GET  /.well-known/oauth-protected-resource      — points clients at the AS
  2. GET  /.well-known/oauth-authorization-server     — advertises the endpoints below
  3. POST /mcp/oauth/register                         — Dynamic Client Registration (public + PKCE)
  4. GET/POST /mcp/oauth/authorize                    — Odoo login + consent -> authorization code
  5. POST /mcp/oauth/token                            — code -> access/refresh token, and refresh

The access token issued here is validated in mcp_controller's /mcp endpoint and
resolved to the Odoo user who logged in, so every tool runs with that user's rights.

Multi-database note: the well-known endpoints are fetched without ?db=. We resolve
the database from the request, then fall back to "the single database served on this
host" (and finally the server's configured db_name). The authorize/token/register
URLs advertised in the metadata carry ?db=<db> so the rest of the flow is unambiguous.

Path-based multi-database: on a shared host serving many databases with no dbfilter,
the ``?db=`` and monodb fallbacks are ambiguous. The connector can instead embed the
database in the URL path (``/mcp/<db>``). Every discovery + OAuth endpoint therefore
also answers under a ``/mcp/<db>`` (or ``/.well-known/oauth-*/mcp/<db>``) form and bakes
``/mcp/<db>`` into the advertised issuer/endpoints, so the whole flow resolves the right
database with no ``?db=`` at all.
"""
import json
import logging
from urllib.parse import quote, urlencode

from markupsafe import escape

from odoo import http, registry, SUPERUSER_ID
from odoo.api import Environment
from odoo.http import request

from .mcp_controller import _get_db_name, _mcp_db_from_path

_logger = logging.getLogger(__name__)


def _cors(extra=None):
    headers = [
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
    ]
    if extra:
        headers.extend(extra)
    return headers


def _json_response(payload, status=200, extra_headers=None):
    headers = _cors([("Content-Type", "application/json"), ("Cache-Control", "no-store")])
    if extra_headers:
        headers.extend(extra_headers)
    return request.make_response(json.dumps(payload), status=status, headers=headers)


def _base_url():
    """External base URL (scheme + host) as seen by the client, honouring the proxy."""
    req = request.httprequest
    proto = (req.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip() or req.scheme
    host = (req.headers.get("X-Forwarded-Host") or req.headers.get("Host") or req.host or "").strip()
    return "%s://%s" % (proto, host)


def _resolve_db_for_oauth():
    """Resolve the database for OAuth requests that may arrive without ?db=."""
    db = _get_db_name()
    if db:
        return db
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
        configured = odoo.tools.config.get("db_name")
        if configured:
            first = configured.split(",")[0].strip()
            if first:
                return first
    except Exception:
        pass
    return None


def _db_query(db):
    return ("?db=%s" % quote(db)) if db else ""


def _path_db(db=None):
    """The database for a *path-based* OAuth request.

    Prefer the ``<db>`` route converter value; otherwise recover it from the request
    path (e.g. ``/.well-known/oauth-protected-resource/mcp/<db>``). Returns None for the
    legacy query-based flow, which keeps advertising ``?db=`` URLs instead.
    """
    if db:
        return db
    return _mcp_db_from_path(request.httprequest.path or "")


class McpOAuthController(http.Controller):

    # ---- Discovery metadata -------------------------------------------------

    @http.route(
        ["/.well-known/oauth-protected-resource",
         "/.well-known/oauth-protected-resource/mcp",
         "/.well-known/oauth-protected-resource/mcp/<db>"],
        type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], save_session=False,
    )
    def protected_resource_metadata(self, db=None, **kw):
        """RFC 9728 — tells the client which authorization server protects the resource.

        Path-based form (``/.well-known/oauth-protected-resource/mcp/<db>``) advertises a
        db-scoped resource and issuer so the db survives the rest of the discovery chain
        on a shared multi-db host with no dbfilter.
        """
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=_cors())
        base = _base_url()
        path_db = _path_db(db)
        if path_db:
            prefix = "%s/mcp/%s" % (base, quote(path_db))
            return _json_response({
                "resource": prefix,
                "authorization_servers": [prefix],
                "bearer_methods_supported": ["header"],
                "scopes_supported": ["mcp"],
            })
        return _json_response({
            "resource": "%s/mcp" % base,
            "authorization_servers": [base],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"],
        })

    @http.route(
        ["/.well-known/oauth-authorization-server",
         "/.well-known/oauth-authorization-server/mcp",
         "/.well-known/oauth-authorization-server/mcp/<db>",
         "/mcp/<db>/.well-known/oauth-authorization-server"],
        type="http", auth="none", csrf=False, methods=["GET", "OPTIONS"], save_session=False,
    )
    def authorization_server_metadata(self, db=None, **kw):
        """RFC 8414 — advertises authorize/token/register endpoints.

        Path-based form bakes ``/mcp/<db>`` into the issuer and every endpoint, so no
        ``?db=`` is needed; the legacy form keeps advertising ``?db=`` URLs.
        """
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=_cors())
        base = _base_url()
        path_db = _path_db(db)
        if path_db:
            prefix = "%s/mcp/%s" % (base, quote(path_db))
            return _json_response({
                "issuer": prefix,
                "authorization_endpoint": "%s/oauth/authorize" % prefix,
                "token_endpoint": "%s/oauth/token" % prefix,
                "registration_endpoint": "%s/oauth/register" % prefix,
                "scopes_supported": ["mcp"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            })
        q = _db_query(_resolve_db_for_oauth())
        return _json_response({
            "issuer": base,
            "authorization_endpoint": "%s/mcp/oauth/authorize%s" % (base, q),
            "token_endpoint": "%s/mcp/oauth/token%s" % (base, q),
            "registration_endpoint": "%s/mcp/oauth/register%s" % (base, q),
            "scopes_supported": ["mcp"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        })

    # ---- Dynamic Client Registration ---------------------------------------

    @http.route(["/mcp/oauth/register", "/mcp/<db>/oauth/register"],
                type="http", auth="none", csrf=False,
                methods=["POST", "OPTIONS"], save_session=False)
    def register(self, db=None, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=_cors())
        db = db or _resolve_db_for_oauth()
        if not db:
            return _json_response({"error": "invalid_request",
                                   "error_description": "Cannot resolve database."}, status=400)
        try:
            body = request.httprequest.get_data(as_text=True) or "{}"
            data = json.loads(body)
        except Exception as e:
            return _json_response({"error": "invalid_client_metadata",
                                   "error_description": "Bad JSON: %s" % e}, status=400)
        redirect_uris = data.get("redirect_uris") or []
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return _json_response({"error": "invalid_redirect_uri",
                                   "error_description": "redirect_uris is required."}, status=400)
        auth_method = data.get("token_endpoint_auth_method") or "none"
        client_name = data.get("client_name")
        reg = registry(db)
        with reg.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            client = env["rag_odoo_mcp_server.oauth_client"].register(
                redirect_uris, client_name=client_name, auth_method=auth_method)
            resp = {
                "client_id": client.client_id,
                "client_id_issued_at": int(client.create_date.timestamp()),
                "redirect_uris": redirect_uris,
                "token_endpoint_auth_method": client.token_endpoint_auth_method,
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "client_name": client.client_name,
            }
            if client.client_secret:
                resp["client_secret"] = client.client_secret
            cr.commit()
        return _json_response(resp, status=201)

    # ---- Authorization (login + consent -> code) ---------------------------

    @http.route(["/mcp/oauth/authorize", "/mcp/<db>/oauth/authorize"],
                type="http", auth="public", methods=["GET", "POST"])
    def authorize(self, db=None, **kw):
        """Authorization endpoint. Requires the user to log into Odoo, then issues a code.

        GET  -> if not logged in, bounce to /web/login; else render a consent screen.
        POST -> user approved: mint a one-time code and redirect back to the client.

        Works path-based (``/mcp/<db>/oauth/authorize``) or query-based (``?db=``); the
        login bounce returns to the SAME local path, so the db is preserved either way.
        """
        db = db or _get_db_name() or _resolve_db_for_oauth()
        response_type = kw.get("response_type")
        client_id = kw.get("client_id")
        redirect_uri = kw.get("redirect_uri")
        state = kw.get("state")
        code_challenge = kw.get("code_challenge")
        code_challenge_method = (kw.get("code_challenge_method") or "S256")
        scope = kw.get("scope")
        resource = kw.get("resource")

        # Validate the client + redirect_uri BEFORE any redirect (prevents open redirect).
        client = request.env["rag_odoo_mcp_server.oauth_client"].sudo().find(client_id)
        if not client:
            return self._error_page("Unknown client_id.", 400)
        if not redirect_uri or not client.redirect_uri_allowed(redirect_uri):
            return self._error_page("redirect_uri is not registered for this client.", 400)
        if response_type != "code":
            return self._redirect_error(redirect_uri, state, "unsupported_response_type")
        if code_challenge_method != "S256" or not code_challenge:
            return self._redirect_error(redirect_uri, state, "invalid_request",
                                        "PKCE S256 code_challenge is required.")

        # Require an authenticated Odoo session. Bounce to Odoo's own login, asking it
        # to return here afterwards. The redirect target must be a LOCAL path (Odoo
        # rejects absolute-URL redirects on login for open-redirect safety).
        if not request.session.uid:
            qs = request.httprequest.query_string.decode("utf-8", "ignore")
            target = request.httprequest.path + (("?" + qs) if qs else "")
            login_url = "/web/login?%s" % urlencode({"db": db or "", "redirect": target})
            return request.redirect(login_url, local=True)

        if request.httprequest.method == "POST":
            if kw.get("decision") != "allow":
                return self._redirect_error(redirect_uri, state, "access_denied")
            code = request.env["rag_odoo_mcp_server.oauth_code"].sudo().issue(
                client_id=client_id,
                user_id=request.session.uid,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                scope=scope,
                resource=resource,
            )
            sep = "&" if "?" in redirect_uri else "?"
            params = {"code": code}
            if state:
                params["state"] = state
            return request.redirect("%s%s%s" % (redirect_uri, sep, urlencode(params)), local=False)

        # GET, logged in -> consent screen.
        user = request.env.user
        return self._consent_page(client, user, kw)

    # ---- Token endpoint (code -> token, refresh) ---------------------------

    @http.route(["/mcp/oauth/token", "/mcp/<db>/oauth/token"],
                type="http", auth="none", csrf=False,
                methods=["POST", "OPTIONS"], save_session=False)
    def token(self, db=None, **kw):
        if request.httprequest.method == "OPTIONS":
            return request.make_response("", headers=_cors())
        db = db or _resolve_db_for_oauth()
        if not db:
            return _json_response({"error": "invalid_request",
                                   "error_description": "Cannot resolve database."}, status=400)
        grant_type = kw.get("grant_type")
        client_id = kw.get("client_id")
        reg = registry(db)
        with reg.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            client = env["rag_odoo_mcp_server.oauth_client"].find(client_id)
            if not client:
                return _json_response({"error": "invalid_client"}, status=401)
            # Confidential clients must present their secret.
            if client.client_secret:
                if kw.get("client_secret") != client.client_secret:
                    return _json_response({"error": "invalid_client"}, status=401)

            if grant_type == "authorization_code":
                uid = env["rag_odoo_mcp_server.oauth_code"].consume(
                    code=kw.get("code"),
                    client_id=client_id,
                    redirect_uri=kw.get("redirect_uri"),
                    code_verifier=kw.get("code_verifier"),
                )
                if not uid:
                    return _json_response({"error": "invalid_grant"}, status=400)
                tok = env["rag_odoo_mcp_server.oauth_token"].issue(client_id, uid, scope=kw.get("scope"))
                cr.commit()
                return _json_response(tok)

            if grant_type == "refresh_token":
                tok = env["rag_odoo_mcp_server.oauth_token"].refresh(kw.get("refresh_token"), client_id)
                if not tok:
                    return _json_response({"error": "invalid_grant"}, status=400)
                cr.commit()
                return _json_response(tok)

            return _json_response({"error": "unsupported_grant_type"}, status=400)

    # ---- Small HTML helpers -------------------------------------------------

    def _html(self, body, status=200):
        page = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Authorize MCP access</title>"
            "<style>body{font-family:system-ui,Segoe UI,Roboto,sans-serif;background:#f6f7f9;"
            "margin:0;padding:40px;color:#1f2937}.card{max-width:440px;margin:0 auto;background:#fff;"
            "border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.08);padding:28px}"
            "h1{font-size:20px;margin:0 0 6px}p{color:#4b5563;line-height:1.5}"
            ".muted{color:#6b7280;font-size:13px}.row{display:flex;gap:12px;margin-top:22px}"
            "button{flex:1;padding:11px 14px;border-radius:9px;border:0;font-size:15px;cursor:pointer}"
            ".allow{background:#4f46e5;color:#fff}.deny{background:#e5e7eb;color:#111827}"
            ".pill{display:inline-block;background:#eef2ff;color:#4338ca;border-radius:999px;"
            "padding:2px 10px;font-size:12px;margin-left:6px}</style></head><body>"
            "<div class='card'>%s</div></body></html>" % body
        )
        return request.make_response(page, status=status,
                                     headers=[("Content-Type", "text/html; charset=utf-8")])

    def _consent_page(self, client, user, kw):
        hidden = "".join(
            "<input type='hidden' name='%s' value='%s'>" % (k, escape(kw.get(k) or ""))
            for k in ("response_type", "client_id", "redirect_uri", "state",
                      "code_challenge", "code_challenge_method", "scope", "resource")
        )
        # CSRF token — this consent POST changes state (mints an auth code for the
        # logged-in user), so it must be protected against cross-site submission.
        hidden += "<input type='hidden' name='csrf_token' value='%s'>" % escape(request.csrf_token())
        body = (
            "<h1>Connect to Odoo <span class='pill'>MCP</span></h1>"
            "<p><strong>%s</strong> wants to access this Odoo instance on your behalf.</p>"
            "<p class='muted'>You are signed in as <strong>%s</strong>. The assistant will act "
            "with your account's permissions — it can only see and do what you can.</p>"
            "<form method='post'>%s"
            "<div class='row'>"
            "<button class='deny' name='decision' value='deny' type='submit'>Cancel</button>"
            "<button class='allow' name='decision' value='allow' type='submit'>Allow</button>"
            "</div></form>"
            % (escape(client.client_name or "An MCP client"),
               escape(user.name or user.login or "this user"),
               hidden)
        )
        return self._html(body)

    def _error_page(self, message, status):
        return self._html("<h1>Authorization error</h1><p>%s</p>" % escape(message), status)

    def _redirect_error(self, redirect_uri, state, error, description=None):
        params = {"error": error}
        if description:
            params["error_description"] = description
        if state:
            params["state"] = state
        sep = "&" if "?" in redirect_uri else "?"
        return request.redirect("%s%s%s" % (redirect_uri, sep, urlencode(params)), local=False)
