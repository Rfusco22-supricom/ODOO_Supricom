from odoo import models, fields, api
from datetime import timedelta



class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    product_cost = fields.Float(
        string="Costo Producto",
        compute="_compute_commission_fields",
        store=True,
        help="Costo estándar del producto al momento de la venta.",
    )
    commission_base = fields.Monetary(
        string="Base Comisión",
        currency_field="currency_id",
        compute="_compute_commission_fields",
        store=True,
        help="Monto base para el cálculo de comisión (Subtotal - Costo Total).",
    )
    commission_amount = fields.Monetary(
        string="Monto Comisión",
        currency_field="currency_id",
        compute="_compute_commission_fields",
        store=True,
        help="Monto calculado de comisión preliminar para esta línea.",
    )
    deduction_percentage = fields.Float(
        string="% Deducción",
        compute="_compute_commission_fields",
        store=True,
        help="Porcentaje de gastos fijos aplicado a esta línea.",
    )
    commission_final_amount = fields.Monetary(
        string="Monto Final",
        currency_field="currency_id",
        compute="_compute_commission_fields",
        store=True,
        help="Monto final de comisión a pagar tras deducciones y penalizaciones.",
    )
    is_min_price_sale = fields.Boolean(
        string="Venta a Precio Mínimo",
        compute="_compute_is_min_price_sale",
        store=True,
        help="Indica si esta línea proviene de una venta con precio mínimo o inferior.",
    )

    @api.depends("sale_line_ids.is_min_price_sale")
    def _compute_is_min_price_sale(self):
        for line in self:
            # If any related sale line was min price, mark this invoice line trigger.
            # Usually strict 1:1 or logic from SO.
            if any(sl.is_min_price_sale for sl in line.sale_line_ids):
                line.is_min_price_sale = True
            else:
                line.is_min_price_sale = False

    @api.depends(
        "price_subtotal",
        "product_id",
        "quantity",
        "move_id.invoice_date_due",
        "move_id.manual_commission_override",
        "move_id.payment_state",
    )
    def _compute_commission_fields(self):
        # Prevent AccessError if user doesn't have write access to lines (e.g. multi-company)
        # Commission fields should be computed regardless of current user's strict restrictions on the line
        for line in self.sudo():
            if line.product_id:
                # FIX: Force context to line's company to fetch correct Standard Price (Cost)
                # This ensures that even if the user is in Company A, creating an invoice for Company B,
                # we get the Cost defined for Company B.
                line.product_cost = line.product_id.with_company(line.company_id).standard_price
                # Calculate base: (Sale Price - Cost) * Quantity
                # Note: price_subtotal is quantity * price_unit (usually)
                # We need total cost for the line quantity
                total_cost = line.product_cost * line.quantity

                # Convert Cost (Company Currency) to Line Currency (e.g. USD) if needed
                if line.currency_id and line.currency_id != line.company_id.currency_id:
                    total_cost = line.company_id.currency_id._convert(
                        total_cost,
                        line.currency_id,
                        line.company_id,
                        line.move_id.invoice_date or fields.Date.today(),
                    )

                # Check company setting for commission base type
                if line.company_id.commission_base_type == "margin":
                    line.commission_base = line.price_subtotal - total_cost
                else:
                    line.commission_base = line.price_subtotal


                # Check for overdue payments — with grace days by country (VEN=10, PAN=15)
                is_overdue = False
                if (
                    line.move_id.payment_state in ["paid", "in_payment"]
                    and line.move_id.invoice_date_due
                ):
                    # Determine grace days from salesperson's vendor type country
                    _salesperson = line.move_id.invoice_user_id
                    _vt = _salesperson.vendor_type_id if _salesperson else False
                    _country = _vt.country if _vt else ''
                    _grace_days = 10 if _country == 'VEN' else (15 if _country == 'PAN' else 0)
                    _grace_date = line.move_id.invoice_date_due + timedelta(days=_grace_days)
                    # Get reconciled payments
                    reconciled_payments = line.move_id._get_reconciled_payments()
                    if reconciled_payments:
                        max_payment_date = max(reconciled_payments.mapped("date"))
                        if max_payment_date > _grace_date:
                            is_overdue = True

                # If overdue and no override, commission is 0
                if is_overdue and not line.move_id.manual_commission_override:
                    line.commission_amount = 0.0
                    line.commission_final_amount = 0.0
                    line.deduction_percentage = 0.0
                # Else logic to calculate commission amount (Estimated)
                else:
                    salesperson = line.move_id.invoice_user_id
                    rate = 0.0
                    if salesperson:
                        # Try to find active contract
                        contract = self.env['hr.contract'].search([
                            ('employee_id.user_id', '=', salesperson.id),
                            ('state', 'in', ['open', 'close']),
                            ('date_start', '<=', line.move_id.invoice_date or fields.Date.today()),
                            '|', ('date_end', '=', False), ('date_end', '>=', line.move_id.invoice_date or fields.Date.today())
                        ], limit=1)
                        if contract and contract.fix_commission_rate > 0.0:
                            rate = contract.fix_commission_rate
                    
                    line.commission_amount = line.commission_base * rate
                    
                    # Deduction (Simplified / Placeholder)
                    # Deduction is usually at payment time, but we can try to fetch current fixed expense
                    # For performance, maybe skip or just use rate.
                    # Let's simple use base * rate for now as estimate.
                    line.commission_final_amount = line.commission_amount
                    line.deduction_percentage = 0.0
            else:
                line.product_cost = 0.0
                line.commission_base = 0.0
                line.commission_amount = 0.0
                line.commission_final_amount = 0.0
                line.deduction_percentage = 0.0
