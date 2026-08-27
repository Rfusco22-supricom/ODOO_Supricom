# -*- coding: utf-8 -*-

from itertools import groupby
from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.exceptions import UserError



class PurchaseOrderLineAccount(models.Model):
    _inherit = 'purchase.order.line'

    def _prepare_account_move_line(self, move=False):
        res = {}
        amount = self.price_unit * self.qty_to_invoice
        currency = self.currency_id
        company_currency = self.company_id.currency_id
            
        # Selección de cuenta según método contable
        if self.company_id.anglo_saxon_accounting:
                account = (
                    self.product_id.property_account_expense_id or
                    self.product_id.categ_id.property_stock_account_input_categ_id
            )
        else:
            account = (
                self.product_id.property_account_expense_id or
                self.product_id.categ_id.property_account_expense_categ_id
            )

        if not account:
            raise UserError(_(
                "Debe configurar una cuenta contable adecuada en el producto '%s' o su categoría, "
                "según el método contable de la compañía."
            ) % self.product_id.display_name)

        res.update({
            'balance': currency._convert(
                from_amount=amount,
                to_currency=company_currency,
                company=self.company_id,
                date=self.order_id.date_order or fields.Date.context_today(self),
                round=True
            ),
            'amount_currency': amount,
            'quantity': self.qty_to_invoice,
            'name': self.name or '/',
            'product_id': self.product_id.id,
            'account_id': account.id,
            'purchase_line_id': self.id,
            'price_unit': self.price_unit,

        })

        return res