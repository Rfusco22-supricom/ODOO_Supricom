# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    active_company_taxes_id = fields.Many2many(
        'account.tax',
        string='Customer Taxes (Visually Filtered)',
        compute='_compute_active_company_taxes',
        inverse='_inverse_active_company_taxes',
        help='Default taxes used when selling the product. Showing only active company taxes.'
    )

    active_company_supplier_taxes_id = fields.Many2many(
        'account.tax',
        string='Vendor Taxes (Visually Filtered)',
        compute='_compute_active_company_supplier_taxes',
        inverse='_inverse_active_company_supplier_taxes',
        help='Default taxes used when buying the product. Showing only active company taxes.'
    )

    @api.depends('taxes_id', 'taxes_id.company_id')
    @api.depends_context('company')
    def _compute_active_company_taxes(self):
        for product in self:
            company_id = self.env.company.id
            product.active_company_taxes_id = product.taxes_id.filtered(
                lambda t: not t.company_id or t.company_id.id == company_id
            )

    def _inverse_active_company_taxes(self):
        for product in self:
            company_id = self.env.company.id
            # Get taxes that belong to OTHER companies (which should be preserved)
            other_companies_taxes = product.taxes_id.filtered(
                lambda t: t.company_id and t.company_id.id != company_id
            )
            # Combine the preserved taxes with the new explicitly set taxes
            product.taxes_id = other_companies_taxes | product.active_company_taxes_id

    @api.depends('supplier_taxes_id', 'supplier_taxes_id.company_id')
    @api.depends_context('company')
    def _compute_active_company_supplier_taxes(self):
        for product in self:
            company_id = self.env.company.id
            product.active_company_supplier_taxes_id = product.supplier_taxes_id.filtered(
                lambda t: not t.company_id or t.company_id.id == company_id
            )

    def _inverse_active_company_supplier_taxes(self):
        for product in self:
            company_id = self.env.company.id
            # Get taxes that belong to OTHER companies (which should be preserved)
            other_companies_taxes = product.supplier_taxes_id.filtered(
                lambda t: t.company_id and t.company_id.id != company_id
            )
            # Combine the preserved taxes with the new explicitly set taxes
            product.supplier_taxes_id = other_companies_taxes | product.active_company_supplier_taxes_id
