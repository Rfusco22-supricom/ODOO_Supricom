from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BankTransactionLine(models.Model):
    _name = 'bank.transaction.line'
    _description = 'Línea de Transacción Bancaria API'
    _order = 'trx_date desc, id desc'

    integration_account_id = fields.Many2one(
        'bank.integration.account', string='Cuenta de Integración', required=True, ondelete='cascade'
    )
    journal_id = fields.Many2one(
        'account.journal', string='Diario Bancario', required=True,
        domain="[('type', '=', 'bank')]"
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        related='integration_account_id.company_id', store=True
    )
    trx_date = fields.Date(string='Fecha de Transacción', required=True, default=fields.Date.context_today)
    payment_reference = fields.Char(string='Referencia Bancaria', required=True, index=True)
    amount = fields.Monetary(string='Monto', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.company.currency_id
    )

    payment_type = fields.Selection([
        ('transfer', 'Transferencia Bancaria'),
        ('c2p', 'Pago Móvil C2P'),
        ('other', 'Otro Movimiento'),
    ], string='Tipo de Pago', default='transfer', required=True)

    origin_account = fields.Char(string='Cuenta Emisora')
    origin_phone = fields.Char(string='Teléfono Emisor')
    origin_customer_id = fields.Char(string='RIF / CI Emisor')

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('reconciled', 'Conciliado'),
        ('ignored', 'Ignorado'),
    ], string='Estado', default='pending', required=True, index=True)

    payment_id = fields.Many2one('account.payment', string='Pago en Odoo', ondelete='set null')
    statement_line_id = fields.Many2one('account.bank.statement.line', string='Línea de Extracto Bancario', ondelete='set null')
    statement_id = fields.Many2one('account.bank.statement', string='Extracto Bancario', related='statement_line_id.statement_id', store=True)
    raw_payload = fields.Text(string='Respuesta JSON Bruta')

    def action_mark_ignored(self):
        self.write({'state': 'ignored'})

    def action_mark_pending(self):
        self.write({'state': 'pending'})

    def _find_matching_partner(self):
        """Busca un cliente (res.partner) coincidente por contexto de factura/pago o RIF/CI o teléfono."""
        self.ensure_one()
        # 1. Extraer partner_id directo del contexto
        ctx_partner_id = self.env.context.get('default_partner_id') or self.env.context.get('partner_id')
        if ctx_partner_id:
            partner = self.env['res.partner'].browse(ctx_partner_id)
            if partner.exists():
                return partner

        # 2. Extraer de la factura activa (account.move)
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        if active_model == 'account.move' and active_id:
            move = self.env['account.move'].browse(active_id)
            if move.exists() and move.partner_id:
                return move.partner_id

        # 3. Extraer del registro de pago activo (account.payment.register)
        if active_model == 'account.payment.register' and active_id:
            pay_reg = self.env['account.payment.register'].browse(active_id)
            if pay_reg.exists() and pay_reg.partner_id:
                return pay_reg.partner_id

        # 4. Fallback: buscar por RIF/CI o teléfono
        partner = False
        if self.origin_customer_id:
            clean_vat = self.origin_customer_id.strip()
            partner = self.env['res.partner'].search([
                '|', ('vat', '=ilike', clean_vat), ('vat', '=ilike', f"%{clean_vat}%")
            ], limit=1)
        if not partner and self.origin_phone:
            clean_phone = self.origin_phone.strip()
            partner = self.env['res.partner'].search([
                '|', ('phone', '=', clean_phone), ('mobile', '=', clean_phone)
            ], limit=1)
        return partner

    def action_create_payment(self):
        """Abre la vista de creación de pago pre-completando los datos de esta transacción y el Cliente de la factura."""
        self.ensure_one()
        if self.state == 'reconciled' and self.payment_id:
            raise UserError(_("Esta transacción ya se encuentra conciliada con el pago %s.") % self.payment_id.name)

        partner = self._find_matching_partner()

        return {
            'name': _('Registrar Pago desde Banco'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_payment_type': 'inbound',
                'default_partner_type': 'customer',
                'default_partner_id': partner.id if partner else False,
                'default_journal_id': self.journal_id.id,
                'default_amount': self.amount,
                'default_date': self.trx_date,
                'default_ref': f"Mercantil Ref: {self.payment_reference}",
                'default_bank_transaction_line_id': self.id,
            }
        }
