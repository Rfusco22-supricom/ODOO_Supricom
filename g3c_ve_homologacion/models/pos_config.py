from odoo import models, api, fields

class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Forzamos la desactivación de precuentas y reimpresiones
    iface_print_bill = fields.Boolean(default=False, readonly=True)
    iface_reprint_receipt = fields.Boolean(default=False, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['iface_print_bill'] = False
            vals['iface_reprint_receipt'] = False
        return super(PosConfig, self).create(vals_list)

    def write(self, vals):
        if 'iface_print_bill' in vals:
            vals['iface_print_bill'] = False
        if 'iface_reprint_receipt' in vals:
            vals['iface_reprint_receipt'] = False
        return super(PosConfig, self).write(vals)
