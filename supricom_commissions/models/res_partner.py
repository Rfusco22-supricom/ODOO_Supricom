from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_vendor = fields.Boolean(
        string="Es Vendedor",
        help="Marcar si este contacto es un vendedor activo para el cálculo de comisiones.",
    )
    vendor_type_id = fields.Many2one(
        "commission.vendor.type",
        string="Tipo de Vendedor",
        help="Clasificación del vendedor para determinar sus reglas de comisión.",
    )

    @api.onchange('vendor_type_id')
    def _onchange_vendor_type_id(self):
        if self.vendor_type_id:
            self.is_vendor = True

    @api.onchange('country_id')
    def _onchange_country_id(self):
        self.vendor_type_id = False
        if not self.country_id:
            return {'domain': {'vendor_type_id': []}}
        
        country_code = self.country_id.code
        domain_code = False
        
        if country_code == 'VE':
            domain_code = 'VEN'
        elif country_code == 'PA':
            domain_code = 'PAN'
            
        if domain_code:
            return {'domain': {'vendor_type_id': [('country', '=', domain_code)]}}
        else:
            return {'domain': {'vendor_type_id': [('country', '=', 'NonExistent')]}}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('vendor_type_id') and 'is_vendor' not in vals:
                vals['is_vendor'] = True
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('vendor_type_id') and 'is_vendor' not in vals:
            vals['is_vendor'] = True
        return super().write(vals)

