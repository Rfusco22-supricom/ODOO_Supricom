import logging
import traceback
import werkzeug
from odoo import models, api, fields, SUPERUSER_ID
from odoo.http import request
from odoo.exceptions import UserError, ValidationError, AccessError, AccessDenied

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _handle_exception(cls, exception):
        # Capture specific functional errors
        if isinstance(exception, (UserError, ValidationError, AccessError, AccessDenied)):
            try:
                cls._log_audit_error(exception)
            except Exception as e:
                _logger.error("Auditlog: Failed to log exception: %s", e)
        
        return super(IrHttp, cls)._handle_exception(exception)

    @classmethod
    def _log_audit_error(cls, exception):
        if not request:
            return

        # Use a new cursor to save the log even if the current transaction is rolled back
        registry = request.env.registry
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            error_name = type(exception).__name__
            message = str(exception)
            stack_trace = traceback.format_exc()
            
            # Determine device type from User Agent
            user_agent = request.httprequest.user_agent.string
            device_type = "Computadora"
            if user_agent:
                ua_lower = user_agent.lower()
                if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
                    device_type = "Telefono"
                elif "tablet" in ua_lower or "ipad" in ua_lower:
                    device_type = "Tablet"

            vals = {
                'name': error_name,
                'message': message,
                'stack_trace': stack_trace,
                'user_id': request.session.uid or env.ref('base.public_user').id,
                'url': request.httprequest.url,
                'user_agent': user_agent,
                'device_type': device_type,
                'client_timestamp': fields.Datetime.now(), # Server time as fallback
            }
            
            # Try to link to session if possible
            # Note: We don't have easy access to the auditlog session ID here unless we search for it
            # or if it was stored in the request during this request cycle.
            # For now, we leave http_session_id empty or we could search for it.
            
            env['auditlog.client.error'].create(vals)
