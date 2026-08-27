from odoo import models, fields, api
from collections import defaultdict
from datetime import timedelta


class CommissionSettlementWizard(models.TransientModel):
    _name = "commission.settlement.wizard"
    _description = "Asistente de Liquidación de Comisiones"

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía para la cual se calcularán las comisiones.",
    )
    date_from = fields.Date(
        string="Fecha Inicio", required=True, help="Inicio del periodo a calcular."
    )
    date_to = fields.Date(
        string="Fecha Fin", required=True, help="Fin del periodo a calcular."
    )
    min_price_penalty_pct = fields.Float(
        string="Penalización Precio Mínimo (%)",
        default=0.0,
        help="Porcentaje que se descontará de la comisión en ventas con precio mínimo.",
    )

    def _get_mora_rule(self, salesperson, company, days_overdue, is_credit):
        """
        Busca en la Matriz de Cobranza (commission.collection.matrix) el factor
        de comisión a reconocer según los días de retraso post-vencimiento.

        Prioridad:
        1. Regla especial por vendedor (user_id = salesperson.id)
        2. Regla general por compañía (user_id = False, company_id = company.id)
        """
        payment_cond = "credit" if is_credit else "cash"

        # 1. Regla especial por vendedor
        vendor_matrix = self.env["commission.collection.matrix"].search(
            [
                ("company_id", "=", company.id),
                ("user_id", "=", salesperson.id),
                ("days_from", "<=", days_overdue),
                ("days_to", ">=", days_overdue),
                ("payment_type", "in", ["all", payment_cond]),
            ],
            limit=1,
            order="days_from desc",
        )
        if vendor_matrix:
            return vendor_matrix.commission_factor_pct / 100.0

        # 2. Regla general por compañía
        company_matrix = self.env["commission.collection.matrix"].search(
            [
                ("company_id", "=", company.id),
                ("user_id", "=", False),
                ("days_from", "<=", days_overdue),
                ("days_to", ">=", days_overdue),
                ("payment_type", "in", ["all", payment_cond]),
            ],
            limit=1,
            order="days_from desc",
        )
        if company_matrix:
            return company_matrix.commission_factor_pct / 100.0

        # 3. Fallback binario tradicional si no hay matriz configurada
        grace_days = company.commission_grace_days
        if days_overdue > grace_days:
            return 0.0
        return 1.0

    def action_generate_settlement(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        credit_threshold = company.commission_credit_threshold
        payment_tolerance = company.commission_payment_tolerance / 100.0
        strict_full_payment = company.commission_strict_full_payment
        use_pricelist_mapping = company.commission_use_pricelist_mapping
        cash_rate = company.commission_cash_rate / 100.0
        credit_rate = company.commission_credit_rate / 100.0
        use_targets = company.commission_use_targets
        use_margin = company.commission_base_type == "margin"
        min_target_pct = (company.commission_min_target_pct or 80.0) / 100.0
        max_target_cap = (company.commission_max_target_cap or 150.0) / 100.0

        # 1. Deductions
        fixed_expenses = self.env["commission.fixed.expense"].search(
            [("date_from", ">=", self.date_from), ("date_to", "<=", self.date_to)]
        )
        deduction_pct = sum(fixed_expenses.mapped("deduction_percentage"))

        # 2. Payments
        payments = self.env["account.payment"].search(
            [
                ("company_id", "=", company.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("state", "in", ["posted", "in_process"]),
            ]
        )

        sales_data = defaultdict(
            lambda: {
                "name": "",
                "company_id": False,
                "total_collected": 0.0,
                "total_collected_gross": 0.0,
                "total_invoiced": 0.0,
                "lines": [],
                "country": "",
                "vendor_type": False,
                "target": 0.0,
                "is_manager": False,
                "manager_role": False,
                "total_comm": 0.0,
            }
        )
        country_totals = defaultdict(float)
        items_to_process = []
        processed_pairs = set()

        for payment in payments:
            reconciled_invoices = (
                payment.reconciled_invoice_ids or payment.reconciled_bill_ids
            )
            for invoice in reconciled_invoices:
                if invoice.move_type == "out_invoice" and invoice.company_id == company:
                    p_move_id = payment.move_id.id if payment.move_id else payment.id
                    pair_key = (p_move_id, invoice.id)
                    if pair_key not in processed_pairs:
                        processed_pairs.add(pair_key)
                        items_to_process.append((payment.date, payment.amount, invoice, payment))

        # Also collect bank move entries reconciled with out_invoices
        move_entries = self.env["account.move"].search(
            [
                ("company_id", "=", company.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("state", "=", "posted"),
                ("move_type", "=", "entry"),
            ]
        )
        for entry in move_entries:
            for line in entry.line_ids.filtered(
                lambda l: l.account_id.account_type == "asset_receivable"
            ):
                for partial in line.matched_debit_ids + line.matched_credit_ids:
                    c_line = (
                        partial.debit_move_id
                        if partial.credit_move_id == line
                        else partial.credit_move_id
                    )
                    inv = c_line.move_id
                    if inv.move_type == "out_invoice" and inv.company_id == company and inv.state == "posted":
                        pair_key = (entry.id, inv.id)
                        if pair_key not in processed_pairs:
                            processed_pairs.add(pair_key)
                            items_to_process.append(
                                (entry.date, partial.amount, inv, entry)
                            )

        if strict_full_payment:
            current_invoices = {item[2] for item in items_to_process}
            for inv in current_invoices:
                tolerance_amount = inv.amount_total * payment_tolerance
                if inv.amount_residual <= tolerance_amount:
                    for partial in inv._get_reconciled_partials():
                        c_line = (
                            partial.credit_move_id
                            if partial.debit_move_id.move_id == inv
                            else partial.debit_move_id
                        )
                        pay_move = c_line.move_id
                        if pay_move.state == "posted":
                            pay_obj = self.env["account.payment"].search(
                                [("move_id", "=", pay_move.id)], limit=1
                            ) or pay_move
                            pay_date = pay_obj.date if hasattr(pay_obj, "date") else pay_move.date
                            if pay_date and self.date_from <= pay_date <= self.date_to:
                                pair_key = (pay_move.id, inv.id)
                                if pair_key not in processed_pairs:
                                    processed_pairs.add(pair_key)
                                    items_to_process.append((pay_date, partial.amount, inv, pay_obj))

        for pay_date, pay_amount, invoice, pay_object in items_to_process:
            if pay_date and pay_date > self.date_to:
                continue

            salesperson = invoice.invoice_user_id
            if not salesperson:
                continue

            # Identify Cash or Credit
            is_credit = False
            payment_term = invoice.invoice_payment_term_id
            if payment_term:
                if hasattr(payment_term, "is_contado"):
                    is_credit = not payment_term.is_contado
                else:
                    term_name = (payment_term.name or "").lower()
                    if (
                        "crédito" in term_name
                        or "credito" in term_name
                        or "días" in term_name
                        or "dias" in term_name
                    ):
                        is_credit = True

            # Determine vendor type first
            vendor_type = salesperson.vendor_type_id

            # Calculate days overdue post due date
            days_overdue = 0
            if invoice.invoice_date_due and pay_date:
                days_overdue = (pay_date - invoice.invoice_date_due).days
                if days_overdue < 0:
                    days_overdue = 0

                # Check mora rule from Matriz de Cobranza
                mora_factor = self._get_mora_rule(
                    salesperson, company, days_overdue, is_credit
                )

                is_valid_for_commission = True
                exclude_reason = ""
                if mora_factor == 0.0 and not invoice.manual_commission_override:
                    is_valid_for_commission = False
                    exclude_reason = (
                        f"Factura Vencida ({days_overdue} días de mora — Factor 0%)."
                    )

                # Strict Full Payment Logic as of date_to
                tolerance_amount = invoice.amount_total * payment_tolerance
                total_paid_upto_date = 0.0
                for aml in invoice.line_ids:
                    for partial in aml.matched_credit_ids + aml.matched_debit_ids:
                        c_line = (
                            partial.credit_move_id
                            if partial.debit_move_id.move_id == invoice
                            else partial.debit_move_id
                        )
                        p_date = c_line.date or c_line.move_id.date
                        if p_date and p_date <= self.date_to:
                            total_paid_upto_date += (
                                partial.debit_amount_currency or partial.credit_amount_currency or partial.amount
                            )
                is_fully_paid = (invoice.amount_total - total_paid_upto_date) <= tolerance_amount

                if (
                    strict_full_payment
                    and is_credit
                    and invoice.amount_total > credit_threshold
                ):
                    if not is_fully_paid:
                        is_valid_for_commission = False
                        exclude_reason = f"Pendiente: Saldo residual a la fecha fin ({invoice.amount_total - total_paid_upto_date:.2f}) mayor a tolerancia."

                # Calculate the actual amount paid to this invoice by this payment
                amount_paid_in_invoice_currency = 0.0
                p_move = pay_object.move_id if hasattr(pay_object, "move_id") else pay_object
                p_id = pay_object if (hasattr(pay_object, "_name") and pay_object._name == "account.payment") else False

                for aml in invoice.line_ids:
                    for partial in aml.matched_credit_ids:
                        if (p_id and partial.credit_move_id.payment_id == p_id) or (p_move and partial.credit_move_id.move_id == p_move):
                            amount_paid_in_invoice_currency += (
                                partial.debit_amount_currency or partial.amount
                            )
                    for partial in aml.matched_debit_ids:
                        if (p_id and partial.debit_move_id.payment_id == p_id) or (p_move and partial.debit_move_id.move_id == p_move):
                            amount_paid_in_invoice_currency += (
                                partial.credit_amount_currency or partial.amount
                            )

                if amount_paid_in_invoice_currency == 0.0 and pay_amount:
                    amount_paid_in_invoice_currency = pay_amount

                inv_ratio = 1.0
                if invoice.amount_total != 0:
                    inv_ratio = amount_paid_in_invoice_currency / invoice.amount_total

                invoice_collected_amount = amount_paid_in_invoice_currency
                invoice_collected_amount_comp = invoice_collected_amount
                if invoice.currency_id and invoice.currency_id != company.currency_id:
                    invoice_collected_amount_comp = invoice.currency_id._convert(
                        invoice_collected_amount,
                        company.currency_id,
                        company,
                        pay_date or invoice.date or fields.Date.today(),
                    )

                ratio = inv_ratio

                if (
                    strict_full_payment
                    and is_credit
                    and invoice.amount_total > credit_threshold
                ):
                    if not is_fully_paid:
                        is_valid_for_commission = False
                        exclude_reason = f"Pendiente: Saldo residual ({invoice.amount_residual}) mayor a tolerancia."

                # Contract Lookup (Historical Data)
                contract = self.env["hr.contract"].sudo().search(
                    [
                        ("employee_id.user_id", "=", salesperson.id),
                        ("state", "in", ["open", "close"]),
                        ("date_start", "<=", invoice.invoice_date or invoice.date),
                        "|",
                        ("date_end", "=", False),
                        ("date_end", ">=", invoice.invoice_date or invoice.date),
                    ],
                    limit=1,
                )

                vendor_type = salesperson.vendor_type_id
                if contract and contract.commission_vendor_type_id:
                    vendor_type = contract.commission_vendor_type_id

                country_code = vendor_type.country if (vendor_type and vendor_type.country) else ("PAN" if (company.country_id and company.country_id.code == "PA") or "Panama" in company.name else "VEN")

                sp_key = salesperson

                sales_data[sp_key]["name"] = salesperson.name
                sales_data[sp_key]["company_id"] = company.id
                sales_data[sp_key]["country"] = country_code
                sales_data[sp_key]["vendor_type"] = vendor_type
                sales_data[sp_key]["is_manager"] = vendor_type.is_manager if vendor_type else False
                sales_data[sp_key]["manager_role"] = vendor_type.manager_role if vendor_type else False

                first_line_for_payment = True
                for line in invoice.invoice_line_ids:
                    ratio = inv_ratio

                    price_subtotal = line.price_subtotal
                    mapped_pricelist = False

                    if use_pricelist_mapping:
                        so = False
                        if hasattr(line, "sale_line_ids") and line.sale_line_ids:
                            so = line.sale_line_ids[0].order_id
                        elif invoice.invoice_origin:
                            so = self.env["sale.order"].search(
                                [("name", "=", invoice.invoice_origin)], limit=1
                            )

                        if (
                            so
                            and so.pricelist_id
                            and so.pricelist_id.commission_mapped_pricelist_id
                        ):
                            mapped_pricelist = (
                                so.pricelist_id.commission_mapped_pricelist_id
                            )

                    if mapped_pricelist:
                        price_unit = mapped_pricelist._get_product_price(
                            product=line.product_id,
                            quantity=line.quantity,
                            uom=line.product_uom_id,
                            date=invoice.invoice_date
                            or invoice.date
                            or fields.Date.today(),
                        )
                        if price_unit > 0:
                            price_subtotal = price_unit * line.quantity
                            if line.discount:
                                price_subtotal = price_subtotal * (
                                    1 - line.discount / 100.0
                                )
                        else:
                            mapped_pricelist = False

                    line_currency = (
                        mapped_pricelist.currency_id
                        if mapped_pricelist
                        else invoice.currency_id
                    )

                    product = line.product_id.with_company(self.env.company)
                    line_cost = product.standard_price if product else 0.0
                    total_cost = line_cost * line.quantity

                    if (
                        line_currency
                        and line_currency != self.env.company.currency_id
                    ):
                        total_cost = self.env.company.currency_id._convert(
                            total_cost,
                            line_currency,
                            self.env.company,
                            invoice.date or fields.Date.today(),
                        )

                    if use_margin:
                        line_comm_base = price_subtotal - total_cost
                    else:
                        line_comm_base = price_subtotal

                    comm_base_portion = line_comm_base * ratio
                    company_currency = self.env.company.currency_id

                    comm_base_comp = comm_base_portion
                    if line_currency and line_currency != company_currency:
                        comm_base_comp = line_currency._convert(
                            comm_base_portion,
                            company_currency,
                            self.env.company,
                            pay_date or invoice.date or fields.Date.today(),
                        )

                    country_totals[vendor_type.country] += comm_base_comp

                    line_data = {
                        "date": pay_date,
                        "client_id": invoice.partner_id.id,
                        "product_id": line.product_id.id,
                        "invoice_id": invoice.id,
                        "invoice_date": invoice.date or invoice.invoice_date,
                        "invoice_total": invoice.amount_total,
                        "amount_paid": comm_base_comp,
                        "actual_amount_paid": invoice_collected_amount_comp
                        if first_line_for_payment
                        else 0.0,
                        "original_amount": comm_base_portion,
                        "original_currency": line_currency,
                        "quantity": line.quantity * ratio,
                        "cost": line_cost * line.quantity * ratio,
                        "commission_pct": 0.0,
                        "deduction_pct": 0.0
                        if not is_valid_for_commission
                        else deduction_pct,
                        "penalty_pct": 0.0,
                        "commission_amount": 0.0,
                        "profitability": 0.0,
                        "is_min_price_sale": line.is_min_price_sale,
                        "is_excluded": not is_valid_for_commission,
                        "is_overdue": days_overdue > 0,
                        "days_overdue": days_overdue,
                        "mora_penalty_factor": mora_factor,
                        "exclude_reason": exclude_reason,
                        "payment_term": invoice.invoice_payment_term_id.name or "",
                        "invoice_payment_term_id": invoice.invoice_payment_term_id.id
                        if invoice.invoice_payment_term_id
                        else False,
                        "is_credit": is_credit,
                    }

                    sales_data[sp_key]["total_collected_gross"] += comm_base_comp
                    if not is_valid_for_commission:
                        sales_data[sp_key]["lines"].append(line_data)
                        first_line_for_payment = False
                        continue

                    sales_data[sp_key]["lines"].append(line_data)
                    sales_data[sp_key]["total_collected"] += comm_base_comp
                    first_line_for_payment = False

                    inv_date = invoice.date or invoice.invoice_date
                    due_date = invoice.invoice_date_due or inv_date
                    days_credit = (
                        (due_date - inv_date).days if due_date and inv_date else 0
                    )
                    if days_credit < 0:
                        days_credit = 0

                    days_paid = 0
                    if pay_date and inv_date:
                        days_paid = (pay_date - inv_date).days
                        if days_paid < 0:
                            days_paid = 0

                    if sales_data[sp_key]["lines"]:
                        sales_data[sp_key]["lines"][-1].update(
                            {
                                "invoice_date": inv_date,
                                "invoice_date_due": due_date,
                                "days_credit": days_credit,
                                "days_paid": days_paid,
                                "days_overdue": days_overdue,
                            }
                        )

        # 2b. Calculate Sales (Invoiced) in the period for Meta Achievement
        invoiced_invoices = self.env["account.move"].search(
            [
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
                ("invoice_date", ">=", self.date_from),
                ("invoice_date", "<=", self.date_to),
                ("company_id", "=", company.id),
            ]
        )

        for inv in invoiced_invoices:
            sp = inv.invoice_user_id
            if not sp or not (sp.is_vendor or sp.vendor_type_id):
                continue

            if sp not in sales_data:
                vt = sp.vendor_type_id
                country_code = vt.country if (vt and vt.country) else ("PAN" if company.country_id and company.country_id.code == "PA" or "Panama" in company.name else "VEN")
                sales_data[sp].update(
                    {
                        "name": sp.name,
                        "country": country_code,
                        "vendor_type": vt,
                        "is_manager": vt.is_manager if vt else False,
                        "manager_role": vt.manager_role if vt else False,
                    }
                )

            for line in inv.invoice_line_ids:
                price_subtotal = line.price_subtotal
                if inv.move_type == "out_refund":
                    price_subtotal = -abs(price_subtotal)
                line_currency = inv.currency_id

                if use_margin:
                    product = line.product_id.with_company(self.env.company)
                    line_cost = product.standard_price if product else 0.0
                    total_cost = line_cost * line.quantity

                    if line_currency and line_currency != company.currency_id:
                        total_cost = company.currency_id._convert(
                            total_cost,
                            line_currency,
                            company,
                            inv.invoice_date or fields.Date.today(),
                        )
                    line_base = price_subtotal - total_cost
                else:
                    line_base = price_subtotal

                line_base_comp = line_base
                if line_currency and line_currency != company.currency_id:
                    line_base_comp = line_currency._convert(
                        line_base,
                        company.currency_id,
                        company,
                        inv.invoice_date or fields.Date.today(),
                    )

                sales_data[sp]["total_invoiced"] += line_base_comp

        # 3. Ensure Managers are included
        managers = self.env["res.users"].sudo().search(
            [("vendor_type_id.is_manager", "=", True), ("active", "=", True)]
        )

        for manager in managers:
            if manager not in sales_data:
                vt = manager.vendor_type_id
                sales_data[manager].update(
                    {
                        "name": manager.name,
                        "country": vt.country,
                        "vendor_type": vt,
                        "is_manager": vt.is_manager,
                        "manager_role": vt.manager_role,
                    }
                )

        target_mode = company.commission_target_mode or "individual"
        global_target = 0.0

        targets = self.env["commission.monthly.target"].search(
            [("date_from", ">=", self.date_from), ("date_from", "<=", self.date_to)]
        )
        target_map = {}
        for t in targets:
            converted = t.amount_target
            if t.currency_id and t.currency_id != self.env.company.currency_id:
                converted = t.currency_id._convert(
                    converted,
                    self.env.company.currency_id,
                    self.env.company,
                    self.date_to or fields.Date.today(),
                )

            if target_mode == "branch" and t.target_type == "branch":
                global_target += converted

            if t.vendedor_id:
                target_map[t.vendedor_id.id] = {
                    "amount": converted,
                    "amount_prospect": t.amount_target,
                    "currency_prospect": t.currency_id.id,
                }

        matrix = self.env["commission.matrix"].search([])
        global_achievement_rate = 0.0
        if target_mode == "branch":
            global_invoiced = sum(d["total_invoiced"] for d in sales_data.values())
            if global_target > 0:
                global_achievement_rate = global_invoiced / global_target

        # 4. Create Settlements
        created_settlements = self.env["commission.settlement"]

        for salesperson, data in sales_data.items():
            target_data = {}
            if target_mode == "branch":
                achievement_rate = global_achievement_rate
                target = global_target
            else:
                target_data = target_map.get(salesperson.partner_id.id, {})
                target = target_data.get("amount", 0.0)
                achievement_rate = 0.0
                if target > 0:
                    achievement_rate = data["total_invoiced"] / target

            # CAP: Limit achievement rate to maximum cap (e.g. 150%)
            achievement_rate = min(achievement_rate, max_target_cap)

            # MIN TARGET CHECK: If sales target is set and achievement is below min_target_pct (e.g. 80%), disable commissions
            is_below_min_target = False
            if target > 0 and achievement_rate < min_target_pct:
                is_below_min_target = True

            vendor_type = salesperson.vendor_type_id
            contract = self.env["hr.contract"].sudo().search(
                [
                    ("employee_id.user_id", "=", salesperson.id),
                    ("state", "in", ["open", "close"]),
                    ("date_start", "<=", self.date_to),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">=", self.date_from),
                ],
                limit=1,
            )

            if contract and contract.commission_vendor_type_id:
                vendor_type = contract.commission_vendor_type_id

            applicable_rules = []
            if vendor_type:
                for m in matrix:
                    if m.vendor_type_id == vendor_type:
                        try:
                            threshold = float(m.target_achievement_pct)
                            applicable_rules.append(
                                (threshold, m.commission_percentage)
                            )
                        except ValueError:
                            continue
                applicable_rules.sort(key=lambda x: x[0], reverse=True)

            def get_rate_for_ach(ach):
                if is_below_min_target:
                    return 0.0

                if contract and contract.fix_commission_rate > 0.0:
                    return contract.fix_commission_rate

                use_targets = self.env.company.commission_use_targets
                if not use_targets:
                    if applicable_rules:
                        return applicable_rules[-1][1]
                    return 0.0

                for threshold, rate in applicable_rules:
                    if ach >= threshold:
                        return rate
                return 0.0

            base_rate_salesperson = get_rate_for_ach(achievement_rate)

            # Pre-fetch historical closed targets
            if target_mode == "branch":
                hist_targets = self.env["commission.monthly.target"].search(
                    [("state", "=", "done"), ("target_type", "=", "branch")]
                )
            else:
                hist_targets = self.env["commission.monthly.target"].search(
                    [
                        ("state", "=", "done"),
                        ("vendedor_id", "=", salesperson.partner_id.id),
                    ]
                )
            snapshot_map = {}
            for t in hist_targets:
                if t.date_from:
                    month_key = t.date_from.replace(day=1)
                    snapshot_map[month_key] = t.achievement_percentage / 100.0

            month_names = {
                1: "Enero",
                2: "Febrero",
                3: "Marzo",
                4: "Abril",
                5: "Mayo",
                6: "Junio",
                7: "Julio",
                8: "Agosto",
                9: "Septiembre",
                10: "Octubre",
                11: "Noviembre",
                12: "Diciembre",
            }
            month = self.date_from.month
            year = self.date_from.year
            month_name = month_names.get(month, "")

            settlement_name = f"Comisiones {month_name} {year} - {salesperson.name}"

            settlement_vals = {
                "name": settlement_name,
                "salesperson_id": salesperson.id,
                "company_id": company.id,
                "currency_id": company.currency_id.id,
                "date_from": self.date_from,
                "date_to": self.date_to,
                "target_amount": target,
                "total_collected": data["total_collected"],
                "total_invoiced": data["total_invoiced"],
                "achievement_pct": achievement_rate,
                "min_price_penalty_pct": self.min_price_penalty_pct,
                "target_amount_prospect": target_data.get("amount_prospect", 0.0),
                "target_currency_id": target_data.get("currency_prospect", False),
            }

            lines_to_create = []
            total_commission = 0.0

            for line in data["lines"]:
                line_is_excluded = line.get("is_excluded", False)
                exclude_reason = line.get("exclude_reason", "")

                if is_below_min_target:
                    line_is_excluded = True
                    exclude_reason = f"No alcanzó la meta mínima ({company.commission_min_target_pct:.0f}%)."

                line_ach_rate = achievement_rate
                is_credit_line = line.get("is_credit", False)
                line_invoice_total = line.get("invoice_total", 0.0)

                if line.get("invoice_date"):
                    inv_month = line["invoice_date"].replace(day=1)
                    if (
                        inv_month < self.date_from.replace(day=1)
                        and inv_month in snapshot_map
                    ):
                        line_ach_rate = snapshot_map[inv_month]

                base_comm_rate = (
                    0.0
                    if is_below_min_target
                    else get_rate_for_ach(line_ach_rate)
                )

                if not use_targets and base_comm_rate == 0.0 and not is_below_min_target:
                    base_comm_rate = (
                        credit_rate
                        if (is_credit_line and line_invoice_total > credit_threshold)
                        else cash_rate
                    )

                comm_pct_final = 0.0
                if not line_is_excluded:
                    product = self.env["product.product"].browse(line["product_id"])

                    is_fixed_pct = False
                    is_explicit_pct = False
                    if self.env.company.commission_use_fixed_percentage:
                        fixed_pct_products = (
                            self.env.company.commission_fixed_pct_product_ids
                        )
                        fixed_pct_tags = (
                            self.env.company.commission_fixed_pct_product_tag_ids
                        )
                        fixed_pct_categories = (
                            self.env.company.commission_fixed_pct_product_category_ids
                        )

                        if (
                            not fixed_pct_products
                            and not fixed_pct_tags
                            and not fixed_pct_categories
                        ):
                            is_fixed_pct = True
                        else:
                            in_pct_products = (
                                product.id in fixed_pct_products.ids
                                if fixed_pct_products
                                else False
                            )
                            in_pct_category = (
                                product.categ_id.id in fixed_pct_categories.ids
                                if fixed_pct_categories
                                else False
                            )
                            in_pct_tags = (
                                any(
                                    tag.id in fixed_pct_tags.ids
                                    for tag in product.all_product_tag_ids
                                )
                                if hasattr(product, "all_product_tag_ids")
                                and fixed_pct_tags
                                else False
                            )

                            if in_pct_products or in_pct_category or in_pct_tags:
                                is_fixed_pct = True
                                is_explicit_pct = True

                    if (
                        is_fixed_pct
                        and (
                            is_explicit_pct or product.commission_type == "percentage"
                        )
                        and product.x_comision_fija_producto > 0
                    ):
                        comm_pct_final = product.x_comision_fija_producto
                    else:
                        comm_pct_final = base_comm_rate

                penalty_pct = 0.0
                if not line_is_excluded and line.get("is_min_price_sale"):
                    penalty_pct = self.min_price_penalty_pct

                base = line["amount_paid"]
                profit_amount = base

                if use_margin:
                    original_price = base + line["cost"]
                    margin = (base / original_price) if original_price > 0 else 0
                else:
                    actual_margin_amount = base - line["cost"]
                    margin = (actual_margin_amount / base) if base > 0 else 0

                if profit_amount < 0:
                    profit_amount = 0.0

                product = self.env["product.product"].browse(line["product_id"])

                is_fixed_comm = False
                is_explicit_comm = False
                if self.env.company.commission_use_fixed_amount:
                    fixed_products = self.env.company.commission_fixed_product_ids
                    fixed_tags = self.env.company.commission_fixed_product_tag_ids
                    fixed_categories = (
                        self.env.company.commission_fixed_product_category_ids
                    )

                    if (
                        not fixed_products
                        and not fixed_tags
                        and not fixed_categories
                    ):
                        is_fixed_comm = True
                    else:
                        in_products = (
                            product.id in fixed_products.ids
                            if fixed_products
                            else False
                        )
                        in_category = (
                            product.categ_id.id in fixed_categories.ids
                            if fixed_categories
                            else False
                        )
                        in_tags = (
                            any(
                                tag.id in fixed_tags.ids
                                for tag in product.all_product_tag_ids
                            )
                            if hasattr(product, "all_product_tag_ids")
                            and fixed_tags
                            else False
                        )

                        if in_products or in_category or in_tags:
                            is_fixed_comm = True
                            is_explicit_comm = True

                # Apply mora penalty factor to gross commission
                mora_factor_pct = line.get("mora_penalty_factor", 1.0)

                if (
                    is_fixed_comm
                    and (is_explicit_comm or product.commission_type == "fixed")
                    and product.commission_fixed_amount > 0
                ):
                    gross = product.commission_fixed_amount * line.get("quantity", 0.0) * mora_factor_pct
                    if not line_is_excluded:
                        comm_pct_final = (gross / base) if base else 0.0
                else:
                    gross = profit_amount * comm_pct_final * mora_factor_pct

                deduct = gross * deduction_pct
                penalty = base * penalty_pct

                amount_comm = 0.0
                if not line_is_excluded:
                    amount_comm = gross - deduct - penalty
                    if amount_comm < 0:
                        amount_comm = 0

                total_commission += amount_comm

                # USD Conversion
                comm_amount_usd = 0.0
                usd_currency = self.env.ref("base.USD", raise_if_not_found=False)

                if usd_currency:
                    if line.get("original_currency") == usd_currency:
                        base_usd = line["original_amount"]
                        profit_usd = base_usd
                        if profit_usd < 0:
                            profit_usd = 0.0

                        if (
                            is_fixed_comm
                            and product.commission_type == "fixed"
                            and product.commission_fixed_amount > 0
                        ):
                            gross_usd = (
                                product.commission_fixed_amount
                                * line.get("quantity", 0.0)
                                * mora_factor_pct
                            )
                        else:
                            gross_usd = profit_usd * comm_pct_final * mora_factor_pct

                        deduct_usd = gross_usd * deduction_pct
                        penalty_usd = base_usd * penalty_pct

                        comm_amount_usd = gross_usd - deduct_usd - penalty_usd
                    else:
                        if amount_comm > 0:
                            comm_amount_usd = (
                                self.env.company.currency_id._convert(
                                    amount_comm,
                                    usd_currency,
                                    self.env.company,
                                    line["date"] or fields.Date.today(),
                                )
                            )

                if comm_amount_usd < 0:
                    comm_amount_usd = 0.0

                # Manager Commission per line (for dashboard)
                mgr_comm_amount = 0.0
                sp_country = data.get("country")
                sp_vt = data.get("vendor_type")

                # Operations Manager
                if sp_country == "PAN":
                    mgr_comm_amount += base * 0.0015

                # Sales Manager
                if sp_country == "VEN":
                    mgr_comm_amount += base * 0.0020
                elif sp_country == "PAN":
                    pan_team_target = sum(
                        t.amount_target
                        for t in targets
                        if t.vendedor_id.vendor_type_id.country == "PAN"
                    )
                    pan_country_total = country_totals.get("PAN", 0.0)
                    pan_mgr_rate = 0.0010
                    if pan_team_target > 0:
                        team_ach = pan_country_total / pan_team_target
                        if team_ach >= 1.20:  # Fixed 1.20 (120%)
                            pan_mgr_rate = 0.0020
                        elif team_ach >= 1.00:
                            pan_mgr_rate = 0.0015
                        elif team_ach >= 0.80:
                            pan_mgr_rate = 0.0010
                        else:
                            pan_mgr_rate = 0.0

                    mgr_comm_amount += base * pan_mgr_rate

                lines_to_create.append(
                    (
                        0,
                        0,
                        {
                            "date": line["date"],
                            "client_id": line["client_id"],
                            "product_id": line["product_id"],
                            "invoice_id": line.get("invoice_id"),
                            "invoice_date": line.get("invoice_date"),
                            "invoice_date_due": line.get("invoice_date_due"),
                            "days_credit": line.get("days_credit", 0),
                            "days_paid": line.get("days_paid", 0),
                            "days_overdue": line.get("days_overdue", 0),
                            "mora_penalty_factor": line.get("mora_penalty_factor", 1.0),
                            "manager_commission": mgr_comm_amount,
                            "invoice_payment_term_id": line.get(
                                "invoice_payment_term_id", False
                            ),
                            "amount_paid": base,
                            "cost": line["cost"],
                            "profitability": margin,
                            "is_min_price_sale": line["is_min_price_sale"],
                            "is_overdue": line.get("is_overdue", False),
                            "is_excluded": line_is_excluded,
                            "exclude_reason": exclude_reason,
                            "is_credit": line.get("is_credit", False),
                            "commission_pct": comm_pct_final,
                            "deduction_pct": deduction_pct,
                            "penalty_pct": penalty_pct,
                            "commission_amount": amount_comm,
                            "commission_amount_usd": comm_amount_usd,
                        },
                    )
                )

            # Manager Commission Calculation (Summary Line)
            manager_comm = 0.0
            if data["is_manager"]:
                mgr_vt = data["vendor_type"]
                
                # Exclude sales from excluded partners (e.g. Sr. Hercilio)
                excluded_users = mgr_vt.excluded_user_ids if mgr_vt else self.env["res.users"]
                team_lines_base = 0.0
                team_invoiced_base = 0.0

                for sp_user, sp_info in sales_data.items():
                    if sp_info.get("company_id") == company.id and sp_info["country"] == data["country"] and sp_user not in excluded_users:
                        # For manager team base, include full comisionable collected lines of the team
                        team_lines_base += sp_info.get("total_collected_gross", sp_info["total_collected"])
                        team_invoiced_base += sp_info["total_invoiced"]

                mgr_mode = mgr_vt.manager_commission_type if mgr_vt else "fixed"
                mgr_rate = 0.0

                if mgr_mode == "volume_range":
                    # Valencia Manager Volume Range (Image 1)
                    volume_rule = self.env["commission.manager.volume.range"].search(
                        [
                            ("company_id", "=", company.id),
                            ("vendor_type_id", "=", mgr_vt.id),
                            ("amount_from", "<=", team_lines_base),
                            "|",
                            ("amount_to", ">=", team_lines_base),
                            ("amount_to", "=", 0.0),
                        ],
                        limit=1,
                        order="amount_from desc",
                    )
                    if volume_rule:
                        mgr_rate = volume_rule.commission_percentage
                    elif data["country"] == "VEN":
                        # Fallback for VEN default
                        mgr_rate = 0.20

                    manager_comm = team_lines_base * (mgr_rate / 100.0)

                elif mgr_mode == "achievement_range":
                    # Panama Sales Manager Achievement Range
                    team_target = sum(
                        t.amount_target
                        for t in targets
                        if t.vendedor_id.vendor_type_id.country == data["country"]
                        and t.vendedor_id.id not in excluded_users.mapped("partner_id.id")
                    )
                    team_ach = 0.0
                    if team_target > 0:
                        team_ach = team_invoiced_base / team_target

                    if team_ach >= 1.20:  # 120%
                        mgr_rate = 0.20
                    elif team_ach >= 1.00:  # 100%
                        mgr_rate = 0.15
                    elif team_ach >= 0.80:  # 80%
                        mgr_rate = 0.10
                    else:
                        mgr_rate = 0.0

                    manager_comm = team_lines_base * (mgr_rate / 100.0)

                else:
                    # Fixed Manager Rate (e.g. Panama Ops Manager 0.15%)
                    if mgr_vt and mgr_vt.manager_fixed_rate > 0:
                        mgr_rate = mgr_vt.manager_fixed_rate
                    elif data["manager_role"] == "operations" and data["country"] == "PAN":
                        mgr_rate = 0.15
                    elif data["manager_role"] == "sales" and data["country"] == "VEN":
                        mgr_rate = 0.20

                    manager_comm = team_lines_base * (mgr_rate / 100.0)

                if manager_comm > 0:
                    total_commission += manager_comm
                    mgr_comm_usd = manager_comm
                    usd_curr = self.env.ref("base.USD", raise_if_not_found=False)
                    comp_curr = company.currency_id
                    if usd_curr and comp_curr and comp_curr != usd_curr:
                        mgr_comm_usd = comp_curr._convert(manager_comm, usd_curr, company, self.date_to or fields.Date.today())

                    lines_to_create.append(
                        (
                            0,
                            0,
                            {
                                "date": self.date_to,
                                "amount_paid": team_lines_base,
                                "commission_amount": manager_comm,
                                "commission_amount_usd": mgr_comm_usd,
                                "commission_pct": mgr_rate,
                            },
                        )
                    )

            settlement_vals["total_commission"] = total_commission
            settlement_vals["line_ids"] = lines_to_create

            created_settlements |= self.env["commission.settlement"].create(
                settlement_vals
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Liquidaciones Generadas",
            "res_model": "commission.settlement",
            "view_mode": "tree,form",
            "domain": [("id", "in", created_settlements.ids)],
        }

    def action_print_report(self):
        data = {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "min_price_penalty_pct": self.min_price_penalty_pct,
        }
        return self.env.ref(
            "supricom_commissions.action_report_commission"
        ).report_action(self, data=data)
