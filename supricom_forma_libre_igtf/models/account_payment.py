from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    debit_note_igtf_id = fields.Many2one(
        'account.move',
        'Nota de Débito IGTF',
        readonly=True,
        help="Nota de débito generada automáticamente por el IGTF aplicado al pago"
    )

    igtf_invoice_ids = fields.Many2many(
        'account.move',
        string="Facturas Origen IGTF",
        help="Facturas que originan este pago y la nota de débito por IGTF"
    )
    
    @api.depends('currency_id_dif', 'currency_id', 'amount', 'tax_today', 'igtf_invoice_ids')
    def _currency_equal(self):
        super()._currency_equal()
        for rec in self:
            if not rec.company_id.supricom_fl_igtf_enabled:
                continue

            is_venezuela = rec.partner_id.country_id and rec.partner_id.country_id.code == 'VE'
            if rec.aplicar_igtf_divisa and rec.currency_id.name == 'USD' and is_venezuela:
                igtf_base = rec.amount
                
                rec.mount_igtf = rec.currency_id.round(igtf_base * rec.igtf_divisa_porcentage / 100)
                rec.amount_total_pagar = igtf_base + rec.mount_igtf
            else:
                rec.mount_igtf = 0
                rec.amount_total_pagar = rec.amount

    def register_move_igtf_divisa_payment(self):
        res = super(AccountPayment, self).register_move_igtf_divisa_payment()
        for payment in self:
            is_venezuela = payment.partner_id.country_id and payment.partner_id.country_id.code == 'VE'
            if payment.company_id.supricom_fl_igtf_enabled and payment.move_id_igtf_divisa and is_venezuela:
                payment.move_id_igtf_divisa.button_draft()
                account_igtf_bridge = payment.company_id.account_debit_wh_igtf_id if payment.payment_type == 'inbound' else payment.company_id.account_credit_wh_igtf_id
                if account_igtf_bridge:
                    line_to_modify = payment.move_id_igtf_divisa.line_ids.filtered(lambda l: l.account_id == account_igtf_bridge)
                    if line_to_modify and payment.partner_id:
                        new_account = payment.partner_id.property_account_receivable_id if payment.payment_type == 'inbound' else payment.partner_id.property_account_payable_id
                        if new_account:
                            line_to_modify.with_context(check_move_validity=False).write({'account_id': new_account.id})
                payment.move_id_igtf_divisa.action_post()
        return res

    def action_post(self):
        for payment in self:
            is_venezuela = payment.partner_id.country_id and payment.partner_id.country_id.code == 'VE'
            if payment.company_id.supricom_fl_igtf_enabled and payment.aplicar_igtf_divisa and payment.currency_id.name == 'USD' and is_venezuela:
                igtf_base = payment.amount
                
                payment.mount_igtf = payment.currency_id.round(igtf_base * payment.igtf_divisa_porcentage / 100)

        res = super(AccountPayment, self).action_post()
        
        for payment in self:
            is_venezuela = payment.partner_id.country_id and payment.partner_id.country_id.code == 'VE'
            if payment.company_id.supricom_fl_igtf_enabled and payment.payment_type in ('inbound', 'outbound') and payment.aplicar_igtf_divisa and payment.mount_igtf > 0 and is_venezuela:
                if not payment.debit_note_igtf_id:
                    try:
                        payment._create_igtf_debit_note()
                    except Exception as e:
                        raise UserError(_("Error al crear la Nota de Débito por IGTF: %s") % str(e))
                
                if payment.move_id_igtf_divisa and payment.debit_note_igtf_id:
                    # Cambiar la cuenta IGTF del asiento a la cuenta por cobrar/pagar del partner
                    # para que sea conciliable con la nota de débito
                    account_igtf_bridge = payment.company_id.account_debit_wh_igtf_id if payment.payment_type == 'inbound' else payment.company_id.account_credit_wh_igtf_id
                    if account_igtf_bridge:
                        payment.move_id_igtf_divisa.button_draft()
                        line_to_modify = payment.move_id_igtf_divisa.line_ids.filtered(lambda l: l.account_id == account_igtf_bridge)
                        if line_to_modify and payment.partner_id:
                            new_account = payment.partner_id.property_account_receivable_id if payment.payment_type == 'inbound' else payment.partner_id.property_account_payable_id
                            if new_account:
                                line_to_modify.with_context(check_move_validity=False).write({'account_id': new_account.id})
                        payment.move_id_igtf_divisa.action_post()

                    account_type = 'asset_receivable' if payment.payment_type == 'inbound' else 'liability_payable'
                    
                    move_line_payment = payment.move_id_igtf_divisa.line_ids.filtered(lambda l: l.account_id.account_type == account_type)
                    move_line_invoice = payment.debit_note_igtf_id.line_ids.filtered(lambda l: l.account_id.account_type == account_type)
                    
                    if move_line_payment and move_line_invoice:
                        lines_to_reconcile = move_line_payment + move_line_invoice
                        if not lines_to_reconcile.filtered(lambda l: l.reconciled):
                            lines_to_reconcile.reconcile()
        
        return res
    
    def action_cancel(self):
        for payment in self:
            if payment.company_id.supricom_fl_igtf_enabled and payment.debit_note_igtf_id and payment.debit_note_igtf_id.state == 'posted':
                payment.debit_note_igtf_id.button_cancel()
        
        return super(AccountPayment, self).action_cancel()
    
    def action_draft(self):
        for payment in self:
            if payment.company_id.supricom_fl_igtf_enabled and payment.debit_note_igtf_id and payment.debit_note_igtf_id.state == 'cancel':
                payment.debit_note_igtf_id.button_draft()
        
        return super(AccountPayment, self).action_draft()
    
    def _create_igtf_debit_note(self):
        self.ensure_one()
        
        expected_move_type = 'out_invoice' if self.payment_type == 'inbound' else 'in_invoice'
        
        reconciled_invoices = self.igtf_invoice_ids.filtered(
            lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
        )
        
        if not reconciled_invoices:
            reconciled_invoices = self.reconciled_invoice_ids.filtered(
                lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
            )
        
        if not reconciled_invoices:
            reconciled_invoices = self.move_id.line_ids.matched_debit_ids.debit_move_id.move_id.filtered(
                lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
            ) | self.move_id.line_ids.matched_credit_ids.credit_move_id.move_id.filtered(
                lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
            )
        
        if not reconciled_invoices:
            return
        
        origin_invoice = reconciled_invoices[0]
        
        igtf_product = self.company_id.igtf_product_id
        if not igtf_product:
            raise UserError(_(
                "Error al generar Nota de Débito por IGTF:\n\n"
                "No se ha configurado el producto para Recargo IGTF.\n"
                "Por favor, configure el producto en: Configuración > Contabilidad > Producto IGTF"
            ))
        
        invoice_names = ", ".join(reconciled_invoices.mapped('name'))
        line_description = f"Recargo IGTF - {invoice_names}" if len(reconciled_invoices) > 1 else f"Recargo IGTF - {origin_invoice.name}"

        journal_type_domain = 'sale' if self.payment_type == 'inbound' else 'purchase'
        igtf_journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('is_igtf_debit_note', '=', True),
            ('type', '=', journal_type_domain)
        ], limit=1)
        
        journal = igtf_journal or origin_invoice.journal_id

        debit_note_vals = {
            'move_type': expected_move_type,
            'partner_id': self.partner_id.id,
            'journal_id': journal.id,
            'invoice_date': self.date,
            'date': self.date,
            'currency_id': self.currency_id.id,
            'tax_today': self.tax_today,
            'edit_trm': self.custom_rate,
            'debit_origin_id': origin_invoice.id,
            'ref': f"ND IGTF - Pago {self.name}",
            'invoice_line_ids': [(0, 0, {
                'product_id': igtf_product.id,
                'name': line_description,
                'quantity': 1,
                'price_unit': self.mount_igtf,
                'tax_ids': [(6, 0, [])],
            })],
        }
        
        debit_note = self.env['account.move'].create(debit_note_vals)
        self.write({'debit_note_igtf_id': debit_note.id})
        debit_note.action_post()
        
        return debit_note
