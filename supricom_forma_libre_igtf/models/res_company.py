from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    supricom_fl_igtf_enabled = fields.Boolean(
        string='Módulo Forma Libre e IGTF Activo',
        help='Si se desactiva, se ocultarán los botones de aplicar IGTF y de impresión Forma Libre, y se detendrá la automatización.',
        default=True
    )
    
    igtf_product_id = fields.Many2one(
        'product.product',
        string='Producto para Recargo IGTF',
        help="Producto usado en las notas de débito generadas automáticamente por IGTF en pagos"
    )
