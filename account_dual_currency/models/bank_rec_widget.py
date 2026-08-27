# -*- coding: utf-8 -*-
import logging
import ast
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class BankRecWidget(models.Model):
    _inherit = 'bank.rec.widget'

    def _action_validate(self):
        """Intercept validation of bank reconciliation in Odoo 17 to apply
        the custom exchange rate from the payment to the bank statement's
        journal entry BEFORE they are reconciled.
        """
        for widget in self:
            st_line = widget.st_line_id
            if not st_line or not st_line.move_id:
                continue

            # In Odoo 17, bank.rec.widget.line holds the selected AMLs in source_aml_id.
            try:
                # Find any AML among the selected lines that belongs to a payment with a custom rate.
                payment_amls = widget.line_ids.mapped('source_aml_id').filtered(
                    lambda l: l.move_id.payment_id and l.move_id.payment_id.custom_rate
                )
            except Exception as e:
                _logger.warning("[BANK-RECON-WIDGET] Error accessing source_aml_id: %s", e)
                payment_amls = self.env['account.move.line']

            if payment_amls:
                payment_rate = payment_amls[0].move_id.payment_id.tax_today
                if payment_rate:
                    _logger.info("[BANK-RECON-WIDGET] Found payment with custom rate %.4f for statement line %s", payment_rate, st_line.id)
                    
                    company_currency = widget.company_id.currency_id
                    lines_to_remove = self.env['bank.rec.widget.line']

                    # 1. Odoo 17 guarda en memoria las líneas (bank.rec.widget.line) con
                    # debit y credit precalculados a la tasa del día. Al validar, las 
                    # vuelca directamente a BD, por lo que reescribimos estos valores en memoria.
                    for w_line in widget.line_ids:
                        flag = getattr(w_line, 'flag', None)
                        if flag in ('exchange_diff', 'auto_balance'):
                            # Esta línea ya no es necesaria porque estamos forzando la misma tasa.
                            # Si la dejamos, el asiento se desbalancea.
                            w_line.debit = 0.0
                            w_line.credit = 0.0
                            if hasattr(w_line, 'balance'):
                                w_line.balance = 0.0
                            lines_to_remove |= w_line
                            _logger.info("[BANK-RECON-WIDGET] Marcando para eliminar línea %s: %s", flag, w_line.id)
                            continue

                        # Si no hay moneda extranjera o es igual a la compañía, no hay conversión
                        if not w_line.amount_currency or w_line.currency_id == company_currency:
                            continue
                        
                        # Calculamos el balance correcto usando la tasa del pago
                        ac = w_line.amount_currency
                        new_balance = company_currency.round(ac / payment_rate)

                        # Actualizamos débito y crédito del widget
                        if new_balance > 0:
                            w_line.debit = new_balance
                            w_line.credit = 0.0
                        else:
                            w_line.debit = 0.0
                            w_line.credit = abs(new_balance)
                            
                        # Actualizamos balance por si el widget lo usa internamente
                        if hasattr(w_line, 'balance'):
                            w_line.balance = new_balance
                        
                        _logger.info("[BANK-RECON-WIDGET] Modificando widget line: debit=%.2f credit=%.2f", w_line.debit, w_line.credit)

                    # Eliminar las líneas de diferencial cambiario del widget en memoria
                    if lines_to_remove:
                        widget.line_ids -= lines_to_remove
                        _logger.info("[BANK-RECON-WIDGET] Líneas de exchange_diff removidas del widget en memoria.")

                    # 2. Asegurar que el account.move guarde la marca de edit_trm y tax_today
                    try:
                        with self.env.cr.savepoint():
                            st_line.move_id.write({
                                'edit_trm': True,
                                'tax_today': payment_rate,
                            })
                    except Exception as e:
                        _logger.warning("[BANK-RECON-WIDGET] Could not write to move via ORM: %s", e)

                    # Pasamos el contexto para asegurar que cualquier recálculo futuro
                    # dentro de la misma transacción use esta tasa.
                    return super(BankRecWidget, widget.with_context(
                        edit_trm=True, 
                        tax_today=payment_rate,
                        check_move_validity=False
                    ))._action_validate()

        return super()._action_validate()

    def _prepare_embedded_views_data(self):
        res = super()._prepare_embedded_views_data()
        if 'amls' in res and 'dynamic_filters' in res['amls']:
            for filter_data in res['amls']['dynamic_filters']:
                if filter_data.get('domain'):
                    try:
                        # Parse string domain to Python list of tuples
                        domain = ast.literal_eval(filter_data['domain'])
                        new_domain = []
                        for leaf in domain:
                            if isinstance(leaf, tuple) and len(leaf) == 3 and leaf[0] == 'account_id' and leaf[1] == 'in':
                                val = leaf[2]
                                if isinstance(val, (tuple, list, set)):
                                    # Convert 1-element tuple or set/list to standard list so JS formats it correctly
                                    new_domain.append((leaf[0], leaf[1], list(val)))
                                else:
                                    new_domain.append(leaf)
                            else:
                                new_domain.append(leaf)
                        filter_data['domain'] = str(new_domain)
                    except Exception as e:
                        _logger.error("[BANK-RECON-WIDGET] Error converting dynamic filter domain: %s", e)
        return res

