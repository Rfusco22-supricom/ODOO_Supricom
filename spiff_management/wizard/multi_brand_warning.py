# wizard/multi_brand_warning.py
from odoo import models, fields, api, _

class SpiffMultiBrandWarning(models.TransientModel):
    _name = 'spiff.multi.brand.warning'
    _description = 'Advertencia de Múltiples Marcas'

    order_id = fields.Many2one('sale.order', string="Pedido", required=True)
    brand_names = fields.Char(string="Marcas con Extensión")

    def action_confirm_anyway(self):
        self.ensure_one()
        # Confirm bypassing the multi-brand check
        return self.order_id.with_context(skip_multi_brand_check=True).action_confirm()
