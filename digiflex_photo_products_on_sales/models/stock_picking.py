# -*- coding: utf-8 -*-
from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    show_product_image = fields.Boolean(
        string="Mostrar Foto en Operación de Entrega",
        default=True,
        help="Si está activado, se incluirá la imagen del producto en las líneas de la orden de entrega y en la guía impresa PDF."
    )


class StockMove(models.Model):
    _inherit = 'stock.move'

    product_image = fields.Binary(
        related='product_id.image_128',
        string="Foto",
        readonly=True
    )
