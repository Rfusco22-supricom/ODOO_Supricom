# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductPriceListItem(models.Model):
    _inherit = 'product.pricelist.item'

    currency_id_dif = fields.Many2one("res.currency",
                                      string="Moneda Dual Ref.",
                                      default=lambda self: self.env['res.currency'].search([('name', '=', 'USD')],
                                                                                           limit=1), )
    fixed_price = fields.Float(string="Fixed Price", digits='Product Price', 
                                        compute='_compute_fixed_price',
                                        inverse='_inverse_fixed_price',
                                        store=True,
                                        precompute=True)
    price_fixed_usd = fields.Monetary(string="Precio Fijo en Dolares", 
                                        currency_field='currency_id_dif')
                                        
    price_fixed_usd_vat = fields.Monetary(string="Precio Fijo en Dolares + IVA", currency_field='currency_id_dif', 
                                            compute='_compute_price_fixed_usd_vat',
                                            inverse='_inverse_price_fixed_usd_vat',
                                            store=True,
                                            precompute=True)


    @api.depends('price_fixed_usd')
    def _compute_fixed_price(self):
        for item in self:
            if not item.price_fixed_usd:
                continue
            company = item.company_id or self.env.company
            usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            if not usd_currency:
                continue
            currency_rate = self.env['res.currency.rate'].search([
                ('currency_id', '=', usd_currency.id),
                ('company_id', '=', company.id),
                ('name', '<=', fields.Date.today()),
            ], order='name desc', limit=1)
            if currency_rate and currency_rate.inverse_company_rate:
                item.fixed_price = item.price_fixed_usd * currency_rate.inverse_company_rate
            # Si no hay tasa o es 0, NO sobreescribir — mantener el precio actual

    def _inverse_fixed_price(self):
        for item in self:
            item.fixed_price = item.fixed_price

    @api.depends('price_fixed_usd','product_tmpl_id')
    def _compute_price_fixed_usd_vat(self):
        for item in self:
            item.price_fixed_usd_vat = item.product_tmpl_id.taxes_id.compute_all(item.price_fixed_usd, product=item.product_tmpl_id)['total_included']
            
    def _inverse_price_fixed_usd_vat(self):
        for item in self:
            item.price_fixed_usd_vat = item.price_fixed_usd_vat
        

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def update_price_bs(self):
        for line in self.item_ids:
            line._compute_fixed_price()