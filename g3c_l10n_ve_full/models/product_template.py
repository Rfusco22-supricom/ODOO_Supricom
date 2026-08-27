from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    is_standard_price_invisible = fields.Boolean(compute='_compute_standard_price_invisible', string="Costos no visibles")
    
    # change_price_unit_readonly = fields.Boolean(string="Habilitar edición precio unitario")

    @api.onchange('detailed_type')
    def _compute_standard_price_invisible(self):
        for line in self:
            user = self.env.user
            line.is_standard_price_invisible = not user.has_group('g3c_l10n_ve_full.group_allow_change_price_purchase')
            print(f"is_standard_price_invisible: {line.is_standard_price_invisible}")
