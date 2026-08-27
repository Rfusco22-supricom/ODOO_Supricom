from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AuditlogLog(models.Model):
    _name = "auditlog.log"
    _description = "Auditlog - Log"
    _order = "create_date desc"

    name = fields.Char("Resource Name", size=64, help="The name of the resource being logged (e.g., model name or resource identifier).")
    model_id = fields.Many2one("ir.model", string="Model", index=True, ondelete="set null", help="The technical model name associated with the resource.")
    model_name = fields.Char(readonly=True, help="The name of the model associated with the resource.")
    model_model = fields.Char(string="Technical Model Name", readonly=True)
    res_id = fields.Integer("Resource ID", help="The ID of the specific resource instance being logged.")
    user_id = fields.Many2one("res.users", string="User", help="The user who triggered or is associated with this log entry.")
    method = fields.Char(size=64,)
    line_ids = fields.One2many("auditlog.log.line", "log_id", string="Fields updated",  help="The specific fields that were updated or changed as part of this log entry.")
    http_session_id = fields.Many2one("auditlog.http.session", string="Session", index=True, help="The HTTP session associated with this log entry.")
    http_request_id = fields.Many2one("auditlog.http.request", string="HTTP Request", index=True, help="The specific HTTP request associated with this log entry.")
    log_type = fields.Selection([("full", "Full log"), ("fast", "Fast log")], string="Type",  help="The type of log: 'Full log' captures all details, 'Fast log' captures basic details.")
    methods = fields.Char(string='Methods', compute="_compute_methods", store=False, help="The method or action that triggered this log entry.")

    @api.depends("method")
    def _compute_methods(self):
        translation_dict = {
            "create": _("create"),
            "read": _("read"),
            "write": _("write"),
            "unlink": _("delete"),
        }
        for record in self:
            record.methods = translation_dict.get(record.method, record.method)
            
    @api.model_create_multi
    def create(self, vals_list):
        """Insert model_name and model_model field values upon creation."""
        for vals in vals_list:
            if not vals.get("model_id"):
                raise UserError(_("No model defined to create log."))
            model = self.env["ir.model"].sudo().browse(vals["model_id"])
            vals.update({"model_name": model.name, "model_model": model.model})
        return super().create(vals_list)

    def write(self, vals):
        """Update model_name and model_model field values to reflect model_id
        changes."""
        if "model_id" in vals:
            if not vals["model_id"]:
                raise UserError(_("The field 'model_id' cannot be empty."))
            model = self.env["ir.model"].sudo().browse(vals["model_id"])
            vals.update({"model_name": model.name, "model_model": model.model})
        return super().write(vals)


class AuditlogLogLine(models.Model):
    _name = "auditlog.log.line"
    _description = "Auditlog - Log details (fields updated)"

    field_id = fields.Many2one(
        "ir.model.fields", ondelete="set null", string="Field", index=True
    )
    log_id = fields.Many2one(
        "auditlog.log", string="Log", ondelete="cascade", index=True
    )
    old_value = fields.Text()
    new_value = fields.Text()
    old_value_text = fields.Text("Old value Text")
    new_value_text = fields.Text("New value Text")
    field_name = fields.Char("Technical name", readonly=True)
    field_description = fields.Char("Description", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure field_id is not empty on creation and store field_name and
        field_description."""
        for vals in vals_list:
            if not vals.get("field_id"):
                raise UserError(_("No field defined to create line."))
            field = self.env["ir.model.fields"].sudo().browse(vals["field_id"])
            vals.update(
                {"field_name": field.name, "field_description": field.field_description}
            )
        return super().create(vals_list)

    def write(self, vals):
        """Ensure field_id is set during write and update field_name and
        field_description values."""
        if "field_id" in vals:
            if not vals["field_id"]:
                raise UserError(_("The field 'field_id' cannot be empty."))
            field = self.env["ir.model.fields"].sudo().browse(vals["field_id"])
            vals.update(
                {"field_name": field.name, "field_description": field.field_description}
            )
        return super().write(vals)