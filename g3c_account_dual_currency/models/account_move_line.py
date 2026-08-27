# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, Command

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    # def reconcile(self):
    #     ''' Reconcile the current move lines all together.
    #     :return: A dictionary representing a summary of what has been done during the reconciliation:
    #             * partials:             A recorset of all account.partial.reconcile created during the reconciliation.
    #             * exchange_partials:    A recorset of all account.partial.reconcile created during the reconciliation
    #                                     with the exchange difference journal entries.
    #             * full_reconcile:       An account.full.reconcile record created when there is nothing left to reconcile
    #                                     in the involved lines.
    #             * tax_cash_basis_moves: An account.move recordset representing the tax cash basis journal entries.
    #     '''
    #     not_paid_invoices = self.move_id.filtered(lambda move:
    #                                               move.is_invoice(include_receipts=True)
    #                                               and move.payment_state not in ('paid', 'in_payment')
    #                                               )
    #     results = super(AccountMoveLine, self).reconcile()
    #     if not 'partials' in results:
    #         return results
    #     for parcial in results['partials']:

    #         amount_usd = min(abs(parcial.debit_move_id.amount_residual_usd), abs(parcial.credit_move_id.amount_residual_usd))
    #         parcial.write({'amount_usd': abs(amount_usd)})
    #         self.env.cr.commit()
    #         # parcial.debit_move_id._compute_amount_residual_usd()
    #         # parcial.credit_move_id._compute_amount_residual_usd()
    #         # self.env.cr.commit()


    #     return results