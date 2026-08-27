# -*- coding: utf-8 -*-


import json
from odoo import models, fields, api, _
from odoo.tools import (
    date_utils,
    formatLang,
)


class AccountMove(models.Model):
    _inherit = "account.move"

    amount_untaxed_usd = fields.Monetary(
        currency_field="currency_id_dif",
        string="Base imponible Ref.",
        store=True,
        compute="_amount_all_usd",
        digits="Dual_Currency",
    )
    amount_tax_usd = fields.Monetary(
        currency_field="currency_id_dif",
        string="Impuestos Ref.",
        store=True,
        readonly=True,
        digits="Dual_Currency",
        compute="_amount_all_usd",
    )
    amount_total_usd = fields.Monetary(
        currency_field="currency_id_dif",
        string="Total Ref.",
        store=True,
        readonly=True,
        compute="_amount_all_usd",
        digits="Dual_Currency",
        track_visibility="onchange",
    )
    amount_residual_usd = fields.Monetary(
        currency_field="currency_id_dif",
        compute="_amount_all_usd",
        string="Adeudado Ref.",
        readonly=True,
        digits="Dual_Currency",
        store=True,
    )
    invoice_payments_widget_usd = fields.Binary(
        groups="account.group_account_invoice,account.group_account_readonly",
        compute="_compute_payments_widget_reconciled_info_USD",
    )
    amount_untaxed_bs = fields.Monetary(
        currency_field="company_currency_id",
        string="Base imponible Bs.",
        store=True,
        compute="_amount_all_usd",
    )
    amount_tax_bs = fields.Monetary(
        currency_field="company_currency_id",
        string="Impuestos Bs.",
        store=True,
        readonly=True,
        compute="_amount_all_usd",
    )
    amount_total_bs = fields.Monetary(
        currency_field="company_currency_id",
        string="Total Bs.",
        store=True,
        readonly=True,
        compute="_amount_all_usd",
    )
    amount_exempt_bs = fields.Monetary(
        string="Exento Bs.",
        compute="_amount_all_usd",
        store=True,
        readonly=True,
        currency_field="company_currency_id",
    )
    amount_exempt_usd = fields.Monetary(
        string="Exento Ref.",
        compute="_amount_all_usd",
        store=True,
        readonly=True,
        currency_field="currency_id_dif",
    )

    # @api.depends(
    #     "line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched",
    #     "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual",
    #     "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency",
    #     "line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched",
    #     "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual",
    #     "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency",
    #     "line_ids.balance",
    #     "line_ids.currency_id",
    #     "line_ids.amount_currency",
    #     "line_ids.amount_residual",
    #     "line_ids.amount_residual_currency",
    #     "line_ids.payment_id.state",
    #     "line_ids.full_reconcile_id",
    # )
    # def _compute_amount(self):
    #     for move in self:
    #         super(AccountMove, self)._compute_amount()
    #         total_residual = 0.0
    #         for line in move.line_ids:
    #             if move.is_invoice(True):
    #                 if line.display_type == "payment_term":
    #                     # Residual amount.
    #                     total_residual += line.amount_residual_usd
    #         move.amount_residual_usd = total_residual

    @api.depends(
        "line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched",
        "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual",
        "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency",
        "line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched",
        "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual",
        "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency",
        "line_ids.balance",
        "line_ids.balance_usd",
        "line_ids.currency_id",
        "line_ids.amount_currency",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "line_ids.payment_id.state",
        "line_ids.full_reconcile_id",
        "state",
    )
    def _amount_all_usd(self):
        for move in self:
            amount_untaxed_bs, amount_untaxed_usd = 0.0, 0.0
            amount_exempt_bs, amount_exempt_usd = 0.0, 0.0
            amount_tax_bs, amount_tax_usd = 0.0, 0.0
            amount_total_bs, amount_total_usd = 0.0, 0.0
            amount_residual_usd = 0.0

            for line in move.line_ids:
                if move.is_invoice(True):
                    # === Invoices ===
                    if line.display_type == "tax" or (
                        line.display_type == "rounding" and line.tax_repartition_line_id
                    ):
                        # Tax amount.
                        amount_tax_bs += line.balance
                        amount_tax_usd += line.balance_usd
                        # Manejo para asignar el monto del impuesto SI no se asigna correctamente en la linea anterior a este comentario 'amount_tax_usd += line.balance_usd'
                        if not amount_tax_usd:
                            if move.currency_id.name in ['VED', 'VEF']:
                                amount_tax_usd += (line.balance / move.tax_today)
                        amount_total_bs += line.balance
                        amount_total_usd += line.balance_usd
                    elif line.display_type in ("product", "rounding"):
                        # Untaxed amount.
                        if all(t.appl_type in ("exento", "sdcf") for t in line.tax_ids):
                            amount_exempt_bs += line.balance
                            amount_exempt_usd += line.balance_usd
                        else:
                            amount_untaxed_bs += line.balance
                            amount_untaxed_usd += line.balance_usd
                        amount_total_bs += line.balance
                        amount_total_usd += line.balance_usd
                    elif line.display_type == "payment_term":
                        # Residual amount.
                        amount_residual_usd += line.amount_residual_usd
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        amount_total_bs += line.balance
                        amount_total_usd += line.balance_usd

            move.amount_exempt_bs = abs(amount_exempt_bs)
            move.amount_exempt_usd = abs(amount_exempt_usd)
            move.amount_tax_bs = abs(amount_tax_bs)
            move.amount_total_bs = abs(amount_total_bs)
            move.amount_residual_usd = abs(amount_residual_usd)

            move.amount_untaxed_usd = move.amount_untaxed / move.tax_today if move.tax_today else 0.0
            move.amount_tax_usd = move.amount_tax / move.tax_today if move.tax_today else 0.0
            move.amount_total_usd = move.amount_total / move.tax_today if move.tax_today else 0.0

            if move.amount_residual == 0:
                move.amount_residual_usd = 0.0
            else:
                move.amount_residual_usd = move.amount_residual / move.tax_today if move.tax_today else 0.0
            
            if move.currency_id.name == 'USD':
                move.amount_untaxed_bs = move.amount_untaxed * move.tax_today if move.tax_today else 0.0
                move.amount_tax_bs = move.amount_tax * move.tax_today if move.tax_today else 0.0
                move.amount_total_bs = move.amount_total * move.tax_today if move.tax_today else 0.0
                move.amount_residual_usd = move.amount_residual
                move.amount_total_usd = move.amount_total


            if move.currency_id.name in ('VEF', 'base.VES'):
                move.amount_untaxed_bs = move.amount_untaxed
                move.amount_tax_bs = move.amount_tax / move.tax_today if move.tax_today else 0.0
                move.amount_total_bs = move.amount_total / move.tax_today if move.tax_today else 0.0
                move.amount_residual_usd = move.amount_residual / move.tax_today if move.tax_today else 0.0
                move.amount_total_usd = move.amount_total / move.tax_today if move.tax_today else 0.0

           
    @api.depends("move_type", "line_ids.amount_residual_usd")
    def _compute_payments_widget_reconciled_info_USD(self):
        for move in self:
            payments_widget_vals = {
                "title": _("Less Payment"),
                "outstanding": False,
                "content": [],
            }
            total_pagado = 0
            if move.state == "posted" and move.is_invoice(include_receipts=True):
                reconciled_vals = []
                reconciled_partials = move._get_all_reconciled_invoice_partials_USD()

                for reconciled_partial in reconciled_partials:
                    counterpart_line = reconciled_partial["aml"]
                    if counterpart_line.move_id.ref:
                        reconciliation_ref = "%s (%s)" % (
                            counterpart_line.move_id.name,
                            counterpart_line.move_id.ref,
                        )
                    else:
                        reconciliation_ref = counterpart_line.move_id.name
                    if (
                        counterpart_line.amount_currency
                        and counterpart_line.currency_id
                        != counterpart_line.company_id.currency_id
                    ):
                        foreign_currency = counterpart_line.currency_id
                    else:
                        foreign_currency = False
                    total_pagado = total_pagado + float(reconciled_partial["amount"])
                    reconciled_vals.append(
                        {
                            "name": counterpart_line.name,
                            "journal_name": counterpart_line.journal_id.name,
                            "amount": reconciled_partial["amount"],
                            "currency_id": (
                                move.company_id.currency_id_dif.id
                                if move.company_id.currency_id_dif
                                else move.company_id.currency_id.id
                            ),
                            "date": counterpart_line.date,
                            "partial_id": reconciled_partial["partial_id"],
                            "account_payment_id": counterpart_line.payment_id.id,
                            "payment_method_name": counterpart_line.payment_id.payment_method_line_id.name,
                            "move_id": counterpart_line.move_id.id,
                            "ref": reconciliation_ref,
                            # these are necessary for the views to change depending on the values
                            "is_exchange": reconciled_partial["is_exchange"],
                            "amount_company_currency": formatLang(
                                self.env,
                                abs(counterpart_line.balance_usd),
                                currency_obj=counterpart_line.company_id.currency_id_dif,
                            ),
                            "amount_foreign_currency": foreign_currency
                            and formatLang(
                                self.env,
                                abs(counterpart_line.amount_currency),
                                currency_obj=foreign_currency,
                            ),
                        }
                    )
                payments_widget_vals["content"] = reconciled_vals

            if payments_widget_vals["content"]:
                move.invoice_payments_widget_usd = payments_widget_vals
                if total_pagado < move.amount_total_usd:
                    move.amount_residual_usd = move.amount_total_usd - total_pagado
                else:
                    move.amount_residual_usd = 0
                # if move.amount_residual_usd > 0:
                #     move.payment_state = 'partial'
                # else:
                #     move.payment_state = 'paid'
            else:
                move.amount_residual_usd = move.amount_total_usd
                move.invoice_payments_widget_usd = False

    @api.depends("move_type", "line_ids.amount_residual_usd")
    def _compute_payments_widget_reconciled_info_bs(self):
        for move in self:
            if move.state != "posted" or not move.is_invoice(include_receipts=True):
                move.invoice_payments_widget_bs = json.dumps(False)
                continue
            reconciled_vals = move._get_reconciled_info_JSON_values_bs()
            if reconciled_vals:
                info = {
                    "title": _("Less Payment"),
                    "outstanding": False,
                    "content": reconciled_vals,
                }
                move.invoice_payments_widget_bs = json.dumps(
                    info, default=date_utils.json_default
                )
            else:
                move.invoice_payments_widget_bs = json.dumps(False)

    def _get_reconciled_info_JSON_values_bs(self):
        self.ensure_one()
        foreign_currency = (
            self.currency_id
            if self.currency_id != self.company_id.currency_id
            else False
        )

        reconciled_vals = []
        pay_term_line_ids = self.line_ids.filtered(
            lambda line: line.account_id.account_type
            in ("asset_receivable", "liability_payable")
        )
        partials = pay_term_line_ids.mapped(
            "matched_debit_ids"
        ) + pay_term_line_ids.mapped("matched_credit_ids")
        for partial in partials:
            counterpart_lines = partial.debit_move_id + partial.credit_move_id

            counterpart_line = counterpart_lines.filtered(
                lambda line: line not in self.line_ids
            )

            if counterpart_line.credit > 0:
                amount = counterpart_line.credit
            else:
                amount = counterpart_line.debit

            ref = counterpart_line.move_id.name
            if counterpart_line.move_id.ref:
                ref += " (" + counterpart_line.move_id.ref + ")"

            reconciled_vals.append(
                {
                    "name": counterpart_line.name,
                    "journal_name": counterpart_line.journal_id.name,
                    "amount": partial.amount,
                    "currency": self.currency_id_dif.symbol,
                    "digits": [69, 2],
                    "position": self.currency_id_dif.position,
                    "date": counterpart_line.date,
                    "payment_id": counterpart_line.id,
                    "account_payment_id": counterpart_line.payment_id.id,
                    "payment_method_name": (
                        counterpart_line.payment_id.payment_method_id.name
                        if counterpart_line.journal_id.type == "bank"
                        else None
                    ),
                    "move_id": counterpart_line.move_id.id,
                    "ref": ref,
                }
            )
        return reconciled_vals

    def _get_all_reconciled_invoice_partials_USD(self):
        self.ensure_one()
        reconciled_lines = self.line_ids.filtered(
            lambda line: line.account_id.account_type
            in ("asset_receivable", "liability_payable")
        )
        if not reconciled_lines:
            return {}

        query = """
            SELECT
                part.id,
                part.exchange_move_id,
                part.amount_usd AS amount,
                part.credit_move_id AS counterpart_line_id
            FROM account_partial_reconcile part
            WHERE part.debit_move_id IN %s

            UNION ALL

            SELECT
                part.id,
                part.exchange_move_id,
                part.amount_usd AS amount,
                part.debit_move_id AS counterpart_line_id
            FROM account_partial_reconcile part
            WHERE part.credit_move_id IN %s
        """
        self._cr.execute(query, [tuple(reconciled_lines.ids)] * 2)

        partial_values_list = []
        counterpart_line_ids = set()
        exchange_move_ids = set()
        for values in self._cr.dictfetchall():
            partial_values_list.append(
                {
                    "aml_id": values["counterpart_line_id"],
                    "partial_id": values["id"],
                    "amount": values["amount"],
                    "currency": self.currency_id,
                }
            )
            counterpart_line_ids.add(values["counterpart_line_id"])
            if values["exchange_move_id"]:
                exchange_move_ids.add(values["exchange_move_id"])

        if exchange_move_ids:
            query = """
                SELECT
                    part.id,
                    part.credit_move_id AS counterpart_line_id
                FROM account_partial_reconcile part
                JOIN account_move_line credit_line ON credit_line.id = part.credit_move_id
                WHERE credit_line.move_id IN %s AND part.debit_move_id IN %s

                UNION ALL

                SELECT
                    part.id,
                    part.debit_move_id AS counterpart_line_id
                FROM account_partial_reconcile part
                JOIN account_move_line debit_line ON debit_line.id = part.debit_move_id
                WHERE debit_line.move_id IN %s AND part.credit_move_id IN %s
            """
            self._cr.execute(
                query, [tuple(exchange_move_ids), tuple(counterpart_line_ids)] * 2
            )

            for values in self._cr.dictfetchall():
                counterpart_line_ids.add(values["counterpart_line_id"])
                partial_values_list.append(
                    {
                        "aml_id": values["counterpart_line_id"],
                        "partial_id": values["id"],
                        "currency": self.company_id.currency_id,
                    }
                )

        counterpart_lines = {
            x.id: x for x in self.env["account.move.line"].browse(counterpart_line_ids)
        }
        for partial_values in partial_values_list:
            partial_values["aml"] = counterpart_lines[partial_values["aml_id"]]
            partial_values["is_exchange"] = (
                partial_values["aml"].move_id.id in exchange_move_ids
            )
            if partial_values["is_exchange"]:
                partial_values["amount"] = abs(partial_values["aml"].balance_usd)

        return partial_values_list

    # def js_assign_outstanding_line(self, line_id):
    #     """Called by the 'payment' widget to reconcile a suggested journal item to the present
    #     invoice.

    #     :param line_id: The id of the line to reconcile with the current invoice.
    #     """
    #     self.ensure_one()
    #     lines = self.env["account.move.line"].browse(line_id)
    #     l = self.line_ids.filtered(
    #         lambda line: line.account_id == lines[0].account_id and not line.reconciled
    #     )
    #     if abs(lines[0].amount_residual) == 0 and abs(lines[0].amount_residual_usd) > 0:
    #         if l.full_reconcile_id:
    #             l.full_reconcile_id.unlink()
    #         partial = self.env["account.partial.reconcile"].create(
    #             [
    #                 {
    #                     "amount": 0,
    #                     "amount_usd": (
    #                         l.move_id.amount_residual_usd
    #                         if abs(lines[0].amount_residual_usd)
    #                         > l.move_id.amount_residual_usd
    #                         else abs(lines[0].amount_residual_usd)
    #                     ),
    #                     "debit_amount_currency": 0,
    #                     "credit_amount_currency": 0,
    #                     "debit_move_id": l.id,
    #                     "credit_move_id": line_id,
    #                 }
    #             ]
    #         )
    #         return (lines + l).reconcile()
    #     else:
    #         results = (lines + l).reconcile()
    #         if "partials" in results:
    #             monto_usd = 0
    #             if abs(lines[0].amount_residual_usd) > 0:

    #                 total_residual_usd = 0
    #                 for line in self.line_ids:
    #                     if line.display_type == "payment_term":
    #                         # Residual amount.
    #                         total_residual_usd += abs(line.amount_residual_usd)
    #                 if abs(lines[0].amount_residual_usd) > total_residual_usd:
    #                     monto_usd = total_residual_usd
    #                 else:
    #                     monto_usd = abs(lines[0].amount_residual_usd)

    #             results["partials"].sudo().amount_usd = monto_usd
    #             self.env.cr.commit()
    #             lines[0].sudo()._compute_amount_residual_usd()
    #             l.sudo()._compute_amount_residual_usd()
    #         return results

    def _compute_payments_widget_to_reconcile_info(self):
        for move in self:
            move.invoice_outstanding_credits_debits_widget = False
            move.invoice_has_outstanding = False

            if (
                move.state != "posted"
                or move.payment_state not in ("not_paid", "partial")
                or not move.is_invoice(include_receipts=True)
            ):
                continue

            pay_term_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type
                in ("asset_receivable", "liability_payable")
            )

            domain = [
                ("account_id", "in", pay_term_lines.account_id.ids),
                ("parent_state", "=", "posted"),
                ("partner_id", "=", move.commercial_partner_id.id),
                ("reconciled", "=", False),
                "|",
                "|",
                ("amount_residual", "!=", 0.0),
                ("amount_residual_usd", "!=", 0.0),
                ("amount_residual_currency", "!=", 0.0),
            ]

            payments_widget_vals = {
                "outstanding": True,
                "content": [],
                "move_id": move.id,
            }

            if move.is_inbound():
                domain.append(("balance", "<", 0.0))
                payments_widget_vals["title"] = _("Outstanding credits")
            else:
                domain.append(("balance", ">", 0.0))
                payments_widget_vals["title"] = _("Outstanding debits")

            for line in self.env["account.move.line"].search(domain):
                if line.debit == 0 and line.credit == 0 and not line.full_reconcile_id:
                    if abs(line.amount_residual_usd) > 0:
                        payments_widget_vals["content"].append(
                            {
                                "journal_name": line.ref or line.move_id.name,
                                "amount": 0,
                                "amount_usd": abs(line.amount_residual_usd),
                                "currency_id": move.currency_id.id,
                                "currency_id_dif": move.currency_id_dif.id,
                                "id": line.id,
                                "move_id": line.move_id.id,
                                "date": fields.Date.to_string(line.date),
                                "account_payment_id": line.payment_id.id,
                            }
                        )
                        continue
                if line.currency_id == move.currency_id:
                    # Same foreign currency.
                    amount = abs(line.amount_residual_currency)
                    amount_usd = abs(line.amount_residual_usd)
                else:
                    # Different foreign currencies.
                    amount = line.company_currency_id.with_context(edit_trm=line.move_id.edit_trm, tax_today=line.move_id.tax_today)._convert(
                        abs(line.amount_residual),
                        move.currency_id,
                        move.company_id,
                        line.date,
                    )
                    amount_usd = abs(line.amount_residual_usd)

                if move.currency_id.is_zero(amount) and amount_usd == 0:
                    continue

                payments_widget_vals["content"].append(
                    {
                        "journal_name": line.ref or line.move_id.name,
                        "amount": amount,
                        "amount_usd": amount_usd,
                        "currency_id": move.currency_id.id,
                        "currency_id_dif": move.currency_id_dif.id,
                        "id": line.id,
                        "move_id": line.move_id.id,
                        "date": fields.Date.to_string(line.date),
                        "account_payment_id": line.payment_id.id,
                    }
                )

            if not payments_widget_vals["content"]:
                continue
            move.invoice_outstanding_credits_debits_widget = payments_widget_vals
            move.invoice_has_outstanding = True
