# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    qty_available_storage = fields.Float(
        string='Stock en Ubicación',
        compute='_compute_qty_available_storage',
        digits='Product Unit of Measure',
    )
    is_global_stock_hidden = fields.Boolean(
        string='Ocultar Stock Global',
        compute='_compute_is_global_stock_hidden',
    )

    def _compute_is_global_stock_hidden(self):
        has_group = self.env.user.has_group('digiflex_widget_stock_by_storage.group_hide_global_stock')
        for record in self:
            record.is_global_stock_hidden = has_group

    def _compute_qty_available_storage(self):
        company = self.env.company
        location = company.storage_location_id or self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1
        ).lot_stock_id

        if not location:
            for product in self:
                product.qty_available_storage = 0.0
            return

        quants = self.env['stock.quant']._read_group(
            domain=[
                ('product_id', 'in', self.ids),
                ('location_id', 'child_of', location.id),
            ],
            groupby=['product_id'],
            aggregates=['quantity:sum'],
        )
        res = {product.id: (qty or 0.0) for product, qty in quants}
        for product in self:
            product.qty_available_storage = res.get(product.id, 0.0)

    def action_open_storage_location_quants(self):
        self.ensure_one()
        company = self.env.company
        location = company.storage_location_id or self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1
        ).lot_stock_id

        action = self.env['ir.actions.actions']._for_xml_id('stock.location_open_quants')
        domain = [('product_id', '=', self.id)]
        if location:
            domain.append(('location_id', 'child_of', location.id))
        action['domain'] = domain
        action['context'] = {
            'default_product_id': self.id,
            'default_location_id': location.id if location else False,
            'single_product': True,
        }
        return action
