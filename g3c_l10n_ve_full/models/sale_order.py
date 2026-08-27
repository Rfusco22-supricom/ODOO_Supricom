from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_price_unit_readonly = fields.Boolean(compute='_compute_price_unit_readonly',string="Es de solo lectura el precio unitario?")
    
    change_price_unit_readonly = fields.Boolean(string="Permitir cambiar precio")

    @api.onchange('partner_id')
    def _compute_price_unit_readonly(self):
        for line in self:
            user = self.env.user
            line.is_price_unit_readonly = user.has_group('g3c_l10n_ve_full.group_allow_change_price_sales')
            print(f"is_price_unit_readonly: {line.is_price_unit_readonly}, change_price_unit_readonly:{line.change_price_unit_readonly}")
