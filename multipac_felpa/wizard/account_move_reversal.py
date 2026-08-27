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

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def _prepare_default_reversal(self, move):
        reverse_date = self.date
        mixed_payment_term = move.invoice_payment_term_id.id if move.invoice_payment_term_id.early_pay_discount_computation == 'mixed' else None
        fel_pa_document_type_id = self.env['fel_pa.tools.document_type'].search([('journal_id', '=', self.journal_id.id), ('document_type', '=', '04'), ('active', '=', True)], limit=1)

        return {
            'ref': _('Reversal of: %(move_name)s, %(reason)s', move_name=move.name, reason=self.reason)
                   if self.reason
                   else _('Reversal of: %s', move.name),
            'date': reverse_date,
            'invoice_date_due': reverse_date,
            'invoice_date': move.is_invoice(include_receipts=True) and (self.date or move.date) or False,
            'journal_id': self.journal_id.id,
            'invoice_payment_term_id': mixed_payment_term,
            'invoice_user_id': move.invoice_user_id.id,
            'auto_post': 'at_date' if reverse_date > fields.Date.context_today(self) else 'no',
            'fel_pa_document_references_ids': [(6, 0, [move.id])],
            'fel_pa_document_type_id': fel_pa_document_type_id.id,
        }

    def reverse_moves(self, is_modify=False):
        """Link return moves to the lines of refund invoice"""
        action = super(
            AccountMoveReversal, self.with_context(force_copy_stock_moves=True)
        ).reverse_moves()
        if "res_id" in action:
            moves = self.env["account.move"].browse(action["res_id"])
        else:
            moves = self.env["account.move"].search(action["domain"])
        if is_modify:
            origin_moves = self.move_ids
            for line in origin_moves.mapped("invoice_line_ids"):
                reverse_moves = line.move_line_ids.mapped("returned_move_ids")
                if reverse_moves:
                    moves.mapped("invoice_line_ids").filtered(
                        lambda m, line=line: m.product_id == line.product_id
                    ).move_line_ids = reverse_moves
        else:
            for line in moves.mapped("invoice_line_ids"):
                reverse_moves = line.move_line_ids.mapped("returned_move_ids")
                if reverse_moves:
                    line.move_line_ids = reverse_moves
        return action

