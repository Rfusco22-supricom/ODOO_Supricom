from odoo import models, fields, api, _
from odoo.exceptions import UserError

class CurrencyExchangeMove(models.Model):
    _name = 'currency.exchange.move'
    _description = 'Currency Exchange / Money Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, default='Nuevo')
    date = fields.Date(string='Fecha', required=True, default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('posted', 'En Proceso'),
        ('done', 'Realizado'),
        ('cancel', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)

    # Origin
    journal_origin_id = fields.Many2one('account.journal', string='Diario Origen', required=True, domain=[('type', 'in', ('bank', 'cash'))])
    currency_origin_id = fields.Many2one('res.currency', related='journal_origin_id.currency_id', string='Moneda Origen', readonly=True)
    amount_origin = fields.Monetary(string='Monto a Enviar', required=True, currency_field='currency_origin_id')

    # Destination
    journal_dest_id = fields.Many2one('account.journal', string='Diario Destino', required=True, domain=[('type', 'in', ('bank', 'cash'))])
    currency_dest_id = fields.Many2one('res.currency', related='journal_dest_id.currency_id', string='Moneda Destino', readonly=True)
    amount_dest = fields.Monetary(string='Monto a Recibir', required=True, currency_field='currency_dest_id')

    # Accounting
    transfer_account_id = fields.Many2one('account.account', string='Cuenta Puente/Transitoria', required=True, 
                                          default=lambda self: self._get_default_transfer_account(),
                                          help="Cuenta usada para el transito de dinero.")
    profit_loss_account_id = fields.Many2one('account.account', string='Cuenta Diferencial', 
                                             default=lambda self: self._get_default_diff_account(),
                                             help="Cuenta para registrar Ganancia/Perdida por cambio.")
    
    move_ids = fields.One2many('account.move', 'currency_exchange_id', string='Asientos Contables')
    
    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)

    @api.model
    def _get_config(self):
        return self.env['currency.exchange.config'].search([('company_id', '=', self.env.company.id)], limit=1)

    @api.model
    def _get_default_transfer_account(self):
        return self._get_config().transfer_account_id

    @api.model
    def _get_default_diff_account(self):
        return self._get_config().profit_loss_account_id

    @api.model
    def create(self, vals):
        if vals.get('name', 'Nuevo') == 'Nuevo':
            vals['name'] = self.env['ir.sequence'].next_by_code('currency.exchange.move') or 'Nuevo'
        return super().create(vals)

    def _prepare_move_line_vals(self, label, account, debit, credit, amount_currency, currency):
        """
        Helper to prepare move line vals, respecting account currency restrictions.
        """
        self.ensure_one()
        
        # Determine target currency: Account > Line/Transaction > Company
        target_currency = account.currency_id or currency or self.company_id.currency_id
        
        # Calculate amount_currency if not provided matching the target currency
        final_amount_currency = 0.0
        
        # If we have a specific amount_currency passed and it matches the target currency (or target is company), use it?
        # But wait, if account has restriction, we MUST use that currency. 
        
        # Current logic passed:
        # amount_currency: The amount in 'currency' (transaction currency).
        # currency: The transaction currency.
        
        if account.currency_id:
            # Account is restricted. We must convert the Balance (Debit-Credit) to this currency.
            balance = debit - credit
            # Balance is in Company Currency. Convert Company -> Account
            final_amount_currency = self.company_id.currency_id._convert(
                balance, 
                account.currency_id, 
                self.company_id, 
                self.date
            )
            target_id = account.currency_id.id
        else:
            # Account is NOT restricted.
            target_id = target_currency.id
            if target_id == self.company_id.currency_id.id:
                 # If target is company currency, amount_currency is usually 0 unless we want to enforce it? 
                 # Standard Odoo: amount_currency is 0 if same as company.
                 # But we can set it equal to balance if we want. Let's stick to standard.
                 final_amount_currency = 0.0
                 # We previously enforced passing company id.
            else:
                 # Target is foreign. 
                 if currency and currency.id == target_id:
                     final_amount_currency = amount_currency
                 else:
                     # We have a currency/amount but target is different (shouldn't happen if logic is passed correctly, 
                     # but if we passed False/None for currency, we might need to convert).
                     balance = debit - credit
                     final_amount_currency = self.company_id.currency_id._convert(
                        balance, 
                        target_currency, 
                        self.company_id, 
                        self.date
                    )

        return {
            'name': label,
            'account_id': account.id,
            'debit': debit,
            'credit': credit,
            'amount_currency': final_amount_currency,
            'currency_id': target_id,
        }


    def action_send(self):
        self.ensure_one()
        if self.amount_origin <= 0:
            raise UserError(_("El monto a enviar debe ser positivo."))
        
        # Logic to determine currency on the line
        # If journal has a currency, we MUST use it.
        # If journal has no currency, use currency_origin_id if different from company currency.
        
        journal_curr = self.journal_origin_id.currency_id
        line_currency = journal_curr or (self.currency_origin_id if self.currency_origin_id != self.company_id.currency_id else False)
        
        # If we have a line currency, we must provide amount_currency
        # If line_currency is False (Company Currency implicit), amount_currency is 0.0 (usually)
        
        amount_currency_origin = 0.0
        if line_currency:
             amount_currency_origin = -self.amount_origin
        
        # Calculate balance in company currency
        balance = 0.0
        if self.currency_origin_id != self.company_id.currency_id:
             balance = self.currency_origin_id._convert(self.amount_origin, self.company_id.currency_id, self.company_id, self.date)
        else:
             balance = self.amount_origin

        # Create Origin Move: Credit Origin Journal (Outstanding Payment), Debit Transfer Account
        # Use journal's outstanding payment account if set, else default
        # Odoo 17: Accounts are in outbound_payment_method_line_ids
        origin_account_id = self.journal_origin_id.default_account_id.id
        for line in self.journal_origin_id.outbound_payment_method_line_ids:
            if line.payment_account_id:
                origin_account_id = line.payment_account_id.id
                break
        
        if not origin_account_id:
             raise UserError(_("No se encontró una cuenta de pagos salientes para el diario %s.") % self.journal_origin_id.name)
        
        move_vals = {
            'ref': self.name + ' - Send',
            'date': self.date,
            'journal_id': self.journal_origin_id.id,
            'currency_exchange_id': self.id,
            'line_ids': [
                (0, 0, self._prepare_move_line_vals(
                    _('Transferencia Saliente'),
                    self.env['account.account'].browse(origin_account_id),
                    0.0,
                    balance,
                    amount_currency_origin,
                    line_currency
                )),
                (0, 0, self._prepare_move_line_vals(
                    _('Dinero en Transito'),
                    self.transfer_account_id,
                    balance,
                    0.0,
                    -amount_currency_origin,
                    line_currency
                )),
            ]
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.write({'state': 'posted'})

    def action_receive(self):
        self.ensure_one()
        
        # Check permissions
        if self.journal_dest_id.inbound_transfer_auth_user_ids:
            if self.env.user not in self.journal_dest_id.inbound_transfer_auth_user_ids:
                raise UserError(_("No tienes permisos para recibir dinero en el diario %s.") % self.journal_dest_id.name)

        if self.amount_dest <= 0:
            raise UserError(_("El monto a recibir debe ser positivo."))
        
        # Determine currency to use on the line
        journal_curr = self.journal_dest_id.currency_id
        line_currency = journal_curr or (self.currency_dest_id if self.currency_dest_id != self.company_id.currency_id else False)
        
        # Calculate balance in company currency
        balance = 0.0
        if self.currency_dest_id != self.company_id.currency_id:
             balance = self.currency_dest_id._convert(self.amount_dest, self.company_id.currency_id, self.company_id, self.date)
        else:
             balance = self.amount_dest
        
        # Amount Currency
        amount_currency_dest = 0.0
        if line_currency:
             amount_currency_dest = self.amount_dest
             
        # Dest Account: Outstanding Receipt if set, else Default
        # Odoo 17: Accounts are in inbound_payment_method_line_ids
        dest_account_id = self.journal_dest_id.default_account_id.id
        for line in self.journal_dest_id.inbound_payment_method_line_ids:
            if line.payment_account_id:
                dest_account_id = line.payment_account_id.id
                break
        
        if not dest_account_id:
             raise UserError(_("No se encontró una cuenta de pagos entrantes para el diario %s.") % self.journal_dest_id.name)

        move_vals = {
            'ref': self.name + ' - Receive',
            'date': self.date,
            'journal_id': self.journal_dest_id.id,
            'currency_exchange_id': self.id,
            'line_ids': [
                (0, 0, self._prepare_move_line_vals(
                    _('Transferencia Entrante'),
                    self.transfer_account_id,
                    0.0,
                    balance,
                    -amount_currency_dest if line_currency else 0.0,
                    line_currency
                )),
                (0, 0, self._prepare_move_line_vals(
                    _('Dinero Recibido'),
                    self.env['account.account'].browse(dest_account_id),
                    balance,
                    0.0,
                    amount_currency_dest if line_currency else 0.0,
                    line_currency
                )),
            ]
        }

        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        self.create_exchange_diff_entry()
        self.write({'state': 'done'})

    def create_exchange_diff_entry(self):
        lines = self.move_ids.line_ids.filtered(lambda l: l.account_id == self.transfer_account_id)
        balance = sum(lines.mapped('balance')) # Debit - Credit
        
        if not self.company_id.currency_id.is_zero(balance):
            # If balance > 0 (Debit balance), we lost money/need to credit account to clear it. -> Expense
            # If balance < 0 (Credit balance), we gained money/need to debit account to clear it. -> Income (or expense reversal)
            
            if not self.profit_loss_account_id:
                  # If no account set, maybe warn? For now assume it's required if diff exists, 
                  # but user might surely want it.
                  raise UserError(_("Diferencial cambiario detectado ({}) pero no hay cuenta configurada.".format(balance)))

            diff_move_vals = {
                'ref': self.name + ' - Exchange Diff',
                'date': self.date,
                'journal_id': self._get_config().journal_id.id or self.journal_origin_id.id,
                'currency_exchange_id': self.id,
                'line_ids': []
            }
            
            if balance > 0:
                # Debit Balance exists. We need to Credit Transfer Acct, Debit Expense.
                # LOSS
                diff_move_vals['line_ids'] = [
                     (0, 0, self._prepare_move_line_vals(
                        _('Perdida Cambiaria'),
                        self.profit_loss_account_id,
                        balance,
                        0.0,
                        0.0, # Will be calc
                        False
                     )),
                     (0, 0, self._prepare_move_line_vals(
                        _('Limpiar Transito'),
                        self.transfer_account_id,
                        0.0,
                        balance,
                        0.0, # Will be calc
                        False
                     ))
                ]
            else:
                # Credit Balance exists (balance < 0). We need to Debit Transfer Acct, Credit Income.
                # GAIN
                diff_move_vals['line_ids'] = [
                     (0, 0, self._prepare_move_line_vals(
                        _('Ganancia Cambiaria'),
                        self.profit_loss_account_id,
                        0.0,
                        -balance,
                        0.0, # Will be calc
                        False
                     )),
                     (0, 0, self._prepare_move_line_vals(
                        _('Limpiar Transito'),
                        self.transfer_account_id,
                        -balance, # balance is neg, so -balance is pos
                        0.0,
                        0.0, # Will be calc
                        False
                     ))
                ]
            
            diff_move = self.env['account.move'].create(diff_move_vals)
            diff_move.action_post()

    def action_cancel(self):
        # self.move_ids.button_draft()
        # self.move_ids.button_cancel()
        # For simplicity, let's just allow cancel if drafts, else raise
        if any(m.state == 'posted' for m in self.move_ids):
             raise UserError(_("Por favor cancele los asientos contables relacionados primero."))
        self.write({'state': 'cancel'})

class AccountMove(models.Model):
    _inherit = 'account.move'
    
    currency_exchange_id = fields.Many2one('currency.exchange.move', string='Cambio de Divisas')

