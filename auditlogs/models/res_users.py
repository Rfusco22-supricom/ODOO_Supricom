import logging
import odoo
from odoo import models, api, SUPERUSER_ID
from odoo.http import request
from odoo.exceptions import AccessDenied

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = "res.users"

    @classmethod
    def _login(cls, db, login, password, user_agent_env):
        try:
            uid = super(ResUsers, cls)._login(db, login, password, user_agent_env)
            cls._log_audit_session(db, login, 'success', uid=uid)
            return uid
        except AccessDenied:
            cls._log_audit_session(db, login, 'failed')
            raise

    @classmethod
    def _log_audit_session(cls, db, login, status, uid=None):
        if not request:
            return
        
        try:
            registry = odoo.registry(db)
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                
                vals = {
                    'name': request.session.sid,
                    'user_id': uid,
                    'login': login,
                    'status': status,
                    'remote_ip': request.httprequest.remote_addr,
                }
                env['auditlog.http.session'].create(vals)
        except Exception as e:
            _logger.error("Could not create auditlog session: %s", e)
