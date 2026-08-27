# -*- coding: utf-8 -*-
from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    show_product_image = fields.Boolean(
        string="Mostrar Foto en Cotización",
        default=True,
        help="Si está activado, se incluirá la imagen del producto en las líneas de la cotización impresa (PDF) y vista."
    )


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_image = fields.Binary(
        related='product_id.image_128',
        string="Foto",
        readonly=True
    )
