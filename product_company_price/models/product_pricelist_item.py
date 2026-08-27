# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    fixed_price_usd = fields.Float(
        string="Fixed Price USD",
        digits='Product Price',
        default=0.0,
    )
