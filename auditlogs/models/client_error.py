from odoo import fields, models, api

class AuditlogClientError(models.Model):
    _name = "auditlog.client.error"
    _description = "Auditlog - Client Error"
    _order = "create_date desc"

    name = fields.Char("Error Name", required=True)
    message = fields.Text("Message", required=True)
    stack_trace = fields.Text("Stack Trace")
    user_id = fields.Many2one("res.users", string="User")
    http_session_id = fields.Many2one("auditlog.http.session", string="Session")
    url = fields.Char("URL")
    user_agent = fields.Char("User Agent")
    device_type = fields.Char("Device Type")
    client_timestamp = fields.Char("Client Timestamp")
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('user_id'):
                vals['user_id'] = self.env.user.id
            
            # Try to link to a session if we can find one matching the user/request
            # This is tricky because the request that sends the log might be different from the one that caused it.
            # But we can try to find the current session.
            if not vals.get('http_session_id') and hasattr(self.env['auditlog.http.session'], 'current_http_session'):
                 # We might need to be careful about recursion or overhead here, but it should be fine.
                 # However, current_http_session relies on request.session.
                 # If the log is sent via RPC, there is a session.
                 pass 
                 # Actually, let's leave it to the default logic or explicit passing if needed.
                 # If we want to link it to the *current* session when the log is reported:
                 
        return super().create(vals_list)
