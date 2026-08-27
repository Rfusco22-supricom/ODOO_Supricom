from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hide_sale_confirm = fields.Boolean(
        related='company_id.hide_sale_confirm',
        readonly=False,
        string='Ocultar botón de Confirmar en Ventas'
    )

    homologacion_activa = fields.Boolean(
        related='company_id.homologacion_activa',
        readonly=False,
        string='Activar G3C'
    )
    
    igtf_product_id = fields.Many2one(
        'product.product',
        related='company_id.igtf_product_id',
        readonly=False,
        string='Producto para Recargo IGTF'
    )

    igtf_debit_note_paid = fields.Boolean(
        related='company_id.igtf_debit_note_paid',
        readonly=False,
        string='Generar ND de IGTF Pagada'
    )
