# -*- coding: utf-8 -*-
"""
Database-backed MCP session storage.

The MCP transport (SSE + POST) needs to correlate a GET /mcp/sse stream with the
subsequent POST /mcp/messages requests. The previous implementation stored sessions
in a module-level Python dict — that breaks the moment Odoo runs multiple workers
(Odoo.sh always does), because the POST may land on a different worker than the
one that created the session, yielding "Unknown or expired session" 400 errors.

These two models persist sessions and per-session JSON-RPC response queues in
PostgreSQL so any worker can serve any session.

Lifecycle:
  - GET /mcp/sse  → mcp_session.create_session(...)  → SSE stream polls
                    mcp_session_message every ~1s for undelivered rows.
  - POST /mcp/messages → looks up session, dispatches JSON-RPC, then
                         mcp_session_message.push(session_id, response).
  - SSE stream sees the new message on its next poll, emits it, marks delivered.
  - On disconnect / GC → mark_closed(session_id); periodic cron prunes.
"""
import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Sessions idle longer than this are considered abandoned and will be marked closed
# by the GC cron. The default (30 minutes) is well above the SSE keepalive window
# but short enough to free DB rows on dropped connections.
SESSION_IDLE_MINUTES = 30

# Closed sessions and their delivered messages older than this are hard-deleted.
RETENTION_MINUTES = 60


class McpSession(models.Model):
    _name = "rag_odoo_mcp_server.mcp_session"
    _description = "MCP SSE Session (DB-backed for multi-worker deployments)"
    _order = "create_date desc"
    _rec_name = "session_id"

    session_id = fields.Char(string="Session ID", required=True, index=True)
    company_id = fields.Integer(string="Company ID (from SSE connect)")
    state = fields.Selection(
        [("active", "Active"), ("closed", "Closed")],
        default="active",
        required=True,
        index=True,
    )
    last_seen = fields.Datetime(default=fields.Datetime.now, required=True, index=True)

    _sql_constraints = [
        ("session_id_unique", "unique(session_id)", "MCP session_id must be unique."),
    ]

    @api.model
    def create_session(self, session_id, company_id=None):
        """Insert a new active session row."""
        return self.sudo().create({
            "session_id": session_id,
            "company_id": company_id or 0,
            "state": "active",
            "last_seen": fields.Datetime.now(),
        })

    @api.model
    def find_active(self, session_id):
        """Return an active session recordset for *session_id*, or empty."""
        if not session_id:
            return self.browse([])
        return self.sudo().search(
            [("session_id", "=", session_id), ("state", "=", "active")],
            limit=1,
        )

    @api.model
    def touch(self, session_id):
        """Bump last_seen for an active session. No-op if the session is gone."""
        sess = self.find_active(session_id)
        if sess:
            sess.write({"last_seen": fields.Datetime.now()})
        return bool(sess)

    @api.model
    def mark_closed(self, session_id):
        """Mark a session as closed (best-effort; idempotent)."""
        if not session_id:
            return
        recs = self.sudo().search([("session_id", "=", session_id)], limit=1)
        if recs:
            recs.write({"state": "closed"})

    @api.model
    def get_company_id(self, session_id):
        """Return the company_id stored at SSE connect, or None."""
        sess = self.find_active(session_id)
        if not sess:
            return None
        cid = sess.company_id
        return cid if cid else None

    @api.model
    def _gc(self):
        """Periodic garbage collection — called by ir.cron."""
        Message = self.env["rag_odoo_mcp_server.mcp_session_message"].sudo()
        # 1) Close sessions that are silent past the idle window (probably dropped client).
        idle_cutoff = fields.Datetime.subtract(fields.Datetime.now(), minutes=SESSION_IDLE_MINUTES)
        stale = self.sudo().search([
            ("state", "=", "active"),
            ("last_seen", "<", idle_cutoff),
        ])
        if stale:
            stale.write({"state": "closed"})
        # 2) Delete closed sessions and their messages older than the retention window.
        retention_cutoff = fields.Datetime.subtract(fields.Datetime.now(), minutes=RETENTION_MINUTES)
        old_sessions = self.sudo().search([
            ("state", "=", "closed"),
            ("last_seen", "<", retention_cutoff),
        ])
        if old_sessions:
            session_ids = old_sessions.mapped("session_id")
            # Delete their messages first
            Message.search([("session_id", "in", session_ids)]).unlink()
            old_sessions.unlink()
        # 3) Delete orphaned messages (session row gone for any reason).
        Message.search([
            ("create_date", "<", retention_cutoff),
            ("delivered", "=", True),
        ]).unlink()


class McpSessionMessage(models.Model):
    _name = "rag_odoo_mcp_server.mcp_session_message"
    _description = "MCP JSON-RPC response queued for delivery over SSE"
    _order = "id"

    session_id = fields.Char(string="Session ID", required=True, index=True)
    payload = fields.Text(string="JSON-RPC payload", required=True)
    delivered = fields.Boolean(default=False, index=True)

    @api.model
    def push(self, session_id, payload):
        """Insert one JSON-RPC response payload to be delivered on the SSE stream.

        *payload* may be a dict (will be json.dumps'd) or a pre-serialized string.
        """
        if not session_id:
            _logger.warning("MCP push called without session_id; dropping payload.")
            return self.browse([])
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        return self.sudo().create({
            "session_id": session_id,
            "payload": payload or "",
            "delivered": False,
        })

    @api.model
    def pop_undelivered(self, session_id, limit=50):
        """Return JSON-RPC payload strings to deliver, and mark them delivered.

        Caller is expected to commit the cursor so the 'delivered' flag persists
        before the next poll runs (otherwise the same rows would be re-emitted).
        """
        if not session_id:
            return []
        msgs = self.sudo().search(
            [("session_id", "=", session_id), ("delivered", "=", False)],
            order="id",
            limit=limit,
        )
        if not msgs:
            return []
        payloads = [m.payload or "" for m in msgs]
        msgs.write({"delivered": True})
        return payloads
