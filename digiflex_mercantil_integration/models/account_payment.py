import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    bank_transaction_line_id = fields.Many2one(
        'bank.transaction.line', string='Transacción Bancaria API',
        ondelete='set null', copy=False
    )
    bank_integration_enabled = fields.Boolean(
        related='journal_id.bank_integration_enabled', string='Integración API Habilitada'
    )

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        for payment in self:
            if payment.bank_transaction_line_id:
                payment.bank_transaction_line_id.write({
                    'state': 'reconciled',
                    'payment_id': payment.id,
                })
            # 1. Conciliación contable automática de líneas de cuenta por cobrar/pagar con facturas del partner
            payment._auto_reconcile_with_partner_invoices()
            # 2. Conciliación bancaria automática en el Diario entre la línea del extracto bancario y el pago
            payment._auto_reconcile_bank_statement_line()
        return res

    def _auto_reconcile_with_partner_invoices(self):
        """Concilia automáticamente las líneas del asiento del pago con las facturas pendientes del cliente/proveedor."""
        for payment in self:
            if not payment.partner_id or payment.state != 'posted':
                continue

            pay_lines = payment.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable') and not l.reconciled
            )
            if not pay_lines:
                continue

            # 1. Si la factura de origen viene en el contexto
            invoice = False
            active_model = self.env.context.get('active_model')
            active_id = self.env.context.get('active_id')
            if active_model == 'account.move' and active_id:
                move = self.env['account.move'].browse(active_id)
                if move.exists() and move.move_type in ('out_invoice', 'in_invoice'):
                    invoice = move

            if invoice:
                inv_lines = invoice.line_ids.filtered(
                    lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable') and not l.reconciled
                )
                if inv_lines:
                    (pay_lines + inv_lines).reconcile()
                    continue

            # 2. Si no viene en el contexto, buscar facturas abiertas del mismo cliente/proveedor
            domain = [
                ('partner_id', '=', payment.partner_id.id),
                ('account_id', 'in', pay_lines.mapped('account_id').ids),
                ('reconciled', '=', False),
                ('move_id.state', '=', 'posted'),
                ('id', 'not in', pay_lines.ids),
            ]
            open_lines = self.env['account.move.line'].search(domain, order='date asc, id asc')
            if open_lines:
                (pay_lines + open_lines).reconcile()

    def _auto_reconcile_bank_statement_line(self):
        """Concilia automáticamente la línea del extracto bancario con el asiento del pago en el Diario Bancario."""
        for payment in self:
            if payment.state != 'posted' or not payment.bank_transaction_line_id:
                continue

            trx_line = payment.bank_transaction_line_id
            st_line = trx_line.statement_line_id
            if not st_line or st_line.is_reconciled:
                continue

            # Buscar la línea de cobros/pagos pendientes del asiento del pago (ej. 101403 Outstanding Receipts)
            pay_outstanding_line = payment.line_ids.filtered(
                lambda l: not l.reconciled and l.account_id.account_type not in ('asset_receivable', 'liability_payable')
            )
            if not pay_outstanding_line:
                continue

            # Buscar la línea del extracto bancario que corresponde a la cuenta de suspenso / contrapartida
            st_suspense_line = st_line.line_ids.filtered(
                lambda l: not l.reconciled and l.account_id != payment.journal_id.default_account_id
            )
            if not st_suspense_line:
                st_suspense_line = st_line.line_ids.filtered(lambda l: not l.reconciled)

            if st_suspense_line:
                try:
                    # Odoo 17: Ajustar la cuenta contable de la línea del extracto a la cuenta de cobros pendientes
                    target_account = pay_outstanding_line[0].account_id
                    st_suspense_line.sudo().write({'account_id': target_account.id})
                    
                    # Conciliar ambas líneas contables que ahora pertenecen a la misma cuenta
                    (st_suspense_line[0] + pay_outstanding_line[0]).reconcile()
                    _logger.info("Extracto bancario %s conciliado correctamente con pago %s en cuenta %s", st_line.name, payment.name, target_account.code)
                except Exception as e:
                    _logger.warning("Error al conciliar extracto bancario %s con pago %s: %s", st_line.name, payment.name, str(e))

    def action_open_bank_select_wizard(self):
        """Abre el wizard interactivo para consultar el banco y seleccionar el ingreso no conciliado."""
        self.ensure_one()
        return {
            'name': _('Consultar e Seleccionar Ingreso Bancario'),
            'type': 'ir.actions.act_window',
            'res_model': 'bank.transaction.select.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payment_id': self.id,
                'default_journal_id': self.journal_id.id if self.journal_id else False,
                'default_date_from': self.date or fields.Date.context_today(self),
                'default_date_to': self.date or fields.Date.context_today(self),
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'active_model': 'account.payment',
                'active_id': self.id,
            }
        }


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    bank_transaction_line_id = fields.Many2one(
        'bank.transaction.line', string='Transacción Bancaria API',
        ondelete='set null'
    )
    bank_integration_enabled = fields.Boolean(
        related='journal_id.bank_integration_enabled', string='Integración API Habilitada'
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard(batch_result)
        if self.bank_transaction_line_id:
            payment_vals['bank_transaction_line_id'] = self.bank_transaction_line_id.id
        return payment_vals

    def action_open_bank_select_wizard(self):
        """Abre el wizard de consulta bancaria desde el modal de Registro de Pago de Factura."""
        self.ensure_one()
        return {
            'name': _('Consultar e Seleccionar Ingreso Bancario'),
            'type': 'ir.actions.act_window',
            'res_model': 'bank.transaction.select.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_journal_id': self.journal_id.id if self.journal_id else False,
                'default_date_from': self.payment_date or fields.Date.context_today(self),
                'default_date_to': self.payment_date or fields.Date.context_today(self),
                'default_amount': self.amount,
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'active_model': 'account.payment.register',
                'active_id': self.id,
            }
        }
