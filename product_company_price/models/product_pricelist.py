# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    is_default_company_price = fields.Boolean(
        string="Es Predeterminada",
        default=False,
        help="Si está activo, esta lista de precios será utilizada para "
             "establecer el Precio Base por empresa en los productos.",
    )

    @api.constrains('is_default_company_price', 'company_id')
    def _check_unique_default_per_company(self):
        for pricelist in self:
            if pricelist.is_default_company_price and pricelist.company_id:
                existing = self.search([
                    ('is_default_company_price', '=', True),
                    ('company_id', '=', pricelist.company_id.id),
                    ('id', '!=', pricelist.id),
                ])
                if existing:
                    raise ValidationError(
                        "Ya existe una lista de precios predeterminada para la empresa %s: '%s'.\n"
                        "Desactive la anterior antes de activar esta."
                        % (pricelist.company_id.name, existing[0].name)
                    )
