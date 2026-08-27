from odoo import models, api, fields
from collections import defaultdict
from datetime import timedelta


class CommissionReport(models.AbstractModel):
    _name = "report.supricom_commissions.report_commission"
    _description = "Reporte de Comisiones"

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data:
            data = {}

        # If called from Settlement model (not Wizard), fetch from first record
        if not data.get("date_from") and docids:
            # Try to get from settlement
            settlement = self.env["commission.settlement"].browse(docids[0])
            if settlement.exists():
                data["date_from"] = settlement.date_from
                data["date_to"] = settlement.date_to
                data["min_price_penalty_pct"] = settlement.min_price_penalty_pct

        date_from = data.get("date_from")
        date_to = data.get("date_to")

        # 1. Deductions
        fixed_expenses = self.env["commission.fixed.expense"].search(
            [("date_from", ">=", date_from), ("date_to", "<=", date_to)]
        )
        deduction_pct = sum(fixed_expenses.mapped("deduction_percentage"))

        # 2. Payments
        payments = self.env["account.payment"].search(
            [
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("state", "in", ["posted", "in_process"]),
            ]
        )

        # Structure: { Salesperson: { 'total_collected': 0.0, 'lines': [], ... } }
        sales_data = defaultdict(
            lambda: {
                "name": "",
                "total_collected": 0.0,
                "lines": [],
                "country": "",
                "vendor_type": False,
                "target": 0.0,
                "is_manager": False,
                "manager_role": False,
                "total_comm": 0.0,
            }
        )

        # Track country totals for managers
        country_totals = defaultdict(float)  # { 'VEN': 0.0, 'PAN': 0.0 }

        for payment in payments:
            # We iterate payments to attribute commissions based on Payment Date.
            # Get invoices
            reconciled_invoices = payment.reconciled_invoice_ids
            if not reconciled_invoices:
                reconciled_invoices = payment.reconciled_bill_ids

            for invoice in reconciled_invoices:
                if invoice.move_type != "out_invoice":
                    continue

                salesperson = invoice.invoice_user_id
                if not salesperson or not salesperson.is_vendor:
                    continue

                vendor_type = salesperson.vendor_type_id

                # OVERDUE CHECK with grace days by country (VEN=10, PAN=15)
                is_overdue = False
                if invoice.invoice_date_due:
                    _country = vendor_type.country if vendor_type else ''
                    _grace_days = 10 if _country == 'VEN' else (15 if _country == 'PAN' else 0)
                    _grace_date = invoice.invoice_date_due + timedelta(days=_grace_days)
                    if payment.date > _grace_date:
                        is_overdue = True

                is_valid_for_commission = True
                if is_overdue and not invoice.manual_commission_override:
                    is_valid_for_commission = False

                sp_key = salesperson
                sales_data[sp_key]["name"] = salesperson.name
                sales_data[sp_key]["country"] = vendor_type.country
                sales_data[sp_key]["vendor_type"] = vendor_type
                sales_data[sp_key]["is_manager"] = vendor_type.is_manager
                sales_data[sp_key]["manager_role"] = vendor_type.manager_role

                # Calculate the actual amount paid to this invoice by this payment
                amount_paid_in_invoice_currency = 0.0
                for aml in invoice.line_ids:
                    for partial in aml.matched_credit_ids:
                        if partial.credit_move_id.payment_id == payment or partial.credit_move_id.move_id == payment.move_id:
                            amount_paid_in_invoice_currency += partial.debit_amount_currency
                    for partial in aml.matched_debit_ids:
                        if partial.debit_move_id.payment_id == payment or partial.debit_move_id.move_id == payment.move_id:
                            amount_paid_in_invoice_currency += partial.credit_amount_currency

                inv_ratio = 1.0
                if invoice.amount_total != 0:
                    inv_ratio = amount_paid_in_invoice_currency / invoice.amount_total

                # Process Lines
                for line in invoice.invoice_line_ids:
                    ratio = inv_ratio

                    comm_base_portion = line.commission_base * ratio

                    # Accumulate Country Total (Only valid sales count? Or all sales?)
                    # Ops Manager gets 0.15% on ALL sales. So we should track all.
                    country_totals[vendor_type.country] += comm_base_portion

                    if not is_valid_for_commission:
                        # Add to lines with 0 commission
                        sales_data[sp_key]["lines"].append(
                            {
                                "date": payment.date,
                                "client": invoice.partner_id.name,
                                "product": line.product_id.name,
                                "price": line.price_unit,
                                "cost": line.product_cost,
                                "commission_base": comm_base_portion,
                                "comm_pct_base": 0.0,
                                "deduction_pct": 0.0,
                                "amount_comm": 0.0,
                                "is_excluded": True,  # Marker for report
                                "payment_term": invoice.invoice_payment_term_id.name
                                or "",
                            }
                        )
                        continue

                    # Valid for commission -> Add to Total Collected (Target)
                    sales_data[sp_key]["total_collected"] += comm_base_portion

                    sales_data[sp_key]["lines"].append(
                        {
                            "date": payment.date,
                            "client": invoice.partner_id.name,
                            "product": line.product_id.name,
                            "price": line.price_unit,
                            "cost": line.product_cost,
                            "commission_base": comm_base_portion,
                            "comm_pct_base": 0.0,  # Placeholder
                            "deduction_pct": deduction_pct,
                            "amount_comm": 0.0,  # Placeholder
                            "is_excluded": False,
                            "is_min_price_sale": line.is_min_price_sale,
                            "payment_term": invoice.invoice_payment_term_id.name or "",
                        }
                    )

        # 3. Targets & Matrix
        targets = self.env["commission.monthly.target"].search(
            [("date_from", ">=", date_from), ("date_from", "<=", date_to)]
        )
        target_map = {t.vendedor_id.id: t.amount_target for t in targets}

        matrix = self.env["commission.matrix"].search([])
        matrix_map = {}
        for m in matrix:
            matrix_map[(m.vendor_type_id.id, m.target_achievement_pct)] = (
                m.commission_percentage
            )

        # 4. Calculation
        for salesperson, data in sales_data.items():
            # A. Normal Commission
            target = target_map.get(salesperson.partner_id.id, 0.0)
            data["target"] = target

            achievement_rate = 0.0
            if target > 0:
                achievement_rate = data["total_collected"] / target

            # Determine Matrix Bracket
            ach_str = "0.8"
            if achievement_rate >= 1.5:
                ach_str = "1.5"
            elif achievement_rate >= 1.1:
                ach_str = "1.1"
            elif achievement_rate >= 1.0:
                ach_str = "1.0"
            elif achievement_rate >= 0.8:
                ach_str = "0.8"

            base_comm_rate = 0.0
            if data["vendor_type"]:
                base_comm_rate = matrix_map.get((data["vendor_type"].id, ach_str), 0.0)

            # Apply to lines
            for line in data["lines"]:
                if line["is_excluded"]:
                    continue

                line["comm_pct_base"] = base_comm_rate

                # Gross Comm
                gross = line["commission_base"] * base_comm_rate
                # Deduction
                deduct = gross * deduction_pct

                # Penalty for Min Price
                penalty = 0.0
                if line.get(
                    "is_min_price_sale"
                ):  # We need to ensure we fetch this from invoice line earlier
                    penalty = line["commission_base"] * data.get(
                        "min_price_penalty_pct", 0.0
                    )

                line["penalty_pct"] = (
                    data.get("min_price_penalty_pct", 0.0)
                    if line.get("is_min_price_sale")
                    else 0.0
                )

                line["amount_comm"] = gross - deduct - penalty

                # Calculate USD Amount (Replica of Wizard Logic)
                comm_amount_usd = 0.0
                usd_currency = self.env["res.currency"].search(
                    [("name", "=", "USD")], limit=1
                )

                if usd_currency:
                    # If we had original currency info we could use it, but here we work from company currency (amount_comm)
                    # Use payment date or invoice date? report uses payment.date
                    if line["amount_comm"] > 0:
                        comm_amount_usd = self.env.company.currency_id._convert(
                            line["amount_comm"],
                            usd_currency,
                            self.env.company,
                            line["date"],
                        )

                line["commission_amount_usd"] = comm_amount_usd

            # B. Manager Commission
            # Managers might have their own sales (handled above).
            # PLUS they get Team commission.
            # We will add a special line or adjust 'total_comm' in summary.

            manager_comm = 0.0

            if data["is_manager"]:
                country_total = country_totals.get(data["country"], 0.0)

                if data["manager_role"] == "operations":
                    # Ops Manager Logic (Panama/General)
                    if data["country"] == "PAN":
                        # 3. Gerente de Operaciones Panamá: Recibe un 0,15% fijo por todas las ventas realizadas.
                        manager_comm = country_total * (0.15 / 100.0)

                elif data["manager_role"] == "sales":
                    # Sales Manager Logic
                    if data["country"] == "VEN":
                        # 1. Gerente de Ventas Venezuela: 0,20% sobre todas las ventas cobradas, sin importar cumplimiento.
                        manager_comm = country_total * (0.20 / 100.0)

                    elif data["country"] == "PAN":
                        # 2. Gerente de Ventas Panamá: Su comisión depende del cumplimiento de meta de todo su equipo
                        team_target = sum(
                            t.amount_target
                            for t in targets
                            if t.vendedor_id.vendor_type_id.country == data["country"]
                        )

                        team_achievement = 0.0
                        if team_target > 0:
                            team_achievement = country_total / team_target

                        # - 80% de meta alcanzada: 0,10%.
                        # - 100% de meta alcanzada: 0,15%.
                        # - 110% de meta alcanzada: 0,20%.
                        mgr_rate = 0.0
                        if team_achievement >= 1.10:
                            mgr_rate = 0.20
                        elif team_achievement >= 1.00:
                            mgr_rate = 0.15
                        elif team_achievement >= 0.80:
                            mgr_rate = 0.10

                        manager_comm = country_total * (mgr_rate / 100.0)

                # Add Manager Commission Line
                if manager_comm > 0:
                    data["lines"].append(
                        {
                            "date": date_to,
                            "client": "COMISION GERENCIAL",
                            "product": "Bono por Equipo/Operaciones",
                            "price": 0,
                            "cost": 0,
                            "commission_base": country_total,
                            "comm_pct_base": 0.0,
                            "deduction_pct": 0.0,
                            "amount_comm": manager_comm,
                            "is_excluded": False,
                        }
                    )

        return {
            "doc_ids": docids,
            "doc_model": "commission.settlement.wizard",
            "data": data,
            "sales_data": sales_data,
            "deduction_pct": deduction_pct,
            "date_from": date_from,
            "date_to": date_to,
        }
