"""Account payment dual currency extensions."""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    sent_to_bank = fields.Boolean(
        string='Enviado a Banco (Compat)',
        help="Campo heredado por compatibilidad con versiones anteriores o módulos personalizados."
    )

    tax_today = fields.Float(
        string="Tasa",
        default=lambda self: self._compute_default_rate(),
        digits=(16, 4),
        help="Tasa de cambio aplicada al pago."
    )
    currency_id_dif = fields.Many2one(
        "res.currency",
        string="Divisa de Referencia",
        default=lambda self: self.env.company.currency_id_dif,
    )
    currency_id_company = fields.Many2one(
        "res.currency",
        string="Divisa compañia",
        default=lambda self: self.env.company.currency_id,
    )
    amount_local = fields.Monetary(string="Importe local", currency_field='currency_id_company')
    amount_ref = fields.Monetary(string="Importe referencia", currency_field='currency_id_dif')
    currency_equal = fields.Boolean(compute="_currency_equal")
    move_id_dif = fields.Many2one(
        'account.move',
        'Asiento contable diferencia',
        readonly=True,
        help="Asiento contable de diferencia en tipo de cambio",
    )

    currency_id_name = fields.Char(related="currency_id.name")
    journal_igtf_id = fields.Many2one('account.journal', string='Diario IGTF', check_company=True)
    aplicar_igtf_divisa = fields.Boolean(string="Aplicar IGTF")
    igtf_divisa_porcentage = fields.Float('% IGTF', related='company_id.igtf_divisa_porcentage')

    mount_igtf = fields.Monetary(currency_field='currency_id', string='Importe IGTF', readonly=True)

    amount_total_pagar = fields.Monetary(currency_field='currency_id', string="Total Pagar(Importe + IGTF):",
                                         readonly=True)

    move_id_igtf_divisa = fields.Many2one(
        'account.move', 'Asiento IGTF Divisa',
        readonly=True)

    tax_today_readonly = fields.Boolean(compute="_compute_tax_today_readonly")

    custom_rate = fields.Boolean(
        string='¿Usar Tasa de Cambio Personalizada?',
        tracking=2,
        default=False,
        help='Permite definir manualmente la tasa de cambio aplicada al pago.'
    )

    @api.depends('custom_rate', 'state')
    def _compute_tax_today_readonly(self):
        for payment in self:
            payment.tax_today_readonly = payment.state != 'draft' or not payment.custom_rate
            
    @api.constrains('custom_rate', 'tax_today')
    def _check_manual_rate(self):
        for payment in self:
            if payment.custom_rate and float_compare(payment.tax_today, 0.0, precision_digits=6) <= 0:
                raise ValidationError(_('La tasa manual debe ser mayor a cero.'))

    def _compute_default_rate(self):
        payment = self[:1]
        company = payment.company_id or self.env.company
        date = payment.date or fields.Date.context_today(payment)
        
        rate = company.currency_id._get_conversion_rate(
            company.currency_id,
            company.currency_id_dif,
            company,
            date,
        )

        if company.currency_id_dif == self.env.ref('base.USD'):
            return 1 / rate if rate else 1

    def _ensure_manual_currency_rate(self):
        """Create a currency rate record matching the manual rate if missing."""
        rate_model = self.env['res.currency.rate'].sudo()
        for payment in self:
            if not payment.custom_rate:
                continue
            currency = payment.currency_id_dif
            company = payment.company_id
            company_currency = payment.company_currency_id or company.currency_id
            if not currency or currency == company_currency:
                continue
            if not payment.tax_today:
                continue
            rate_date = payment.date or fields.Date.context_today(payment)
            company_root = company.root_id or company
            existing_rate = rate_model.search([
                ('currency_id', '=', currency.id),
                ('company_id', '=', company_root.id),
                ('name', '=', rate_date),
            ], limit=1)
            if existing_rate:
                continue
            rate_model.create({
                'currency_id': currency.id,
                'company_id': company_root.id,
                'name': rate_date,
                'inverse_company_rate': payment.tax_today,
            })

    @api.depends('currency_id_dif','currency_id','amount','tax_today')
    def _currency_equal(self):
        for rec in self:
            currency_equal = rec.currency_id_company != rec.currency_id
            
            usd_currency = self.env.ref('base.USD')
            
            if currency_equal:
                if rec.currency_id == usd_currency:
                    # Pago en USD, moneda de la compañía es VEF (u otra)
                    # El importe local (VEF) se multiplica, el ref (USD) es el monto original
                    rec.amount_local = rec.amount * rec.tax_today
                    rec.amount_ref = rec.amount
                else:
                    # Pago en VEF, moneda de la compañía es USD (o similar)
                    # El importe local (USD) se divide, el ref (VEF) es el monto original
                    rec.amount_local = (rec.amount / rec.tax_today) if rec.amount > 0 and rec.tax_today > 0 else 0
                    rec.amount_ref = rec.amount
            else:
                rec.amount_local = rec.amount
                if rec.currency_id == usd_currency:
                    # Pago en USD, compañía en USD, importe referencia es VEF (se multiplica)
                    rec.amount_ref = rec.amount * rec.tax_today
                else:
                    # Pago en VEF, compañía en VEF, importe referencia es USD (se divide)
                    rec.amount_ref = (rec.amount / rec.tax_today) if rec.amount > 0 and rec.tax_today > 0 else 0
                    
            rec.currency_equal = currency_equal

            if rec.aplicar_igtf_divisa:
                if rec.currency_id.name == 'USD':
                    rec.mount_igtf = rec.amount * rec.igtf_divisa_porcentage / 100
                    rec.amount_total_pagar = rec.mount_igtf + rec.amount
                else:
                    rec.mount_igtf = 0
                    rec.amount_total_pagar = rec.amount
            else:
                rec.mount_igtf = 0
                rec.amount_total_pagar = rec.amount

    def action_draft(self):
        res = super().action_draft()
        self.move_id_dif.button_draft()
        if self.move_id_igtf_divisa and self.move_id_igtf_divisa.state == 'done':
            self.move_id_igtf_divisa.button_draft()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self.move_id_dif.button_cancel()
        if self.move_id_igtf_divisa:
            self.move_id_igtf_divisa.button_cancel()
        return res

    def action_post(self):
        # Safety net: correct line balances using the custom rate BEFORE posting.
        # If write() already synced the lines (Odoo 16/17 lazy-move style), this
        # is a no-op because the amounts will already be correct.
        self.filtered(
            lambda p: p.custom_rate and p.tax_today
        )._sync_move_lines_with_custom_rate()

        res = super().action_post()
        self.move_id_dif._post(soft=False)
        for payment in self:
            if payment.move_id:
                payment.move_id.write({
                    'edit_trm': payment.custom_rate,
                    'tax_today': payment.tax_today,
                })
            if not payment.move_id_igtf_divisa and payment.aplicar_igtf_divisa:
                payment.register_move_igtf_divisa_payment()
            elif payment.move_id_igtf_divisa and payment.move_id_igtf_divisa.state == 'draft':
                payment.move_id_igtf_divisa.action_post()
        return res

    def register_move_igtf_divisa_payment(self):
        diario = self.journal_igtf_id or self.journal_id

        # Validar que las cuentas IGTF estén configuradas antes de crear el asiento
        # Para la cuenta del pago, usar la cuenta predeterminada del diario (banco/caja)
        # con fallback a la cuenta a nivel de compañía
        if self.payment_type == 'inbound':
            payment_account = (
                diario.default_account_id or 
                diario.company_id.account_journal_payment_debit_account_id
            )
            igtf_account = self.company_id.account_debit_wh_igtf_id
            igtf_account_label = "Cuenta Débito IGTF (account_debit_wh_igtf_id)"
        else:
            payment_account = (
                diario.default_account_id or 
                diario.company_id.account_journal_payment_credit_account_id
            )
            igtf_account = self.company_id.account_credit_wh_igtf_id
            igtf_account_label = "Cuenta Crédito IGTF (account_credit_wh_igtf_id)"

        if not payment_account:
            raise ValidationError(_(
                "No se puede registrar el asiento IGTF: Falta configurar la cuenta predeterminada en el diario '%s'.\n\n"
                "Por favor vaya a: Contabilidad > Configuración > Diarios > %s > Pestaña 'Pagos'"
            ) % (diario.name, diario.name))

        if not igtf_account:
            raise ValidationError(_(
                "No se puede registrar el asiento IGTF: Falta configurar la %s en la compañía.\n\n"
                "Por favor vaya a: Contabilidad > Configuración > Ajustes > Sección 'Dual Currency / IGTF'"
            ) % igtf_account_label)

        vals = {
            'date': self.date,
            'journal_id': diario.id,
            'currency_id': self.currency_id.id,
            'tax_today': self.tax_today,
            'edit_trm': self.custom_rate,
            'ref': self.ref,
            'state': 'draft',
            'move_type': 'entry',
            'line_ids': [],
        }

        move_id = self.env['account.move'].with_context(check_move_validity=False).create(vals)
        line_ids = [
            (5, 0, 0),
            (0, 0, {
                'account_id': payment_account.id,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'date_maturity': False,
                'ref': "Comisión IGTF Divisa",
                'date': self.date,
                'partner_id': self.partner_id.id,
                'name': "Comisión IGTF Divisa",
                'journal_id': self.journal_id.id,
                'credit': float(self.mount_igtf * self.tax_today) if self.payment_type != 'inbound' else float(0.0),
                'debit': float(self.mount_igtf * self.tax_today) if self.payment_type == 'inbound' else float(0.0),
                'amount_currency': -self.mount_igtf if self.payment_type != 'inbound' else self.mount_igtf,
            }),
            (0, 0, {
                'account_id': igtf_account.id,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'date_maturity': False,
                'ref': "Comisión IGTF Divisa",
                'date': self.date,
                'name': "Comisión IGTF Divisa",
                'journal_id': self.journal_id.id,
                'credit': float(self.mount_igtf * self.tax_today) if self.payment_type == 'inbound' else float(0.0),
                'debit': float(self.mount_igtf * self.tax_today) if self.payment_type != 'inbound' else float(0.0),
                'amount_currency': -self.mount_igtf if self.payment_type == 'inbound' else self.mount_igtf,
            })
        ]
        move_id.line_ids = line_ids
        if move_id:
            self.write({'move_id_igtf_divisa': move_id.id})
            move_id.action_post()
        return True

    def _prepare_payment_moves(self):
        """Override: adds custom rate to move vals and corrects line debit/credit.

        Odoo core computes debit/credit using the system exchange rate. For payments
        with a custom rate we recalculate those values here so the journal entry is
        created with the correct amounts from the start.
        """
        move_vals_list = super()._prepare_payment_moves()
        for payment, move_vals in zip(self, move_vals_list):
            payment_currency = payment.currency_id
            company_currency = payment.company_id.currency_id

            for move_val in move_vals:
                move_val.update({
                    'tax_today': payment.tax_today,
                    'edit_trm': payment.custom_rate,
                })

                # For custom-rate payments in a foreign currency journal, the debit/credit
                # in line vals are computed with the system rate by Odoo core. Correct them
                # here so the move is created with the right amounts.
                if (payment.custom_rate and payment.tax_today
                        and payment_currency != company_currency):
                    try:
                        rate = self.env['res.currency'].with_context(
                            edit_trm=True, tax_today=payment.tax_today,
                        )._get_conversion_rate(
                            from_currency=payment_currency,
                            to_currency=company_currency,
                            company=payment.company_id,
                            date=payment.date or fields.Date.today(),
                        )
                    except Exception:
                        rate = None

                    if rate:
                        for line_cmd in move_val.get('line_ids', []):
                            if not (isinstance(line_cmd, (list, tuple)) and len(line_cmd) == 3):
                                continue
                            line_vals = line_cmd[2]
                            if not isinstance(line_vals, dict):
                                continue
                            ac = line_vals.get('amount_currency', 0.0)
                            line_currency_id = line_vals.get('currency_id')
                            if not ac or not line_currency_id:
                                continue
                            line_currency = self.env['res.currency'].browse(line_currency_id)
                            if line_currency != payment_currency:
                                continue
                            correct = company_currency.round(abs(ac) * rate)
                            if line_vals.get('debit', 0.0):
                                line_vals['debit'] = correct
                            elif line_vals.get('credit', 0.0):
                                line_vals['credit'] = correct
        return move_vals_list

    def _sync_move_lines_with_custom_rate(self):
        """Correct move line amounts for payments that use a custom exchange rate.

        Odoo creates/updates journal lines using the system BCV rate. When a payment
        has custom_rate=True this method:
          - For same-currency journals (e.g. VEF company + VEF payment): the native
            balance is already correct (= amount_currency). Only debit_usd/credit_usd
            need to be recalculated with the custom rate.
          - For foreign-currency journals (e.g. VEF payment, USD company): the native
            balance uses the system rate and must be corrected. Writing the corrected
            debit/credit/balance automatically triggers the account_move_line write()
            override which recalculates debit_usd/credit_usd.
        """
        for payment in self:
            if not payment.custom_rate or not payment.tax_today:
                continue
            move = payment.move_id
            if not move or move.state != 'draft':
                continue

            company_currency = payment.company_currency_id
            payment_currency = payment.currency_id

            # Ensure the move has the correct rate flags before we read related fields
            if not move.edit_trm or move.tax_today != payment.tax_today:
                move.with_context(check_move_validity=False).write({
                    'edit_trm': True,
                    'tax_today': payment.tax_today,
                })

            if payment_currency == company_currency:
                # Same-currency payment (e.g. VEF journal + VEF company):
                # native balance = amount_currency, which is already correct.
                # Only recalculate debit_usd / credit_usd using the custom rate.
                for line in move.line_ids.filtered(
                    lambda l: l.display_type not in ('line_section', 'line_note')
                ):
                    new_du = line._calculate_debit_usd(
                        line.balance, line.amount_currency, move,
                        line.currency_id, line.company_id,
                    )
                    new_cu = line._calculate_credit_usd(
                        line.balance, line.amount_currency, move,
                        line.currency_id, line.company_id,
                    )
                    if (abs(line.debit_usd - new_du) > 0.001
                            or abs(line.credit_usd - new_cu) > 0.001):
                        line.debit_usd = new_du
                        line.credit_usd = new_cu
                continue

            # Foreign-currency payment: recalculate native balance with custom rate.
            try:
                rate = self.env['res.currency'].with_context(
                    edit_trm=True, tax_today=payment.tax_today,
                )._get_conversion_rate(
                    from_currency=payment_currency,
                    to_currency=company_currency,
                    company=payment.company_id,
                    date=payment.date or fields.Date.today(),
                )
            except Exception:
                continue

            if not rate:
                continue

            for line in move.line_ids.filtered(
                lambda l: (
                    l.display_type not in ('line_section', 'line_note')
                    and l.currency_id == payment_currency
                )
            ):
                ac = line.amount_currency
                if not ac:
                    continue
                correct = company_currency.round(abs(ac) * rate)
                # Only rewrite if the current balance differs from the correct one
                if abs(abs(line.balance) - correct) < 0.001:
                    continue
                if ac > 0:
                    write_vals = {
                        'debit': correct, 'credit': 0.0, 'balance': correct,
                    }
                else:
                    write_vals = {
                        'debit': 0.0, 'credit': correct, 'balance': -correct,
                    }
                # Writing debit/credit/balance triggers our account_move_line.write()
                # override which auto-recalculates debit_usd / credit_usd.
                line.with_context(check_move_validity=False).write(write_vals)

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._ensure_manual_currency_rate()
        return payments

    def write(self, vals):
        res = super().write(vals)
        tracked_fields = {'tax_today', 'custom_rate', 'currency_id', 'date'}
        if tracked_fields & set(vals.keys()):
            self._ensure_manual_currency_rate()
        for payment in self:
            if payment.custom_rate:
                if payment.tax_today != payment.move_id.tax_today:
                    payment.move_id.write({
                        'edit_trm': payment.custom_rate,
                        'tax_today': payment.tax_today,
                    })
        # When the custom rate or rate value changes, fix the draft move lines so
        # they reflect the custom rate (not the system BCV rate Odoo used originally).
        if {'tax_today', 'custom_rate'} & set(vals.keys()):
            self.filtered(
                lambda p: p.custom_rate and p.tax_today
            )._sync_move_lines_with_custom_rate()
        return res

    @api.constrains('ref', 'journal_id', 'state')
    def _check_ref_uniqueness(self):
        for payment in self:
            if payment.ref and payment.journal_id.type == 'bank' and payment.state != 'cancel':
                # Búsqueda usando sudo() para asegurar que encontramos duplicados incluso si el usuario no tiene acceso a ellos
                duplicate_payment = self.sudo().search([
                    ('ref', '=', payment.ref),
                    ('journal_id', '=', payment.journal_id.id),
                    ('state', '!=', 'cancel'),
                    ('id', '!=', payment.id),
                    ('company_id', '=', payment.company_id.id),
                ], limit=1)
                if duplicate_payment:
                    raise ValidationError(_(
                        "La referencia bancaria '%s' ya ha sido registrada en el diario '%s'. "
                        "Existe un pago previo con esta referencia: %s."
                    ) % (payment.ref, payment.journal_id.name, duplicate_payment.name))

