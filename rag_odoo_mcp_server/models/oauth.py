# -*- coding: utf-8 -*-
"""
OAuth 2.1 storage for the MCP Streamable HTTP transport.

Modern MCP clients (Claude desktop/web "custom connector") authenticate to a remote
MCP server with OAuth 2.1 (the MCP Authorization spec), not a static header. These
three PostgreSQL-backed models implement the server side of that flow so a user can
add the connector URL, log in with their normal Odoo account, and have Claude run
every tool AS that user (their ORM access rights are the real boundary).

Flow (see controllers/mcp_oauth.py):
  register  -> oauth_client   (Dynamic Client Registration; public + PKCE)
  authorize -> oauth_code     (short-lived one-time code, bound to the Odoo user + PKCE)
  token     -> oauth_token    (opaque access + refresh tokens, bound to the user)
  /mcp      -> validate_access_token() resolves a Bearer token back to a uid.

Everything is DB-backed so it works across multiple workers / instances behind the
load balancer.
"""
import base64
import hashlib
import logging
import secrets

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Lifetimes. Access tokens are short (clients refresh); codes are single-use and brief.
ACCESS_TOKEN_TTL_SECONDS = 3600            # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
AUTH_CODE_TTL_SECONDS = 600                # 10 minutes


def _now():
    return fields.Datetime.now()


def _b64url_nopad(raw):
    """base64url without padding — the encoding PKCE and token generation use."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def verify_pkce_s256(code_verifier, code_challenge):
    """Return True if S256(code_verifier) matches the stored code_challenge."""
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = _b64url_nopad(digest)
    return secrets.compare_digest(expected, code_challenge)


class OAuthClient(models.Model):
    _name = "rag_odoo_mcp_server.oauth_client"
    _description = "MCP OAuth Client (Dynamic Client Registration)"
    _order = "create_date desc"
    _rec_name = "client_id"

    client_id = fields.Char(required=True, index=True)
    client_secret = fields.Char()  # empty for public (PKCE) clients
    client_name = fields.Char()
    redirect_uris = fields.Text(help="JSON array of allowed redirect URIs.")
    token_endpoint_auth_method = fields.Char(default="none")

    _sql_constraints = [
        ("client_id_unique", "unique(client_id)", "OAuth client_id must be unique."),
    ]

    @api.model
    def register(self, redirect_uris, client_name=None, auth_method="none"):
        """Create a new registered client and return its record."""
        import json
        client_id = _b64url_nopad(secrets.token_bytes(24))
        secret = None
        if auth_method and auth_method != "none":
            secret = _b64url_nopad(secrets.token_bytes(32))
        return self.sudo().create({
            "client_id": client_id,
            "client_secret": secret or False,
            "client_name": client_name or "MCP Client",
            "redirect_uris": json.dumps(list(redirect_uris or [])),
            "token_endpoint_auth_method": auth_method or "none",
        })

    @api.model
    def find(self, client_id):
        if not client_id:
            return self.browse([])
        return self.sudo().search([("client_id", "=", client_id)], limit=1)

    def redirect_uri_allowed(self, redirect_uri):
        """True if redirect_uri exactly matches one of the client's registered URIs."""
        import json
        self.ensure_one()
        try:
            allowed = json.loads(self.redirect_uris or "[]")
        except Exception:
            allowed = []
        return redirect_uri in allowed


class OAuthCode(models.Model):
    _name = "rag_odoo_mcp_server.oauth_code"
    _description = "MCP OAuth Authorization Code (single use)"
    _order = "id desc"
    _rec_name = "code"

    code = fields.Char(required=True, index=True)
    client_id = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    redirect_uri = fields.Char(required=True)
    code_challenge = fields.Char()
    code_challenge_method = fields.Char(default="S256")
    scope = fields.Char()
    resource = fields.Char()
    expires_at = fields.Datetime(required=True, index=True)
    used = fields.Boolean(default=False, index=True)

    _sql_constraints = [
        ("code_unique", "unique(code)", "OAuth code must be unique."),
    ]

    @api.model
    def issue(self, client_id, user_id, redirect_uri, code_challenge,
              code_challenge_method="S256", scope=None, resource=None):
        code = _b64url_nopad(secrets.token_bytes(32))
        self.sudo().create({
            "code": code,
            "client_id": client_id,
            "user_id": user_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge or False,
            "code_challenge_method": code_challenge_method or "S256",
            "scope": scope or False,
            "resource": resource or False,
            "expires_at": fields.Datetime.add(_now(), seconds=AUTH_CODE_TTL_SECONDS),
        })
        return code

    @api.model
    def consume(self, code, client_id, redirect_uri, code_verifier):
        """Validate + burn an authorization code. Returns the res.users id or None.

        Enforces: code exists, not used, not expired, bound to this client and
        redirect_uri, and PKCE S256 verifier matches.
        """
        if not code:
            return None
        rec = self.sudo().search([("code", "=", code)], limit=1)
        if not rec:
            return None
        # Single use — mark immediately so a replay can never succeed, even on error.
        already_used = rec.used
        rec.write({"used": True})
        if already_used:
            _logger.warning("MCP OAuth: authorization code replay detected for client %s", client_id)
            return None
        if rec.expires_at and rec.expires_at < _now():
            return None
        if rec.client_id != client_id:
            return None
        if rec.redirect_uri != redirect_uri:
            return None
        if rec.code_challenge:
            if not verify_pkce_s256(code_verifier, rec.code_challenge):
                _logger.warning("MCP OAuth: PKCE verification failed for client %s", client_id)
                return None
        return rec.user_id.id


class OAuthToken(models.Model):
    _name = "rag_odoo_mcp_server.oauth_token"
    _description = "MCP OAuth Access/Refresh Token"
    _order = "id desc"
    _rec_name = "user_id"

    access_token = fields.Char(required=True, index=True)
    refresh_token = fields.Char(index=True)
    client_id = fields.Char(index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    scope = fields.Char()
    access_expires_at = fields.Datetime(required=True, index=True)
    refresh_expires_at = fields.Datetime()
    revoked = fields.Boolean(default=False, index=True)

    _sql_constraints = [
        ("access_token_unique", "unique(access_token)", "OAuth access_token must be unique."),
    ]

    @api.model
    def issue(self, client_id, user_id, scope=None):
        """Create a fresh access+refresh token pair. Returns a dict for the token response."""
        access = _b64url_nopad(secrets.token_bytes(32))
        refresh = _b64url_nopad(secrets.token_bytes(32))
        self.sudo().create({
            "access_token": access,
            "refresh_token": refresh,
            "client_id": client_id,
            "user_id": user_id,
            "scope": scope or False,
            "access_expires_at": fields.Datetime.add(_now(), seconds=ACCESS_TOKEN_TTL_SECONDS),
            "refresh_expires_at": fields.Datetime.add(_now(), seconds=REFRESH_TOKEN_TTL_SECONDS),
        })
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "refresh_token": refresh,
            "scope": scope or "",
        }

    @api.model
    def validate_access_token(self, access_token):
        """Return the res.users id for a valid, unexpired, unrevoked token, else None."""
        if not access_token:
            return None
        rec = self.sudo().search([("access_token", "=", access_token)], limit=1)
        if not rec or rec.revoked:
            return None
        if rec.access_expires_at and rec.access_expires_at < _now():
            return None
        if not rec.user_id or not rec.user_id.active:
            return None
        return rec.user_id.id

    @api.model
    def refresh(self, refresh_token, client_id):
        """Rotate a refresh token. Returns a new token dict or None if invalid."""
        if not refresh_token:
            return None
        rec = self.sudo().search([("refresh_token", "=", refresh_token)], limit=1)
        if not rec or rec.revoked:
            return None
        if rec.refresh_expires_at and rec.refresh_expires_at < _now():
            return None
        if rec.client_id != client_id:
            return None
        if not rec.user_id or not rec.user_id.active:
            return None
        uid = rec.user_id.id
        scope = rec.scope
        # Rotate: revoke the old pair, issue a new one.
        rec.write({"revoked": True})
        return self.issue(client_id, uid, scope=scope)

    @api.model
    def _gc(self):
        """Delete expired/revoked tokens and codes. Called by ir.cron."""
        now = _now()
        self.sudo().search([
            "|", ("revoked", "=", True),
            ("refresh_expires_at", "<", now),
        ]).unlink()
        self.env["rag_odoo_mcp_server.oauth_code"].sudo().search([
            "|", ("used", "=", True),
            ("expires_at", "<", now),
        ]).unlink()
