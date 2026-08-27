from odoo import models, api

class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    @api.model
    def create(self, vals):
        # Create the partial reconciliation first
        partial = super(AccountPartialReconcile, self).create(vals)
        
        # Check if this reconciliation involves an Overdue Invoice with Manual Commission Override
        # We need to identify the Invoice side and the Payment side.
        
        # Partial connects Debit Move Line and Credit Move Line.
        # One is Invoice, One is Payment (usually).
        
        lines = [partial.debit_move_id, partial.credit_move_id]
        invoice = False
        payment = False
        
        for line in lines:
            if line.move_id.move_type == 'out_invoice':
                invoice = line.move_id
            if line.payment_id: # Direct link if payment created line
                # Or via move
                payment = self.env['account.payment'].search([('move_id', '=', line.move_id.id)], limit=1)
                if not payment and line.move_id.payment_id:
                     payment = line.move_id.payment_id
        
        # Logic: If we found an invoice and it has manual_commission_override = True
        if invoice and invoice.manual_commission_override and payment:
             # Check if it WAS overdue.
             # If manual_commission_override is True, it implies it was authorized because it was overdue.
             # We should log this new payment event.
             
             # Call the helper on the invoice model
             invoice._log_commission_exception(payment, invoice)
             
        return partial
