from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = "sale.order"

    allow_below_min_price = fields.Boolean(
        string="Autorizar Precio por Debajo del Mínimo",
        tracking=True,
        help="Si se marca, permite vender productos por debajo de su precio mínimo establecido. Usar con precaución.",
    )
