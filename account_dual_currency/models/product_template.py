# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class Productos(models.Model):
    _inherit = 'product.template'

    list_price_usd = fields.Float(string="Precio de venta $", compute='_compute_list_price_usd', inverse='_set_list_price_usd', required=True, default=0.0, tracking=2, store=True)
    standard_price_usd = fields.Float(string="Costo $", inverse='_set_standard_price_usd', compute='_compute_standard_price_usd', readonly=False, store=True)
    costo_reposicion_usd = fields.Float(string="Costo Reposición $")
    list_price_vat_usd = fields.Float('Precio de Venta USD + IVA', digits='Product Price', compute='_compute_list_price_vat_usd', inverse='_set_list_price_vat_usd', required=True, default=0.0, tracking=2, store=True)
    list_price_vat = fields.Float('Precio de Venta  + IVA', digits='Product Price', compute='_compute_list_price_vat', inverse='_set_list_price_vat', required=True, default=0.0, tracking=2, store=True)
    is_ve_company = fields.Boolean(
        string="Company Is VE",
        compute='_compute_is_ve_company'
    )

    @api.depends_context('company')
    def _compute_is_ve_company(self):
        for rec in self:
            rec.is_ve_company = self.env.company.is_ve_company
    
        
    @api.depends('product_variant_ids', 'product_variant_ids.list_price_usd')
    def _compute_list_price_usd(self):
        unique_variants = self.filtered(lambda x: len(x.product_variant_ids) == 1)
        for template in unique_variants:
            template.list_price_usd = template.product_variant_ids.list_price_usd
        for template in (self - unique_variants):
            template.list_price_usd = template.product_variant_ids[0].list_price_usd if len(template.product_variant_ids) > 0 else 0

    def _set_list_price_usd(self):
        for item in self:
            if len(item.product_variant_ids) == 1:
                item.product_variant_ids.list_price_usd = item.list_price_usd

    @api.depends('product_variant_ids', 'product_variant_ids.list_price_vat_usd')
    def _compute_list_price_vat_usd(self):
        unique_variants = self.filtered(lambda x: len(x.product_variant_ids) == 1)
        for template in unique_variants:
            template.list_price_vat_usd = template.product_variant_ids.list_price_vat_usd
        for template in (self - unique_variants):
            template.list_price_vat_usd = template.product_variant_ids[0].list_price_vat_usd if len(template.product_variant_ids) > 0 else 0
    
    def _set_list_price_vat_usd(self):
        for item in self:
            if len(item.product_variant_ids) == 1:
                item.product_variant_ids.list_price_vat_usd = item.list_price_vat_usd

    @api.depends('product_variant_ids', 'product_variant_ids.list_price_vat')
    def _compute_list_price_vat(self):
        unique_variants = self.filtered(lambda x: len(x.product_variant_ids) == 1)
        for template in unique_variants:
            template.list_price_vat = template.product_variant_ids.list_price_vat
        for template in (self - unique_variants):
            template.list_price_vat = template.product_variant_ids[0].list_price_vat if len(template.product_variant_ids) > 0 else 0

    def _set_list_price_vat(self):
        for item in self:
            if len(item.product_variant_ids) == 1:
                item.product_variant_ids.list_price_vat = item.list_price_vat

    def _set_standard_price_usd(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.standard_price_usd = template.standard_price_usd

    @api.depends_context('company')
    @api.depends('product_variant_ids', 'product_variant_ids.standard_price_usd')
    def _compute_standard_price_usd(self):
        # Depends on force_company context because standard_price is company_dependent
        # on the product_product
        for rec in self:
            if len(rec.product_variant_ids) == 1:
                rec.standard_price_usd = rec.product_variant_ids[0].standard_price_usd
            else:
                rec.standard_price_usd = 0.0

    @api.onchange('list_price_usd')
    def _onchange_list_price_usd(self):
        for rec in self:
            if rec.list_price_usd > 0:
                if rec.company_id.currency_id.name == 'USD':
                    rec.list_price = rec.list_price_usd
                    taxes = rec.taxes_id.sudo().filtered(lambda t: t.company_id == rec.company_id)
                    rec.list_price_vat_usd = taxes.compute_all(rec.list_price_usd, product=rec)['total_included']
                    rec.list_price_vat = rec.list_price_vat_usd
                else:
                    tasa = self.env.company.currency_id_dif
                    if tasa:
                        rec.list_price = rec.list_price_usd * tasa.inverse_rate
                        taxes = rec.taxes_id.sudo().filtered(lambda t: t.company_id == rec.company_id)
                        rec.list_price_vat_usd = taxes.compute_all(rec.list_price_usd, product=rec)['total_included']
                        rec.list_price_vat = taxes.compute_all(rec.list_price, product=rec)['total_included']

    @api.constrains('list_price_usd')
    def _constrains_list_price_usd(self):
        for rec in self:
            if rec.list_price_usd > 0:
                if rec.company_id.currency_id.name == 'USD':
                    rec.list_price = rec.list_price_usd
                    taxes = rec.taxes_id.sudo().filtered(lambda t: t.company_id == rec.company_id)
                    rec.list_price_vat_usd = taxes.compute_all(rec.list_price_usd, product=rec)['total_included']
                    rec.list_price_vat = rec.list_price_vat_usd
                else:
                    tasa = self.env.company.currency_id_dif
                    if tasa:
                        rec.list_price = rec.list_price_usd * tasa.inverse_rate
                        taxes = rec.taxes_id.sudo().filtered(lambda t: t.company_id == rec.company_id)
                        rec.list_price_vat_usd = taxes.compute_all(rec.list_price_usd, product=rec)['total_included']
                        rec.list_price_vat = taxes.compute_all(rec.list_price, product=rec)['total_included']

    @api.onchange('standard_price_usd')
    def _onchange_standard_price_usd(self):
        for rec in self:
            if len(rec.product_variant_ids) == 1:
                rec.product_variant_ids[0].standard_price_usd = rec.standard_price_usd

            if rec.standard_price_usd and rec.categ_id.property_valuation == 'manual_periodic':
                if rec.standard_price_usd > 0:
                    if rec.company_id.currency_id.name == 'USD':
                        rec.standard_price = rec.standard_price_usd
                    else:
                        tasa = self.env.company.currency_id_dif
                        if tasa:
                            rec.standard_price = rec.standard_price_usd * tasa.inverse_rate


