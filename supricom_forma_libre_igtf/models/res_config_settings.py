from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    supricom_fl_igtf_enabled = fields.Boolean(
        related='company_id.supricom_fl_igtf_enabled',
        readonly=False,
        string='Módulo Forma Libre e IGTF Activo'
    )
    
    igtf_product_id = fields.Many2one(
        'product.product',
        related='company_id.igtf_product_id',
        readonly=False,
        string='Producto para Recargo IGTF'
    )
