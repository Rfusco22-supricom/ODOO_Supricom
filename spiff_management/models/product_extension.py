from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    spiff_brand_id = fields.Many2one('spiff.brand', string="Marca (SPIFF)", help="Marca del producto para el cálculo de incentivos SPIFF")