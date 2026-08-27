# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _, Command

_logger = logging.getLogger(__name__)

from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning
from odoo.tools import (
    date_utils,
    email_re,
    email_split,
    float_compare,
    float_is_zero,
    format_amount,
    format_date,
    formatLang,
    frozendict,
    get_lang,
    is_html_empty,
    sql
)
import json


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_ve_company = fields.Boolean(
        related='company_id.is_ve_company',
        string='Empresa VE'
    )

    currency_id_dif = fields.Many2one("res.currency",
                                      string="Moneda Dual Ref.",
                                      default=lambda self: self.env['res.currency'].search([('name', '=', 'USD')],
                                                                                           limit=1), )

    acuerdo_moneda = fields.Boolean(string="Acuerdo de Factura Bs.", default=False)

    tax_today_readonly = fields.Float(string="Tax Today Read Only?", compute="_tax_today_readonly", default=True)

    tax_today = fields.Float(string="Tasa", 
                            #  default=lambda self: self.env.company.currency_id_dif.inverse_rate,
                            compute="_tax_today_rate",
                            inverse="_onchange_tax_today",
                            tracking=True, 
                            digits=(16, 4),
                            store=True,
                            copy=True
                            )

    edit_trm = fields.Boolean(string="Editar tasa", 
                              compute=False, # '_edit_trm',
                              copy=False
                              )
                        

    name_rate = fields.Char(
                            store=True, 
                            readonly=True, 
                            compute='_name_ref'
                            )
    amount_untaxed_usd = fields.Monetary(currency_field='currency_id_dif', 
                                         string="Base imponible Ref.", 
                                         store=True)
    amount_tax_usd = fields.Monetary(
        currency_field='currency_id_dif', 
        string="Impuestos Ref.", 
        store=True,
        readonly=True)
    amount_total_usd = fields.Monetary(currency_field='currency_id_dif', 
                                       string='Total Ref.', 
                                       store=True, 
                                       readonly=True,
                                    #    compute='_amount_all_usd',
                                       tracking=True
                                       )

    amount_residual_usd = fields.Monetary(currency_field='currency_id_dif', 
                                        #   compute='_compute_amount', 
                                          string='Adeudado Ref.',
                                          readonly=True, 
                                          store=True
                                          )
    invoice_payments_widget_usd = fields.Binary(
                                                groups="account.group_account_invoice,account.group_account_readonly",
                                                # compute='_compute_payments_widget_reconciled_info_USD'
                                                )

    amount_untaxed_bs = fields.Monetary(currency_field='company_currency_id', 
                                        string="Base imponible Bs.", 
                                        store=True,
                                        # compute="_amount_all_usd"
                                        )
    amount_tax_bs = fields.Monetary(currency_field='company_currency_id', 
                                    string="Impuestos Bs.", 
                                    store=True,
                                    readonly=True)
    amount_total_bs = fields.Monetary(currency_field='company_currency_id', 
                                      string='Total Bs.', 
                                      store=True,
                                      readonly=True,
                                    #   compute='_amount_all_usd'
                                      )

    invoice_payments_widget_bs = fields.Text(groups="account.group_account_invoice")

    same_currency = fields.Boolean(
        string="Mismo tipo de moneda",
        compute='_same_currency'
        )

    @api.depends('edit_trm')
    def _tax_today_readonly(self):
        for record in self:
            record.tax_today_readonly = record.edit_trm == False or record.state != 'draft'

    #Inicio función sustituida por Anthony en Digiflex
    #Comentada por YG 18ENE2025
    @api.depends('invoice_date')
    def _tax_today_rate(self):
        for record in self:
            if not record.company_id.is_ve_company:
                record.tax_today = 1.0
                continue
            if not record.edit_trm:
                date = record.invoice_date or fields.Date.context_today(record)
                date_str = date.strftime("%Y-%m-%d")
                tasa = record.env['res.currency.rate'].search([('currency_id', '=', record.company_id.currency_id_dif.id),('name', '=', date_str)], limit=1).inverse_company_rate
                record.tax_today = tasa if tasa else record.env['res.currency.rate'].search([('currency_id', '=', record.company_id.currency_id_dif.id)], order="name desc", limit=1).inverse_company_rate


    @api.depends('currency_id')
    def _same_currency(self):
        self.same_currency = self.currency_id == self.env.company.currency_id

    @api.onchange('tax_today')
    def _onchange_tax_today(self):
        for rec in self:
            if not rec.company_id.is_ve_company:
                continue
            for aml in rec.line_ids:
                if aml.debit_usd == 0 and aml.debit > 0:
                    aml.with_context(check_move_validity=False).debit_usd = (aml.debit / rec.tax_today) if rec.tax_today > 0 else 0

                if aml.credit_usd == 0 and aml.credit > 0:
                    aml.with_context(check_move_validity=False).credit_usd = (aml.credit / rec.tax_today) if rec.tax_today > 0 else 0

    def _ensure_manual_currency_rate(self):
        """Ensure a currency rate exists for manual invoice rates."""
        rate_model = self.env['res.currency.rate'].sudo()
        invoice_types = {
            'out_invoice', 'out_refund', 'out_receipt',
            'in_invoice', 'in_refund', 'in_receipt',
        }
        for move in self:
            if not move.company_id.is_ve_company:
                continue
            if move.move_type not in invoice_types:
                continue
            if not move.edit_trm:
                continue
            currency = move.currency_id_dif
            company = move.company_id
            if not currency or currency == company.currency_id:
                continue
            if not move.tax_today:
                continue
            rate_date = move.invoice_date or move.date or fields.Date.context_today(move)
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
                'inverse_company_rate': move.tax_today,
            })

    @api.depends('currency_id_dif')
    def _name_ref(self):
        for record in self:
            record.name_rate = record.currency_id_dif.currency_unit_label
    
    def write(self, vals):
        res = super().write(vals)
        tracked_fields = {'tax_today', 'edit_trm', 'invoice_date', 'date', 'currency_id'}
        if tracked_fields & set(vals.keys()):
            self._ensure_manual_currency_rate()
        return res

    def _reconcile_reversed_moves(self, reversed_moves, cancel=False):
        """Override para corregir líneas de NC cross-currency de l10n_ve_full.

        En empresas venezolanas con facturas en moneda extranjera, l10n_ve_full crea las
        líneas de ingreso e IVA del NC como CRÉDITO (misma dirección que la factura original
        en lugar de invertirla como debería ser una reversión).

        Esto hace que Odoo genere la línea AR del NC como DÉBITO (+116) para balancear el
        asiento. Con la factura original también mostrando AR DÉBITO (+116), el motor de
        reconciliación ve dos DÉBITOS del mismo signo → ningún par DÉBITO/CRÉDITO → retorna
        None → la factura no queda pagada.

        Para facturas en la misma moneda de la compañía, l10n_ve_full crea correctamente las
        líneas de ingreso/IVA como DÉBITO (reversión correcta) → AR del NC = CRÉDITO → la
        reconciliación funciona sin necesidad de este fix.

        Fix: si detectamos que ambas líneas AR (original y NC) son DÉBITO (mismo signo),
        invertimos la dirección de TODAS las líneas del NC. El asiento contable sigue
        balanceado (suma = 0) y queda con la convención estándar de Odoo para reversiones:
          - Ingreso NC: DÉBITO  (revierte el CRÉDITO de ingreso de la factura)
          - IVA NC:     DÉBITO  (revierte el CRÉDITO de IVA de la factura)
          - AR NC:      CRÉDITO (reduce la deuda del cliente, opuesto al DÉBITO de la factura)
        """
        if not reversed_moves:
            return super()._reconcile_reversed_moves(reversed_moves, cancel)

        for orig_move, rev_move in zip(self, reversed_moves):
            # Solo aplica a empresas venezolanas con NCs de facturas de venta/compra
            if not rev_move.company_id.is_ve_company:
                continue
            if orig_move.move_type not in ('out_invoice', 'in_invoice',
                                           'out_refund', 'in_refund'):
                continue

            # Obtener líneas AR/AP de ambos movimientos
            ar_account_types = ('asset_receivable', 'liability_payable')
            orig_ar = orig_move.line_ids.filtered(
                lambda l: l.account_id.account_type in ar_account_types
            )
            rev_ar = rev_move.line_ids.filtered(
                lambda l: l.account_id.account_type in ar_account_types
            )
            if not orig_ar or not rev_ar:
                continue

            orig_bal = orig_ar[0].balance
            rev_bal = rev_ar[0].balance

            # Si ambas tienen el mismo signo (ambas DÉBITO o ambas CRÉDITO), l10n_ve_full
            # creó el NC con dirección incorrecta → invertir TODAS las líneas del NC
            if (orig_bal > 0 and rev_bal > 0) or (orig_bal < 0 and rev_bal < 0):
                _logger.info(
                    "[RECONCILE-FLIP] NC %s tiene AR balance=%s (mismo signo que factura %s "
                    "balance=%s). Invirtiendo todas las líneas del NC para corregir dirección.",
                    rev_move.name, rev_bal, orig_move.name, orig_bal
                )
                # SQL directo: invertir balance/debit/credit/amount_currency/amount_residual
                # de TODAS las líneas de la NC. El asiento contable sigue balanceado (suma=0)
                # pero con la dirección correcta para la convención estándar de Odoo.
                line_ids = rev_move.line_ids.ids
                if line_ids:
                    self.env.cr.execute("""
                        UPDATE account_move_line
                        SET
                            debit              = credit,
                            credit             = debit,
                            balance            = -balance,
                            amount_currency    = -amount_currency,
                            amount_residual    = -amount_residual,
                            amount_residual_currency = -amount_residual_currency
                        WHERE id = ANY(%s)
                    """, [line_ids])
                    # Re-leer los valores post-flip del DB y sincronizar ORM cache.
                    # CRÍTICO: sin esto, el ORM conserva el dirty state de computes que
                    # corrieron ANTES del flip. Tras la reconciliación, el flush de esos
                    # valores sucios falla con "No puede modificar asiento conciliado".
                    self.env.cr.execute("""
                        SELECT id, balance, debit, credit,
                               amount_currency, amount_residual, amount_residual_currency
                        FROM account_move_line WHERE id = ANY(%s)
                    """, [line_ids])
                    db_vals = {
                        row[0]: {
                            'balance': row[1], 'debit': row[2], 'credit': row[3],
                            'amount_currency': row[4], 'amount_residual': row[5],
                            'amount_residual_currency': row[6],
                        }
                        for row in self.env.cr.fetchall()
                    }
                    AML = self.env['account.move.line']
                    field_names = ['balance', 'debit', 'credit', 'amount_currency',
                                   'amount_residual', 'amount_residual_currency']
                    fields_map = {fn: AML._fields[fn] for fn in field_names
                                  if fn in AML._fields}
                    for line in rev_move.line_ids:
                        if line.id not in db_vals:
                            continue
                        row = db_vals[line.id]
                        for fname, field in fields_map.items():
                            self.env.cache.set(line, field, row[fname])


        return super()._reconcile_reversed_moves(reversed_moves, cancel)

    def _compute_amount(self):
        """Override para garantizar que las notas de crédito de empresas VE
        tengan amount_total positivo.

        l10n_ve_full crea líneas de ingreso en out_refund con amount_currency negativo
        (misma dirección que la factura original en lugar de invertirla). Esto hace que
        _compute_amount calcule amount_total = -116 en Odoo 16, lo que dispara el check
        "importe total negativo" en action_post().

        Solución: asegurar que los totales almacenados sean positivos para NC de empresas VE.
        Los asientos contables (balance, debit/credit) no se modifican — solo los campos
        de totales de la factura que usa Odoo para mostrar y validar.
        """
        super()._compute_amount()
        for move in self:
            if (move.move_type in ('out_refund', 'in_refund')
                    and move.company_id.is_ve_company
                    and move.amount_total < 0):
                move.amount_total = abs(move.amount_total)
                if move.amount_untaxed < 0:
                    move.amount_untaxed = abs(move.amount_untaxed)
                if move.amount_tax < 0:
                    move.amount_tax = abs(move.amount_tax)

    def _compute_tax_totals(self):
        """Override para corregir el display de IVA/subtotal en NC de empresas VE.

        Después del FLIP en _reconcile_reversed_moves, las líneas de ingreso e IVA
        quedan en convención DÉBITO (+100, +16). Odoo aplica direction_sign=-1 para
        out_refund al calcular tax_totals → los montos quedan -100, -16.

        Resultado: el NC en BORRADOR muestra IVA -16 Bs.F y Total 84 Bs.F, confundiendo
        al cliente antes de confirmar.

        Fix: después de super(), si los montos son negativos para un NC de empresa VE,
        los convertimos a positivos en el dict tax_totals.
        """
        super()._compute_tax_totals()
        for move in self:
            if move.move_type not in ('out_refund', 'in_refund'):
                continue
            if not move.company_id.is_ve_company:
                continue
            ttotals = move.tax_totals
            if not ttotals or not isinstance(ttotals, dict):
                continue
            if (ttotals.get('amount_total') or 0) >= 0:
                continue  # Ya es positivo, nada que hacer

            # Los montos son negativos por el FLIP → convertir a positivo.
            # Usamos copy para no mutar el dict original cacheado por el ORM.
            import copy
            fixed = copy.deepcopy(ttotals)
            currency = move.currency_id
            MONETARY_KEYS = {
                'amount_total', 'amount_untaxed', 'amount',
                'tax_group_amount', 'tax_group_base_amount',
            }

            def _fix(obj):
                if isinstance(obj, dict):
                    for k, v in list(obj.items()):
                        if k in MONETARY_KEYS and isinstance(v, (int, float)) and v < 0:
                            obj[k] = -v
                            # Actualizar el string formateado correspondiente si existe
                            fk = 'formatted_' + k
                            if fk in obj:
                                obj[fk] = formatLang(move.env, -v, currency_obj=currency)
                        elif isinstance(v, (dict, list)):
                            _fix(v)
                elif isinstance(obj, list):
                    for item in obj:
                        _fix(item)

            _fix(fixed)
            move.tax_totals = fixed

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._ensure_manual_currency_rate()
        return moves


    @api.constrains('ref', 'journal_id', 'state')
    def _check_payment_ref_uniqueness(self):
        for move in self:
            # Solo validar en asientos de tipo 'entry' vinculados a un pago, con referencia y en diario de banco
            if move.payment_id and move.ref and move.journal_id.type == 'bank' and move.state != 'cancel':
                duplicate_move = self.sudo().search([
                    ('ref', '=', move.ref),
                    ('journal_id', '=', move.journal_id.id),
                    ('state', '!=', 'cancel'),
                    ('id', '!=', move.id),
                    ('payment_id', '!=', False),
                    ('company_id', '=', move.company_id.id),
                ], limit=1)
                if duplicate_move:
                    raise ValidationError(_(
                        "La referencia bancaria '%s' ya ha sido registrada en el diario '%s'. "
                        "Existe un asiento contable/pago previo con esta referencia: %s."
                    ) % (move.ref, move.journal_id.name, duplicate_move.name))

   