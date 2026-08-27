# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    tax_today = fields.Float(string="Tasa Actual", digits=(16, 4))
    tax_invoice = fields.Float(string="Tasa Factura", digits=(16, 4))
    currency_id_dif = fields.Many2one("res.currency",string="Divisa de Referencia")
    currency_id_name = fields.Char(related="currency_id.name")
    
    is_ve_company = fields.Boolean(
        related='company_id.is_ve_company',
        string='Empresa Venezolana'
    )
    amount_residual_usd = fields.Monetary(currency_field='currency_id_dif',string='Adeudado Divisa Ref.', readonly=True)
    payment_difference_bs = fields.Monetary(string="Diferencia Bs", currency_field='source_currency_id')
    journal_id_dif = fields.Many2one('account.journal', 'Diario de diferencia', store=True,
                                 domain="[('company_id', '=', company_id)]")
    amount_usd = fields.Monetary(currency_field='currency_id_dif',string='Importe $', readonly=True)

    journal_igtf_id = fields.Many2one('account.journal', string='Diario IGTF', check_company=True)
    aplicar_igtf_divisa = fields.Boolean(string="Aplicar IGTF",
                                         default=lambda self: self._get_default_igtf())
    igtf_divisa_porcentage = fields.Float('% IGTF', related='company_id.igtf_divisa_porcentage')

    mount_igtf = fields.Monetary(currency_field='currency_id', string='Importe IGTF', readonly=True)

    amount_total_pagar = fields.Monetary(currency_field='currency_id', string="Total Pagar(Importe + IGTF):",
                                         readonly=True)
    tax_today_readonly = fields.Boolean(compute='_compute_tax_today_readonly', readonly=True)
    custom_rate = fields.Boolean(
        string='¿Usar Tasa de Cambio Personalizada?',
        tracking=2,
        default=False,
        groups='account_dual_currency.group_edit_trm'
    )

    @api.depends('custom_rate')
    def _compute_tax_today_readonly(self):
        for wizard in self:
            wizard.tax_today_readonly = not wizard.custom_rate

    @api.onchange('custom_rate', 'currency_id', 'company_id', 'payment_date')
    def _onchange_custom_rate(self):
        if not self.currency_id:
            return
        company_currency = self.company_currency_id or self.company_id.currency_id
        if self.currency_id == company_currency:
            self.tax_today = 1.0
            return
        if self.custom_rate:
            if not self.tax_today:
                self.tax_today = self._get_default_rate()
        else:
            self.tax_today = self._get_default_rate()

    @api.depends('currency_id')
    def _get_default_igtf(self):
        if self.currency_id == self.company_id.currency_id:
            return False
        else:
            return self.company_id.aplicar_igtf_divisa
    
    @api.onchange('aplicar_igtf_divisa','amount')
    def _mount_igtf(self):
        for wizard in self:
            if wizard.aplicar_igtf_divisa:
                if wizard.currency_id.name == 'USD':
                    # wizard.amount ya es el amount_total (Base Imponible + IVA)
                    wizard.mount_igtf = wizard.amount * wizard.igtf_divisa_porcentage / 100
                    wizard.amount_total_pagar = wizard.mount_igtf + wizard.amount
                else:
                    wizard.mount_igtf = 0
                    wizard.amount_total_pagar = wizard.amount
            else:
                wizard.mount_igtf = 0
                wizard.amount_total_pagar = wizard.amount


    @api.model
    def _get_wizard_values_from_batch(self, batch_result):
        ''' Extract values from the batch passed as parameter (see '_get_batches')
        to be mounted in the wizard view.
        :param batch_result:    A batch returned by '_get_batches'.
        :return:                A dictionary containing valid fields
        '''

        key_values = batch_result['payment_values']
        #print('Values: %s' % batch_result)
        lines = batch_result['lines']
        company = lines[0].company_id
        tax_invoice = lines[0].tax_today
        date = lines[0].move_id.date
        if not self.tax_today:
            tax_today = lines[0].company_id.currency_id_dif.inverse_rate
        else:
            tax_today = self.tax_today

        currency_id_dif = lines[0].currency_id_dif
        amount_residual_usd = lines[0].move_id.amount_residual_usd
        source_amount = abs(sum(lines.mapped('amount_residual'))) if key_values['currency_id'] == company.currency_id.id else abs(sum(lines.mapped('amount_residual_currency')))
        if key_values['currency_id'] == company.currency_id.id:
            source_amount_currency = source_amount
        else:
            source_amount_currency = abs(sum(lines.mapped('amount_residual_currency')))

        return {
            'company_id': company.id,
            'partner_id': key_values['partner_id'],
            'partner_type': key_values['partner_type'],
            'payment_type': key_values['payment_type'],
            'source_currency_id': key_values['currency_id'],
            'source_amount': source_amount,
            'source_amount_currency': source_amount_currency,
            # 'tax_today': tax_today,
            'tax_invoice': tax_invoice,
            'currency_id_dif': currency_id_dif.id,
            'amount_residual_usd': amount_residual_usd,
            'aplicar_igtf_divisa': self.aplicar_igtf_divisa,
            #'payment_date': date,
        }

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        tax_today = self.tax_today if self.custom_rate else self._get_default_rate()
        payment_vals.update({
            'tax_today': tax_today,
            'currency_id_dif': self.currency_id_dif.id,
            'aplicar_igtf_divisa': self.aplicar_igtf_divisa,
            'journal_igtf_id': self.journal_igtf_id.id,
            'mount_igtf': self.mount_igtf,
            'amount_total_pagar': self.amount_total_pagar,
            'custom_rate': self.custom_rate
        })

        return payment_vals


    def _create_payments(self):
        payments = super(AccountPaymentRegister, self)._create_payments()
        for payment in payments:
            if self.custom_rate:
                payment.tax_today = self.tax_today
            payment.custom_rate = self.custom_rate
        return payments

    @api.constrains('communication', 'journal_id')
    def _check_communication_uniqueness(self):
        for wizard in self:
            if wizard.communication and wizard.journal_id.type == 'bank':
                # Búsqueda usando sudo() para asegurar que encontramos duplicados incluso si el usuario no tiene acceso a ellos
                duplicate_payment = self.env['account.payment'].sudo().search([
                    ('ref', '=', wizard.communication),
                    ('journal_id', '=', wizard.journal_id.id),
                    ('state', '!=', 'cancel'),
                    ('company_id', '=', wizard.company_id.id),
                ], limit=1)
                if duplicate_payment:
                    raise ValidationError(_(
                        "La referencia bancaria '%s' ya ha sido registrada en el diario '%s'. "
                        "Existe un pago previo con esta referencia: %s."
                    ) % (wizard.communication, wizard.journal_id.name, duplicate_payment.name))

    @api.constrains('custom_rate', 'tax_today')
    def _check_custom_rate(self):
        for wizard in self:
            if wizard.custom_rate and float_compare(wizard.tax_today, 0.0, precision_digits=6) <= 0:
                raise ValidationError(_('La tasa manual debe ser mayor a cero.'))

    def _get_default_rate(self):
        company_currency = self.company_currency_id or self.company_id.currency_id
        if not self.currency_id or self.currency_id == company_currency:
            return 1.0
        date = self.payment_date or fields.Date.context_today(self)
        return self.currency_id._get_conversion_rate(
            self.currency_id,
            company_currency,
            self.company_id,
            date,
        )

        

        

    @api.model
    def default_get(self, fields_list):
        # OVERRIDE
        #print(fields_list)
        #if 'line_ids' in fields_list:
        #    fields_list.remove("line_ids")
        if 'line_ids' in fields_list:
            fields_list.remove("line_ids")
        res = super().default_get(fields_list)
        fields_list.append("line_ids")
        if 'line_ids' in fields_list and 'line_ids' not in res:

            # Retrieve moves to pay from the context.

            if self._context.get('active_model') == 'account.move':
                lines = self.env['account.move'].browse(self._context.get('active_ids', [])).line_ids
            elif self._context.get('active_model') == 'account.move.line':
                lines = self.env['account.move.line'].browse(self._context.get('active_ids', []))
            else:
                raise UserError(_(
                    "The register payment wizard should only be called on account.move or account.move.line records."
                ))

            # Keep lines having a residual amount to pay.
            available_lines = self.env['account.move.line']
            for line in lines:
                if line.move_id.state != 'posted':
                    raise UserError(_("You can only register payment for posted journal entries."))

                if line.account_type not in ('asset_receivable', 'liability_payable'):
                    continue
                if line.currency_id:
                    if line.move_id.amount_residual_usd == 0.0:
                        continue
                else:
                    if line.company_currency_id.is_zero(line.amount_residual) and line.move_id.amount_residual_usd == 0.0:
                        continue
                available_lines |= line

            # Check.
            if len(lines.company_id) > 1:
                raise UserError(_("You can't create payments for entries belonging to different companies."))
            if len(set(available_lines.mapped('account_type'))) > 1:
                raise UserError(
                    _("You can't register payments for journal items being either all inbound, either all outbound."))

            res['line_ids'] = [(6, 0, available_lines.ids)]

        moves = self.env['account.move']
        if self._context.get('active_model') == 'account.move':
            moves = self.env['account.move'].browse(self._context.get('active_ids', []))
        elif self._context.get('active_model') == 'account.move.line':
            moves = self.env['account.move.line'].browse(self._context.get('active_ids', [])).mapped('move_id')
        if moves and all(move.edit_trm for move in moves):
            rates = moves.mapped('tax_today')
            unique_rates = set(rates)
            if len(unique_rates) == 1:
                res.setdefault('custom_rate', True)
                if 'tax_today' not in res:
                    res['tax_today'] = unique_rates.pop()

        return res

    