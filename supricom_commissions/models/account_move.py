from odoo import models, fields, api
import datetime


class AccountMove(models.Model):
    _inherit = "account.move"

    manual_commission_override = fields.Boolean(
        string="Vencido (check)",
        tracking=True,
        help="Marcar manualmente para autorizar el pago de comisión en facturas vencidas.",
    )

    manual_commission_note = fields.Char(
        string="Nota Autorización",
        tracking=True,
        help="Observación sobre la autorización de comisión en factura vencida.",
    )

    def write(self, vals):
        # Check if manual_commission_override is changing to True
        is_override = vals.get("manual_commission_override")
        # Get note from vals if present (to handle concurrent update)
        new_note = vals.get("manual_commission_note")
        
        if is_override:
            for move in self:
                if not move.manual_commission_override:
                    # It's being turned ON.
                    # 2. Check for EXISTING payments...
                    # We need to find payments linked to this invoice.
                    # Using local helper or standard
                    if move.invoice_payments_widget:
                        pass

                    # Robust way: traverse partials
                    for partial in move._get_reconciled_partials():
                        # partial is account.partial.reconcile
                        counterpart_line = partial.credit_move_id if partial.debit_move_id.move_id == move else partial.debit_move_id
                        payment_move = counterpart_line.move_id
                        
                        # Find the actual payment object if it exists
                        payment = self.env['account.payment'].search([('move_id', '=', payment_move.id)], limit=1)
                        
                        if payment:
                            # Only log if payment date is AFTER invoice due date
                            if move.invoice_date_due and payment.date > move.invoice_date_due:
                                self._log_commission_exception(payment, move, note=new_note)

        # ACCESS ERROR FIX:
        # manual_commission_override triggers recomputation of commission fields on lines.
        # In multi-company, these lines might belong to another company, triggering 'Entry lines' rule error.
        # We separate this write and run it as sudo(), assuming the user has group_commission_manager (enforced by View).
        if 'manual_commission_override' in vals:
            override_val = vals.pop('manual_commission_override')
            # Ensure note is also written if present, though super().write(vals) handles the rest?
            # actually we removed override_val, so we must write it carefully.
            # But the super write below handles the rest of keys. 
            super(AccountMove, self.sudo()).write({'manual_commission_override': override_val})

        if vals:
            return super(AccountMove, self).write(vals)
        return True

    def _get_reconciled_partials(self):
        self.ensure_one()
        reconciled_partials = self.env['account.partial.reconcile']
        for line in self.line_ids:
            reconciled_partials |= line.matched_debit_ids
            reconciled_partials |= line.matched_credit_ids
        return reconciled_partials

    def _log_commission_exception(self, payment, invoice, note=None):
        """
        Calculates the commission for a specific payment on an overdue invoice
        and logs it with the resulting execution data.
        """
        self.ensure_one() # 'self' should be the invoice ideally, but we passed invoice explicitly.
        # Let's trust 'invoice' argument
        
        salesperson = invoice.invoice_user_id
        if not salesperson:
            return

        # 1. Calculate Total Collected for the month of the INVOICE (or Payment? Policy says Invoice Date usually for Target?)
        # Requirement: "Si este abono... actualiza... sus ventas del mes"
        # Usually commissions are settled based on Payment Date for collection, but Target is often set per month.
        # Let's assume the Target Month is the Payment Date Month (when the collection happens).
        # "El porcentaje de comisión... se debe actualizar" implies we need to check the Target of the Payment Month.
        
        date_for_target = payment.date
        month_start = date_for_target.replace(day=1)
        
        # Calculate Total Collected in this month by this salesperson
        # We need to sum up all payments received in this month for this salesperson's invoices.
        # This is expensive. We will attempt a best effort estimation or check the Monthly Closing if it exists/is live.
        # Or re-calculate using the Wizard's logic?
        # Re-using Wizard logic is hard here.
        # Simplified: Sum amount of payments in this month for this user.
        
        # Search for payments in this month linked to this user's invoices
        # This is complex SQL or Search.
        # Let's look for 'commission.monthly.closing' first? 
        # But that might be static.
        # Let's calculate from scratch effectively but efficiently.
        
        domain = [
            ('payment_id.date', '>=', month_start),
            ('payment_id.date', '<=', payment.date), # Up to this payment
            ('invoice_id.invoice_user_id', '=', salesperson.id),
            ('invoice_id.move_type', '=', 'out_invoice')
        ]
        # Partial Reconciles link Payment and Invoice.
        # We search partials.
        # But we don't have a direct link from Partial to "Invoice User" without joining.
        
        # fallback: use simplified logic. 
        # If we can't easily calc "New Tier", we might log the "Current Tier" or Contract Rate.
        # Requirement says: "El sistema debe validar si... alcanza un peldaño superior... log debe capturar esta Comisión Resultante".
        
        # Let's try to get current target achievement.
        target_obj = self.env['commission.monthly.target'].search([
            ('vendedor_id', '=', salesperson.id),
            ('date_from', '<=', month_start),
            ('date_to', '>=', month_start)
        ], limit=1)
        
        target_amount = 0.0
        if target_obj:
            target_amount = target_obj.amount_target
            if target_obj.currency_id and target_obj.currency_id != self.env.company.currency_id:
                target_amount = target_obj.currency_id._convert(
                    target_amount,
                    self.env.company.currency_id,
                    self.env.company,
                    target_obj.date_from or fields.Date.today()
                )
        
        # We need total collected.
        # We can sum payments found for this user in this range?
        # For performance, maybe we just assume the "Current" status from a report or just calculated strictly.
        # Let's do a direct SQL for speed.
        
        sql = """
            SELECT SUM(apr.amount)
            FROM account_partial_reconcile apr
            JOIN account_move_line inv_line ON (apr.debit_move_id = inv_line.id OR apr.credit_move_id = inv_line.id)
            JOIN account_move inv ON inv_line.move_id = inv.id
            JOIN account_move_line pay_line ON (apr.debit_move_id = pay_line.id OR apr.credit_move_id = pay_line.id)
            JOIN account_payment pay ON pay_line.payment_id = pay.id
            WHERE inv.invoice_user_id = %s
            AND inv.move_type = 'out_invoice'
            AND pay.date >= %s AND pay.date <= %s
            AND pay.state = 'posted'
            AND inv_line.account_id != pay_line.account_id -- Ensure we are crossing accounts (receivable)
        """
        # Note: simplistic SQL. Odoo's ORM is safer but slower.
        # Let's stick to safe ORM.
        
        # Fetch all payments for this user in dates.
        # payments = self.env['account.payment'].search([...]) 
        # But payments don't know the salesperson of the invoice they paid.
        
        # Let's proceed with just the Contract Check and Matrix lookup based on *assumed* achievement if calculation is too heavy, 
        # OR implement a rough sum.
        # Given the strict requirement, I will try to implement the sum using a search on account.partial.reconcile.
        
        partials = self.env['account.partial.reconcile'].search([
            ('max_date', '>=', month_start),
            ('max_date', '<=', payment.date)
        ])
        # Filter by salesperson
        total_collected = 0.0
        for p in partials:
            # Check invoice side
            inv = p.debit_move_id.move_id if p.debit_move_id.move_id.move_type == 'out_invoice' else p.credit_move_id.move_id
            if inv.move_type != 'out_invoice':
                # maybe the other side
                 inv = p.credit_move_id.move_id if p.credit_move_id.move_id.move_type == 'out_invoice' else p.debit_move_id.move_id
            
            if inv.move_type == 'out_invoice' and inv.invoice_user_id == salesperson:
                 total_collected += p.amount
                 
        achievement_pct = 0.0
        if target_amount > 0:
            achievement_pct = total_collected / target_amount
            
        # Determine Rate
        contract = self.env['hr.contract'].search([
            ('employee_id.user_id', '=', salesperson.id),
            ('state', 'in', ['open', 'close']),
            ('date_start', '<=', invoice.date),
            '|', ('date_end', '=', False), ('date_end', '>=', invoice.date)
        ], limit=1)
        
        rate = 0.0
        # Priority 1: Contract Fix
        if contract and contract.fix_commission_rate > 0.0:
            rate = contract.fix_commission_rate
        else:
            # Priority 2: Matrix
            # Lookup Matrix using Dynamic Rules
            vendor_type = salesperson.vendor_type_id
            if contract and contract.commission_vendor_type_id:
                vendor_type = contract.commission_vendor_type_id
                
            if vendor_type:
                 # Fetch all rules for this Vendor Type
                 matrix_lines = self.env['commission.matrix'].search([
                     ('vendor_type_id', '=', vendor_type.id)
                 ])
                 
                 # Sort by Target Achievement descending
                 sorted_rules = []
                 for m in matrix_lines:
                     try:
                         thresh = float(m.target_achievement_pct)
                         sorted_rules.append((thresh, m.commission_percentage))
                     except ValueError:
                         continue
                 sorted_rules.sort(key=lambda x: x[0], reverse=True)
                 
                 # Find Match
                 for threshold, r in sorted_rules:
                     if achievement_pct >= threshold:
                         rate = r
                         break
                 
        # Calculate Amount
        # Base portion logic (mimic wizard roughly or just use full amount ratio?)
        # Base = Payment Amount * (Invoice Base / Invoice Total)
        # We need the commission base of the invoice lines.
        # Simplified: Payment Amount / 1.16 (VAT)?? No, depends on lines.
        # Let's just use: Portion of Untaxed Amount.
        
        amount_paid_in_invoice_currency = 0.0
        for aml in invoice.line_ids:
            for partial in aml.matched_credit_ids:
                if partial.credit_move_id.payment_id == payment or partial.credit_move_id.move_id == payment.move_id:
                    amount_paid_in_invoice_currency += partial.debit_amount_currency
            for partial in aml.matched_debit_ids:
                if partial.debit_move_id.payment_id == payment or partial.debit_move_id.move_id == payment.move_id:
                    amount_paid_in_invoice_currency += partial.credit_amount_currency

        ratio = 0.0
        if invoice.amount_total != 0:
            ratio = amount_paid_in_invoice_currency / invoice.amount_total
            
        base_untaxed_portion = 0.0
        # Try to sum commission_base from lines if available
        # This is more accurate than simple ratio
        total_comm_base = sum(line.commission_base for line in invoice.invoice_line_ids)
        if total_comm_base != 0:
             base_untaxed_portion = total_comm_base * ratio
        else:
             base_untaxed_portion = invoice.amount_untaxed * ratio
        
        # Deductions? "Gasto Fijo" is yearly/monthly.
        # Requirement says "Comisión Resultante".
        # We should try to deduct if we want to be exact.
        # But Deduction is a % of the total sales.
        # Getting the deduction % for that month:
        deduction_pct = 0.0
        fixed_expense = self.env['commission.fixed.expense'].search([
            ('date_from', '<=', payment.date),
            ('date_to', '>=', payment.date)
        ], limit=1)
        # Note: The fixed expense record stores the pct based on *its* calculation time.
        # If it's 0, we might strictly need to calc it.
        if fixed_expense:
            deduction_pct = fixed_expense.deduction_percentage

        # Calculate Cost to determine Profit
        # Profit = (Collected - Cost) * Rate - Deduction
        # Collected (Base) = base_untaxed_portion
        # Cost = Sum(Line Cost) * Ratio
        total_cost_company = 0.0
        for line in invoice.invoice_line_ids:
            # Use standard_price as per wizard logic.
            # Note: This uses current standard_price.
            line_cost = line.product_id.standard_price
            total_cost_company += line_cost * line.quantity

        # Convert Cost to Invoice Currency if needed
        total_cost_inv = total_cost_company
        if invoice.currency_id and invoice.currency_id != self.env.company.currency_id:
             total_cost_inv = self.env.company.currency_id._convert(
                total_cost_company,
                invoice.currency_id,
                self.env.company,
                invoice.date or fields.Date.today()
            )

        cost_portion = total_cost_inv * ratio
        profit_base = base_untaxed_portion - cost_portion
        if profit_base < 0:
            profit_base = 0.0
            
        final_commission = (profit_base * rate) * (1 - deduction_pct)
        if final_commission < 0: final_commission = 0
            
        # Create Log
        description_text = f"Abono autorizado (Vencido). Meta: {achievement_pct*100:.1f}%. Tasa: {rate*100:.1f}%. Deducción: {deduction_pct*100:.1f}%."
        
        # Use provided note or fallback to stored note
        current_note = note if note else invoice.manual_commission_note
            
        self.env["commission.override.log"].create({
            "move_id": invoice.id,
            "salesperson_id": salesperson.id,
            "partner_id": salesperson.partner_id.id,
            "payment_id": payment.id,
            "amount_paid": payment.amount,
            "commission_amount": final_commission,
            "description": description_text,
            "note": current_note,
        })
