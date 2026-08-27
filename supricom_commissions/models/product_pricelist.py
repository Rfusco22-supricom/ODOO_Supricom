from odoo import models, fields

class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    commission_mapped_pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Lista Base para Comisiones",
        help="Si se usa esta lista de precios en una orden de venta, el sistema recalculará la comisión usando los precios de la lista seleccionada aquí (Ej. Lista Oficial -> Lista USD).",
    )
