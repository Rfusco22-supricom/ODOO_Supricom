# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _, Command

_logger = logging.getLogger(__name__)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Campos USD calculados en create/write para evitar problemas con notas de crédito
    # NO usar compute porque no se dispara correctamente durante la creación de reversiones
    debit_usd = fields.Monetary(
        currency_field='currency_id_dif', 
        string='Débito $',
        store=True,
        readonly=False
    )
    credit_usd = fields.Monetary(
        currency_field='currency_id_dif', 
        string='Crédito $', 
        store=True,
        readonly=False
    )
    edit_trm = fields.Boolean(related="move_id.edit_trm",
                              store=True, 
                              readonly=False, 
                              help="Indicates if the exchange rate can be edited in this move line.",
                              copy=False)
    tax_today = fields.Float(
                                related="move_id.tax_today",
                                store=True, 
                                digits=(16, 4),
                                copy=False,
                            )
    currency_id_dif = fields.Many2one("res.currency", 
                                      related="move_id.currency_id_dif", 
                                      store=True)
    
    price_unit_usd = fields.Monetary(
                                    currency_field='currency_id_dif', 
                                    string='Precio $', 
                                    store=True,
                                    compute='_price_unit_usd', 
                                    readonly=False
                                    )
    price_subtotal_usd = fields.Monetary(
                                    currency_field='currency_id_dif', 
                                    string='SubTotal $', 
                                    store=True,
                                    compute="_price_subtotal_usd", 
                                    digits='Dual_Currency')
    
    
    amount_residual_usd = fields.Monetary(
                                            string='Residual Amount USD', 
                                            store=True,
                                            help="The residual amount on a journal item expressed in the company currency.")
    
    balance_usd = fields.Monetary(string='Balance Ref.',
                                  currency_field='currency_id_dif', 
                                  store=True, 
                                  readonly=False,
                                  compute='_compute_balance_usd',
                                  default=lambda self: self._compute_balance_usd(),
                                  help="Technical field holding the debit_usd - credit_usd in order to open meaningful graph views from reports")

    @api.depends('debit_usd', 'credit_usd')
    def _compute_balance_usd(self):
        for line in self:
            if line.display_type in ('line_section', 'line_note'):
                line.balance_usd = 0
            else:
                line.balance_usd = line.debit_usd - line.credit_usd

    def _calculate_debit_usd(self, balance, amount_currency, move_id, currency_id, company_id):
        """Método auxiliar para calcular debit_usd usando el balance ya calculado por Odoo.

        Maneja dos escenarios:
        - Instancia VES (moneda base = Bs): convierte de Bs a USD usando la tasa.
        - Instancia B   (moneda base = USD): convierte de USD a VES multiplicando por la tasa.
        """
        to_currency = company_id.currency_id_dif
        if not to_currency:
            return 0.0

        # Caso: la línea ya está expresada en la moneda dual → usar amount_currency directamente
        if currency_id == to_currency:
            return amount_currency if amount_currency > 0.0 else 0.0

        # Valor a convertir (solo débitos, i.e. balance positivo)
        debit_value = balance if balance > 0.0 else 0.0
        if not debit_value:
            return 0.0

        from_currency = company_id.currency_id
        date = move_id.date or fields.Date.today()

        if from_currency == to_currency:
            # Ambas monedas son la misma → no hay conversión útil
            return debit_value

        tax_today = move_id.tax_today

        # Instancia B: moneda compañía = USD, dual = VES
        # El balance está en USD → multiplicar por tasa BCV para obtener VES
        if from_currency != currency_id and to_currency == currency_id:
            # currency_id es la moneda dual (VES), to_currency también es VES
            # from_currency (USD) != to_currency (VES): convertir USD → VES multiplicando
            if tax_today and tax_today > 0.0:
                return from_currency.round(debit_value * tax_today)

        # Instancia A: moneda compañía = VES (Bs), dual = USD
        # El balance está en VES → dividir por tasa BCV para obtener USD
        if from_currency == currency_id and to_currency != from_currency:
            # currency_id == company_currency (VES) y to_currency es USD
            # Convertir VES → USD dividiendo por la tasa
            if tax_today and tax_today > 0.0:
                return from_currency.round(debit_value / tax_today)

        context = {}
        if move_id.edit_trm and tax_today:
            context = {
                'edit_trm': move_id.edit_trm,
                'tax_today': tax_today,
            }

        return from_currency.with_context(**context)._convert(
            debit_value,
            to_currency,
            company_id,
            date,
        )
    
    def _calculate_credit_usd(self, balance, amount_currency, move_id, currency_id, company_id):
        """Método auxiliar para calcular credit_usd usando el balance ya calculado por Odoo.

        Maneja dos escenarios:
        - Instancia VES (moneda base = Bs): convierte de Bs a USD usando la tasa.
        - Instancia B   (moneda base = USD): convierte de USD a VES multiplicando por la tasa.
        """
        to_currency = company_id.currency_id_dif
        if not to_currency:
            return 0.0

        # Caso: la línea ya está expresada en la moneda dual → usar amount_currency directamente
        if currency_id == to_currency:
            return abs(amount_currency) if amount_currency < 0.0 else 0.0

        # Valor a convertir (solo créditos, i.e. balance negativo)
        credit_value = -balance if balance < 0.0 else 0.0
        if not credit_value:
            return 0.0

        from_currency = company_id.currency_id
        date = move_id.date or fields.Date.today()

        if from_currency == to_currency:
            return credit_value

        tax_today = move_id.tax_today

        # Instancia B: moneda compañía = USD, dual = VES
        # El balance está en USD → multiplicar por tasa BCV para obtener VES
        if from_currency != currency_id and to_currency == currency_id:
            if tax_today and tax_today > 0.0:
                return from_currency.round(credit_value * tax_today)

        # Instancia A: moneda compañía = VES (Bs), dual = USD
        # El balance está en VES → dividir por tasa BCV para obtener USD
        if from_currency == currency_id and to_currency != from_currency:
            if tax_today and tax_today > 0.0:
                return from_currency.round(credit_value / tax_today)

        context = {}
        if move_id.edit_trm and tax_today:
            context = {
                'edit_trm': move_id.edit_trm,
                'tax_today': tax_today,
            }

        return from_currency.with_context(**context)._convert(
            credit_value,
            to_currency,
            company_id,
            date,
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para calcular debit_usd y credit_usd DESPUÉS de que Odoo calcule balance"""
        # Primero crear las líneas con super() para que Odoo calcule balance correctamente
        lines = super().create(vals_list)
        
        # Ahora calcular debit_usd y credit_usd usando el balance ya calculado
        for line in lines:
            if line.display_type not in ('line_section', 'line_note'):
                line.debit_usd = line._calculate_debit_usd(
                    line.balance, line.amount_currency, line.move_id, line.currency_id, line.company_id
                )
                line.credit_usd = line._calculate_credit_usd(
                    line.balance, line.amount_currency, line.move_id, line.currency_id, line.company_id
                )
        
        return lines
    
    def _fix_amount_currency_in_vals(self, vals):
        """
        Corrige el signo de amount_currency en vals antes de escribir a la DB.
        Lee el balance directamente desde la DB (no del ORM cache) para evitar
        valores desactualizados durante flushes de campos computed.

        La constraint 'account_move_line_check_amount_currency_balance_sign' requiere:
        - currency_id == company_currency_id: amount_currency == balance (exactamente)
        - currency_id != company_currency_id: sign(amount_currency) == sign(balance)

        Odoo core puede escribir amount_currency con signo incorrecto durante la
        reconciliación automática de notas de crédito (el 'fix in-place').
        """
        if 'amount_currency' not in vals:
            return vals

        new_ac = float(vals['amount_currency'])
        if not self:
            return vals

        # Leer balance desde DB para evitar cache ORM desactualizado.
        # Si balance viene en el mismo write, usarlo directamente (es confiable).
        # Si no, leer el valor comprometido en DB para evitar que el cache ORM
        # desactualizado lleve a una corrección incorrecta.
        balance_in_vals = vals.get('balance')  # si viene en el mismo write, confiar en él
        if balance_in_vals is None and self.ids:
            self.env.cr.execute(
                'SELECT id, balance FROM account_move_line WHERE id = ANY(%s)',
                [list(self.ids)]
            )
            db_balances = {row[0]: float(row[1]) for row in self.env.cr.fetchall()}
        else:
            db_balances = {}

        corrected_vals = dict(vals)
        needs_any_fix = False

        for line in self:
            # Determinar el balance de referencia:
            if balance_in_vals is not None:
                # balance viene en el mismo write() → usar ese valor
                balance = float(balance_in_vals)
            elif line.id in db_balances:
                # línea ya existe en DB → usar valor comprometido
                balance = db_balances[line.id]
            else:
                # línea no existe en DB todavía (recién creada en esta transacción)
                # Durante create(), las líneas tienen valores correctos desde el inicio
                # No corregir — evita que se zeroen product lines durante la creación
                continue

            line_currency = line.currency_id
            company_currency = line.company_currency_id
            needs_fix = False

            if line_currency == company_currency:
                # Mismo-moneda: amount_currency debe = balance exactamente
                if company_currency and not company_currency.is_zero(new_ac - balance):
                    needs_fix = True
                    corrected_ac = balance
            else:
                # Multi-moneda: sign(amount_currency) debe coincidir con sign(balance)
                if balance > 0 and new_ac < 0:
                    needs_fix = True
                    corrected_ac = abs(new_ac)
                elif balance < 0 and new_ac > 0:
                    needs_fix = True
                    corrected_ac = -abs(new_ac)

            if needs_fix:
                needs_any_fix = True
                corrected = dict(vals, amount_currency=corrected_ac)
                # Si amount_residual_usd viene en el mismo write (la reconciliación lo escribe
                # junto con amount_currency), corregirlo a 0.
                # Razón: el motor de reconciliación escribe ambos campos con el valor absoluto
                # positivo como "fix in-place". Al corregir amount_currency al signo correcto,
                # la línea queda totalmente reconciliada → amount_residual_usd = 0.
                if 'amount_residual_usd' in corrected:
                    corrected['amount_residual_usd'] = 0.0
                if len(self) == 1:
                    return corrected
                # Para recordset multi-línea, escribir esta línea por separado
                super(AccountMoveLine, line).write(corrected)

        if needs_any_fix and len(self) > 1:
            # Ya escribimos líneas individualmente, no volver a escribir
            return None  # señal de "ya manejado"

        return corrected_vals if not needs_any_fix else vals


    def write(self, vals):
        """Override write: corrige amount_currency y recalcula debit_usd/credit_usd."""
        if 'amount_currency' in vals:
            corrected = self._fix_amount_currency_in_vals(vals)
            if corrected is None:
                # _fix_amount_currency_in_vals ya escribió cada línea individualmente
                return True
            vals = corrected

        result = super().write(vals)

        if any(k in vals for k in ['balance', 'debit', 'credit', 'amount_currency', 'tax_today']):
            for line in self:
                if line.display_type not in ('line_section', 'line_note'):
                    line.debit_usd = line._calculate_debit_usd(
                        line.balance, line.amount_currency, line.move_id,
                        line.currency_id, line.company_id)
                    line.credit_usd = line._calculate_credit_usd(
                        line.balance, line.amount_currency, line.move_id,
                        line.currency_id, line.company_id)
        return result

    def _write(self, vals):
        """Override _write: intercepta flushes internos de computed fields.

        En Odoo 16, _write() es llamado por el ORM internamente cuando flushea campos
        computed (bypassando write()). Si detectamos que amount_currency violaría la
        constraint, DESCARTAMOS ese campo del write (preservamos el valor en DB).

        ESTO ES DIFERENTE de write() donde CORREGIMOS el valor. La diferencia es:
        - write() viene de reconciliación explícita → hay que corregir para que sea correcto
        - _write() viene de flush interno de compute → el valor es incorrecto, descartarlo
          y preservar el valor correcto ya en DB
        """
        if 'amount_currency' not in vals:
            return super()._write(vals)

        new_ac = float(vals['amount_currency'])
        import logging as _wlog
        _wl = _wlog.getLogger(__name__)
        _wl.info(f"[WRITE-DBG] _write() amount_currency={new_ac:.4f} for ids={list(self.ids)} vals_keys={list(vals.keys())}")

        # SIEMPRE leer el balance ORIGINAL de DB (no el balance_in_vals del compute).

        # El compute quiere escribir {balance:+116, debit:+116, credit:0, amount_currency:+116}
        # en un NC AR que fue creado con balance=-116 (CRÉDITO). Si usáramos balance_in_vals=+116,
        # la comprobación `balance < 0 and new_ac > 0` daría False (porque +116 < 0 es False)
        # y dejaríamos pasar la escritura, convirtiendo incorrectamente el NC AR en DÉBITO.
        if self.ids:
            self.env.cr.execute(
                'SELECT id, balance, amount_currency, debit, credit'
                '  FROM account_move_line WHERE id = ANY(%s)',
                [list(self.ids)]
            )
            db_rows = self.env.cr.fetchall()
            db_balances = {row[0]: float(row[1]) for row in db_rows}
            db_amount_currencies = {row[0]: float(row[2]) for row in db_rows}
            db_debits = {row[0]: float(row[3]) for row in db_rows}
            db_credits = {row[0]: float(row[4]) for row in db_rows}
        else:
            db_balances = {}
            db_amount_currencies = {}
            db_debits = {}
            db_credits = {}

        would_violate = False
        for line in self:
            if line.id not in db_balances:
                continue  # línea nueva, no manejar

            # Usar el balance ORIGINAL de DB para detectar si el nuevo amount_currency
            # tiene signo opuesto al balance que la línea tenía antes del flush.
            original_db_balance = db_balances[line.id]
            line_currency = line.currency_id
            company_currency = line.company_currency_id

            if line_currency == company_currency:
                # Mismo-moneda: amount_currency debe coincidir con balance.
                # Si 'balance' también viene en vals, el ORM actualiza ambos al mismo tiempo
                # (comportamiento estándar al postear una factura nueva cuya línea tiene
                # balance=0 en borrador). En ese caso, comparar contra el NUEVO balance (vals)
                # evita falsos positivos. Si balance no viene en vals, usar el balance de DB.
                if 'balance' in vals:
                    ref_balance = float(vals['balance'])
                else:
                    ref_balance = original_db_balance
                if company_currency and not company_currency.is_zero(new_ac - ref_balance):
                    would_violate = True
                    break
            else:
                # Multi-moneda: los signos deben coincidir (ambos positivos o ambos negativos)
                if (original_db_balance > 0 and new_ac < 0) or (original_db_balance < 0 and new_ac > 0):
                    would_violate = True
                    break

        if would_violate:


            # El compute quería invertir el signo — descartar los campos incorrectos del write.
            # Crítico: también descartar balance/debit/credit porque el compute (e.g.
            # _compute_balance) los recalcula desde el nuevo amount_currency incorrecto.
            # Si los dejamos, el NC AR queda como DÉBITO en DB y Odoo no puede reconciliar
            # (ambas líneas AR serían DÉBITO → sin par CRÉDITO → result: None).
            corrected_arc = {}
            if 'amount_residual_currency' in vals and db_amount_currencies:
                for line in self:
                    db_val = db_amount_currencies.get(line.id)
                    if db_val is not None:
                        corrected_arc[line.id] = db_val

            # Campos a descartar: los que tendrían el signo invertido
            FIELDS_TO_DROP = {'amount_currency', 'amount_residual_currency',
                              'balance', 'debit', 'credit'}
            vals = {k: v for k, v in vals.items() if k not in FIELDS_TO_DROP}

            # Si había amount_residual_currency, reinyectarlo con el valor CORRECTO
            if corrected_arc and len(self) == 1 and self.id in corrected_arc:
                vals['amount_residual_currency'] = corrected_arc[self.id]

            # Si amount_residual_usd viene en el mismo write, también corregirlo a 0.
            if 'amount_residual_usd' in vals:
                vals = dict(vals, amount_residual_usd=0.0)

            # Actualizar cache ORM con los valores CORRECTOS de DB (sin disparar recomputes).
            ac_field = self._fields['amount_currency']
            arc_field = self._fields.get('amount_residual_currency')
            balance_field = self._fields.get('balance')
            debit_field = self._fields.get('debit')
            credit_field = self._fields.get('credit')
            correction_lines = {}
            for line in self:
                db_ac = db_amount_currencies.get(line.id)
                if db_ac is None:
                    continue
                self.env.cache.set(line, ac_field, db_ac)
                if arc_field:
                    self.env.cache.set(line, arc_field, db_ac)
                if balance_field and line.id in db_balances:
                    self.env.cache.set(line, balance_field, db_balances[line.id])
                if debit_field and line.id in db_debits:
                    self.env.cache.set(line, debit_field, db_debits[line.id])
                if credit_field and line.id in db_credits:
                    self.env.cache.set(line, credit_field, db_credits[line.id])
                correction_lines[line.id] = db_ac

            # SQL directo para corregir amount_residual_currency en DB
            # (puede haber sido sobreescrito por _compute_amount_residual con el valor erróneo).
            if correction_lines:
                for line_id, correct_val in correction_lines.items():
                    self.env.cr.execute(
                        'UPDATE account_move_line SET amount_residual_currency = %s'
                        ' WHERE id = %s',
                        [correct_val, line_id]
                    )

        return super()._write(vals)



    @api.onchange('product_id')
    def _onchange_product_id(self):
        self._price_unit_usd()

    @api.depends('price_unit', 'product_id', 'tax_today')
    def _price_unit_usd(self):
        for rec in self:
            if rec.price_unit > 0:
                if rec.move_id.currency_id.name == 'USD':
                    rec.price_unit_usd = rec.price_unit
                elif rec.move_id.currency_id == rec.company_id.currency_id:
                    rec.price_unit_usd = (rec.price_unit / rec.tax_today) if rec.tax_today > 0 else 0
                else:
                    rec.price_unit_usd = rec.price_unit
            else:
                rec.price_unit_usd = 0

    @api.depends('price_subtotal')
    def _price_subtotal_usd(self):
        for rec in self:
            if rec.price_subtotal > 0:
                if rec.move_id.currency_id.name == 'USD':
                    rec.price_subtotal_usd = rec.price_subtotal
                elif rec.move_id.currency_id == rec.company_id.currency_id:
                    rec.price_subtotal_usd = (rec.price_subtotal / rec.tax_today) if rec.tax_today > 0 else 0
                else:
                    rec.price_subtotal_usd = rec.price_subtotal
            else:
                rec.price_subtotal_usd = 0


    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if 'tax_today' not in fields:
            return super(AccountMoveLine, self).read_group(domain, fields, groupby, offset=offset, limit=limit,
                                                           orderby=orderby, lazy=lazy)
        res = super(AccountMoveLine, self).read_group(domain, fields, groupby, offset=offset, limit=limit,
                                                      orderby=orderby, lazy=lazy)
        for group in res:
            if group.get('__domain'):
                records = self.search(group['__domain'])
                group['tax_today'] = 0
        return res

    def _compute_currency_rate(self):
        # esta función se usa para calcular debit y credit en el standard odoo
        for line in self:
            if line.currency_id:
                # Si la moneda de la línea es la misma que la moneda de la compañía,
                # la tasa SIEMPRE debe ser 1 (conversión 1:1).
                # Aplicar edit_trm en este caso rompería la invariante del core:
                # amount_currency debe ser estrictamente igual al balance cuando
                # currency_id == company_currency_id.
                if line.currency_id == line.company_currency_id:
                    line.currency_rate = 1
                else:
                    line.currency_rate = self.env['res.currency'].with_context(
                        edit_trm=line.edit_trm, tax_today=line.tax_today
                    )._get_conversion_rate(
                        from_currency=line.company_currency_id,
                        to_currency=line.currency_id,
                        company=line.company_id,
                        date=line._get_rate_date(),
                    )
            else:
                line.currency_rate = 1

    
    def _reconcile_plan_with_sync(self, plan_list, all_amls):
        # IMPORTANTE: NO propagar el contexto edit_trm/tax_today al motor de reconciliación
        import logging as _ln
        _rlog = _ln.getLogger(__name__)
        _rlog.info(f"[PLAN-SYNC] called with {len(plan_list)} plan entries, {len(all_amls) if all_amls else 0} all_amls")
        for i, plan_entry in enumerate(plan_list):
            if isinstance(plan_entry, dict):
                _rlog.info(f"[PLAN-SYNC] Plan[{i}] keys: {list(plan_entry.keys())}")
                amls = plan_entry.get('amls')
                if amls:
                    for aml in amls:
                        try:
                            _rlog.info(
                                f"[PLAN-SYNC]   AML id={aml.id} "
                                f"balance={aml.balance:.4f} {aml.company_currency_id.name} "
                                f"amount_currency={aml.amount_currency:.4f} {aml.currency_id.name} "
                                f"amount_residual={aml.amount_residual:.4f} "
                                f"amount_residual_currency={aml.amount_residual_currency:.4f} "
                                f"reconciled={aml.reconciled}"
                            )
                        except Exception as e:
                            _rlog.info(f"[PLAN-SYNC]   AML read error: {e}")
            else:
                _rlog.info(f"[PLAN-SYNC] Plan[{i}] (non-dict): {plan_entry!r}")
        result = super()._reconcile_plan_with_sync(plan_list, all_amls)
        _rlog.info(f"[PLAN-SYNC] result: {result}")
        return result


    @api.model
    def _prepare_move_line_residual_amounts(self, aml_values, counterpart_currency, shadowed_aml_values=None, other_aml_values=None):

        def is_payment(aml):
            return aml.move_id.payment_id or aml.move_id.statement_line_id

        def get_odoo_rate(aml, other_aml, currency):
            if forced_rate := self._context.get('forced_rate_from_register_payment'):
                return forced_rate
            if other_aml and not is_payment(aml) and is_payment(other_aml):
                return get_accounting_rate(other_aml, currency)
            if aml.move_id.is_invoice(include_receipts=True):
                exchange_rate_date = aml.move_id.invoice_date
            else:
                exchange_rate_date = aml._get_reconciliation_aml_field_value('date', shadowed_aml_values)
            return currency.with_context(edit_trm=aml.edit_trm, tax_today=aml.tax_today)._get_conversion_rate(aml.company_currency_id, currency, aml.company_id, exchange_rate_date)

        def get_accounting_rate(aml, currency):
            balance = aml._get_reconciliation_aml_field_value('balance', shadowed_aml_values)
            amount_currency = aml._get_reconciliation_aml_field_value('amount_currency', shadowed_aml_values)
            if not aml.company_currency_id.is_zero(balance) and not currency.is_zero(amount_currency):
                return abs(amount_currency / balance)

        aml = aml_values['aml']
        other_aml = (other_aml_values or {}).get('aml')
        remaining_amount_curr = aml_values['amount_residual_currency']
        remaining_amount = aml_values['amount_residual']
        company_currency = aml.company_currency_id
        currency = aml._get_reconciliation_aml_field_value('currency_id', shadowed_aml_values)
        account = aml._get_reconciliation_aml_field_value('account_id', shadowed_aml_values)
        has_zero_residual = company_currency.is_zero(remaining_amount)
        has_zero_residual_currency = currency.is_zero(remaining_amount_curr)
        is_rec_pay_account = account.account_type in ('asset_receivable', 'liability_payable')

        import logging as _rln2
        _rlog2 = _rln2.getLogger(__name__)
        _rlog2.info(
            f"[RESIDUALS] aml.id={aml.id} "
            f"amount_residual={remaining_amount:.4f} {company_currency.name} "
            f"amount_residual_currency={remaining_amount_curr:.4f} {currency.name} "
            f"has_zero_residual={has_zero_residual} "
            f"has_zero_residual_currency={has_zero_residual_currency} "
            f"counterpart_currency={counterpart_currency.name if counterpart_currency else None}"
        )
        available_residual_per_currency = {}

        if not has_zero_residual:
            available_residual_per_currency[company_currency] = {
                'residual': remaining_amount,
                'rate': 1,
            }
        if currency != company_currency and not has_zero_residual_currency:
            available_residual_per_currency[currency] = {
                'residual': remaining_amount_curr,
                'rate': get_accounting_rate(aml, currency),
            }

        if currency == company_currency \
            and is_rec_pay_account \
            and not has_zero_residual \
            and counterpart_currency != company_currency:
            rate = get_odoo_rate(aml, other_aml, counterpart_currency)
            residual_in_foreign_curr = counterpart_currency.round(remaining_amount * rate)
            if not counterpart_currency.is_zero(residual_in_foreign_curr):
                available_residual_per_currency[counterpart_currency] = {
                    'residual': residual_in_foreign_curr,
                    'rate': rate,
                }
        elif currency == counterpart_currency \
            and currency != company_currency \
            and not has_zero_residual_currency:
            available_residual_per_currency[counterpart_currency] = {
                'residual': remaining_amount_curr,
                'rate': get_accounting_rate(aml, currency),
            }
        return available_residual_per_currency

    @api.depends('debit', 'credit', 'account_id', 'currency_id', 'company_id',
                 'matched_debit_ids', 'matched_credit_ids', 'tax_today', 'edit_trm')
    def _compute_amount_residual(self):
        super()._compute_amount_residual()
        manual_lines = self.filtered(lambda line: line.move_id.currency_id_dif)
        (self - manual_lines).amount_residual_usd = 0.0

        stored_lines = manual_lines._origin
        if not stored_lines:
            return

        self.env['account.partial.reconcile'].flush_model(['amount_usd'])
        aml_ids = tuple(stored_lines.ids)

        if not aml_ids:
            return

        self.env.cr.execute('''
            SELECT part.debit_move_id AS line_id, COALESCE(SUM(part.amount_usd), 0.0) AS amount
              FROM account_partial_reconcile part
             WHERE part.debit_move_id IN %s
             GROUP BY part.debit_move_id
        ''', [aml_ids])
        debit_usd_map = dict(self.env.cr.fetchall())

        self.env.cr.execute('''
            SELECT part.credit_move_id AS line_id, COALESCE(SUM(part.amount_usd), 0.0) AS amount
              FROM account_partial_reconcile part
             WHERE part.credit_move_id IN %s
             GROUP BY part.credit_move_id
        ''', [aml_ids])
        credit_usd_map = dict(self.env.cr.fetchall())

        for line in manual_lines:
            manual_currency = line.move_id.currency_id_dif
            if not manual_currency:
                line.amount_residual_usd = 0.0
                continue

            if line.currency_id == manual_currency:
                base_amount = line.amount_currency
            else:
                rate = line.tax_today or line.move_id.tax_today
                if not rate:
                    base_amount = 0.0
                elif manual_currency == line.company_currency_id:
                    base_amount = line.balance
                else:
                    base_amount = line.balance / rate

            debit_usd = debit_usd_map.get(line._origin.id, 0.0)
            credit_usd = credit_usd_map.get(line._origin.id, 0.0)
            residual_amount = base_amount - debit_usd + credit_usd
            line.amount_residual_usd = manual_currency.round(residual_amount)

    def _prepare_reconciliation_single_partial(self, debit_values, credit_values, shadowed_aml_values=None):
        res = super()._prepare_reconciliation_single_partial(
            debit_values, credit_values, shadowed_aml_values
        )
        
        if 'partial_values' in res:
            partial_vals = res['partial_values']
            debit_aml = debit_values['aml']
            credit_aml = credit_values['aml']
            
            debit_rate = debit_aml.tax_today or debit_aml.move_id.tax_today or 0.0
            credit_rate = credit_aml.tax_today or credit_aml.move_id.tax_today or 0.0
            
            # Determinar la tasa correcta para convertir a USD
            # Prioridad 1: Si alguna línea es USD, usar su tasa (la del documento USD)
            # Prioridad 2: Usar la tasa más alta (la que tiene valor configurado, no default 1.0)
            # Prioridad 3: Si una es factura/NC, preferir su tasa sobre el pago
            
            if debit_aml.currency_id.name == 'USD':
                rate = debit_rate
            elif credit_aml.currency_id.name == 'USD':
                rate = credit_rate
            else:
                # Ambas son moneda de compañía (VEF)
                # Preferir la tasa que tenga valor real (> 1) sobre el default (1.0)
                if debit_rate > 1.0 and credit_rate <= 1.0:
                    rate = debit_rate
                elif credit_rate > 1.0 and debit_rate <= 1.0:
                    rate = credit_rate
                elif debit_rate > 1.0 and credit_rate > 1.0:
                    # Ambas tienen tasa, preferir la de la factura (debit para cliente)
                    # Verificar si debit es factura
                    if debit_aml.move_id.is_invoice(include_receipts=True):
                        rate = debit_rate
                    elif credit_aml.move_id.is_invoice(include_receipts=True):
                        rate = credit_rate
                    else:
                        rate = max(debit_rate, credit_rate)
                else:
                    # Ninguna tiene tasa válida, usar 1.0 (no hay conversión útil)
                    rate = 1.0
            
            if rate > 0:
                amount_usd = partial_vals['amount'] / rate
            else:
                amount_usd = 0.0
            
            partial_vals['amount_usd'] = abs(amount_usd)
        
        return res
