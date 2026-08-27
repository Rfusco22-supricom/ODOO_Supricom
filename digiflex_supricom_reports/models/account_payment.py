# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    salesperson_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        compute='_compute_salesperson_id',
        store=True,
        readonly=False,
        index=True,
        help='Vendedor asociado al pago (proveniente de facturas reconciliadas o del cliente).',
    )

    @api.depends('partner_id', 'partner_id.user_id', 'reconciled_invoice_ids', 'reconciled_invoice_ids.invoice_user_id')
    def _compute_salesperson_id(self):
        for payment in self:
            salesperson = False
            # 1. Try to get salesperson from reconciled customer invoices
            if payment.reconciled_invoice_ids:
                invoices_with_user = payment.reconciled_invoice_ids.filtered(lambda inv: inv.invoice_user_id)
                if invoices_with_user:
                    salesperson = invoices_with_user[0].invoice_user_id

            # 2. Fallback to customer's assigned salesperson
            if not salesperson and payment.partner_id and payment.partner_id.user_id:
                salesperson = payment.partner_id.user_id

            # 3. Fallback to payment creator if nothing else found
            if not salesperson and payment.create_uid:
                salesperson = payment.create_uid

            payment.salesperson_id = salesperson
