from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    hide_sale_confirm = fields.Boolean(
        string='Ocultar botón de Confirmar en Ventas',
        help='Si está marcado, los usuarios no podrán confirmar presupuestos de venta.',
        default=False
    )

    homologacion_activa = fields.Boolean(
        string='Activar G3C',
        help='Si se desactiva, se omitirán las restricciones de inventario y bloqueos fiscales (excepto IGTF).',
        default=True
    )

    igtf_product_id = fields.Many2one(
        'product.product',
        string='Producto para Recargo IGTF',
        help="Producto usado en las notas de débito generadas automáticamente por IGTF en pagos de cliente"
    )

    igtf_debit_note_paid = fields.Boolean(
        string='Generar ND de IGTF Pagada',
        help='Si está marcado, la Nota de Débito de IGTF generada automáticamente se conciliará con el asiento del pago.',
        default=False
    )
