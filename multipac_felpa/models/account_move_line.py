# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import api, fields, models, _
from collections import defaultdict

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Compatibility fields for other modules
    commission_amount = fields.Float(string='Commission Amount', help='Compatibility field')
    commission_base = fields.Float(string='Commission Base', help='Compatibility field')
    commission_final_amount = fields.Float(string='Commission Final Amount', help='Compatibility field')
    deduction_percentage = fields.Float(string='Deduction Percentage', help='Compatibility field')
    product_cost = fields.Float(string='Product Cost', help='Compatibility field')
    
    # Venezuelan dual currency fields
    amount_residual_usd = fields.Float(string='Residual Amount USD', help='Compatibility field')
    balance_usd = fields.Float(string='Balance USD', help='Compatibility field')
    credit_usd = fields.Float(string='Credit USD', help='Compatibility field')
    debit_usd = fields.Float(string='Debit USD', help='Compatibility field')
    tax_today = fields.Float(string='Tax Today', help='Compatibility field')
    
    # Other custom fields
    discount_amount_currency = fields.Float(string='Discount Amount Currency', help='Compatibility field')
    discount_date = fields.Date(string='Discount Date', help='Compatibility field')

    move_line_ids = fields.Many2many(
        comodel_name="stock.move",
        relation="stock_move_invoice_line_rel",
        column1="invoice_line_id",
        column2="move_id",
        string="Related Stock Moves",
        readonly=True,
        copy=False,
        help="Related stock moves (only when the invoice has been"
        " generated from a sale order).",
    )

    def copy_data(self, default=None):
        """Copy the move_line_ids in case of refund invoice creating a new invoice
        (refund_method="modify").
        """
        self.ensure_one()
        res = super().copy_data(default=default)
        if (
            self.env.context.get("force_copy_stock_moves")
            and "move_line_ids" not in res
        ):
            res[0]["move_line_ids"] = [(6, 0, self.move_line_ids.ids)]
        return res


    def lots_grouped_by_quantity(self):
        lot_dict = defaultdict(float)
        for sml in self.mapped("move_line_ids.move_line_ids"):
            if sml.lot_id:
                lot_dict[sml.lot_id.name] += sml.qty_done
        return lot_dict

    @api.depends('product_id', 'move_id.partner_id', 'move_id.company_id')
    def _compute_tax_ids(self):
        # Dejar que la lógica nativa calcule los impuestos (usará `fiscal_position_id` si está asignada)
        super(AccountMoveLine, self)._compute_tax_ids()

    @api.onchange('product_id')
    def _onchange_product_id_pa_foreign(self):
        """Fuerza el impuesto exento al cambiar el producto en UI para clientes extranjeros en Panamá."""
        # Dejar que la vista / onchange nativo maneje la asignación de impuestos.
        return
