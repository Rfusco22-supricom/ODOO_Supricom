from odoo import api, fields, models, _
from odoo.tools import date_utils, format_date

class AccountMove(models.Model):
    _inherit = 'account.move'

    dual_total_text = fields.Char(string="Total Dual", compute="_compute_dual_totals_custom")
    dual_untaxed_text = fields.Char(string="Subtotal Dual", compute="_compute_dual_totals_custom")
    dual_tax_text = fields.Char(string="Impuesto Dual", compute="_compute_dual_totals_custom")
    dual_residual_text = fields.Char(string="Saldo Dual", compute="_compute_dual_totals_custom")
    dual_summary_html = fields.Html(compute="_compute_dual_summary_html")
    custom_payments_widget = fields.Binary(compute="_compute_custom_payments_widget", exportable=False) # Keep for compatibility or remove if unused

    @api.depends('amount_total', 'amount_untaxed', 'amount_tax', 'tax_today', 'currency_id', 'amount_residual', 'state', 'move_type', 'line_ids.matched_debit_ids', 'line_ids.matched_credit_ids')
    def _compute_dual_summary_html(self):
        for move in self:
            if not move.is_invoice(include_receipts=True):
                move.dual_summary_html = False
                continue

            tasa = move.tax_today or 1.0
            is_usd = move.currency_id.name == 'USD'
            
            # Configuración de Moneda y Cálculos
            if is_usd:
                # Factura USD -> Mostrar Bs
                symbol = "Bs."
                target_currency = move.company_id.currency_id
                
                untaxed = move.amount_untaxed * tasa
                total = move.amount_total * tasa
                residual = move.amount_residual * tasa
                
                # Para pagos: la factura es USD, queremos ver cuánto representa en Bs
                use_company_amount = True
            else:
                # Factura Bs -> Mostrar USD
                symbol = "$"
                target_currency = move.currency_id_dif
                
                untaxed = (move.amount_untaxed / tasa) if tasa > 0 else 0
                total = (move.amount_total / tasa) if tasa > 0 else 0
                residual = (move.amount_residual / tasa) if tasa > 0 else 0
                
                # Para pagos: la factura es Bs, queremos ver USD
                use_company_amount = False

            # --- Construcción del HTML ---
            
            # Estilos inline para asegurar consistencia
            style_label = 'padding: 4px; text-align: left; font-weight: normal; color: #666;'
            style_value = 'padding: 4px; text-align: right; white-space: nowrap;'
            style_total_label = 'padding: 8px 4px; text-align: left; font-weight: bold; border-top: 1px solid #dee2e6;'
            style_total_value = 'padding: 8px 4px; text-align: right; font-weight: bold; border-top: 1px solid #dee2e6;'
            
            rows = ""
            
            # 1. Subtotal
            rows += f"""
                <tr>
                    <td style="{style_label}">Subtotal Ref.</td>
                    <td style="{style_value}">{symbol} {untaxed:,.2f}</td>
                </tr>
            """
            
            # 2. Desglose de Impuestos
            if move.tax_totals and 'groups_by_subtotal' in move.tax_totals:
                for subtotal_title, groups in move.tax_totals['groups_by_subtotal'].items():
                    for group in groups:
                        if is_usd:
                            tax_amt = group['tax_group_amount'] * tasa
                        else:
                            tax_amt = (group['tax_group_amount'] / tasa) if tasa > 0 else 0
                            
                        rows += f"""
                            <tr>
                                <td style="{style_label}">{group['tax_group_name']}</td>
                                <td style="{style_value}">{symbol} {tax_amt:,.2f}</td>
                            </tr>
                        """

            # 3. Total
            rows += f"""
                <tr>
                    <td style="{style_total_label}">Total Ref.</td>
                    <td style="{style_total_value}">{symbol} {total:,.2f}</td>
                </tr>
            """
            
            # 4. Saldo Pendiente (si aplica)
            if residual != 0 and abs(residual) > 0.01: # Small tolerance
                rows += f"""
                    <tr>
                        <td style="{style_label}">Saldo Pendiente</td>
                        <td style="{style_value}">{symbol} {residual:,.2f}</td>
                    </tr>
                """

            # 5. Pagos (Legacy Logic Reused for HTML)
            payments_html = ""
            pay_term_lines = move.line_ids.filtered(lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable'))
            partials = pay_term_lines.mapped('matched_debit_ids') + pay_term_lines.mapped('matched_credit_ids')
            
            processed_partials = set()
            if partials:
                payments_html = '<div style="margin-top: 8px; border-top: 1px solid #eee; padding-top: 8px;">'
                for partial in partials:
                    if partial.id in processed_partials:
                        continue
                    processed_partials.add(partial.id)

                    counterpart_line = (partial.debit_move_id + partial.credit_move_id).filtered(lambda line: line not in move.line_ids)
                    if not counterpart_line:
                        continue
                        
                    # Recálculo de monto de pago
                    if partial.debit_move_id in move.line_ids:
                        amount_in_invoice_curr = partial.debit_amount_currency
                    else:
                        amount_in_invoice_curr = partial.credit_amount_currency
                    amount_in_invoice_curr = abs(amount_in_invoice_curr)

                    if use_company_amount:
                        # Factura USD -> Convertir a Bs
                        pay_amount = amount_in_invoice_curr * tasa
                    else:
                        # Factura Bs -> Convertir a USD
                        pay_amount = pay_amount = partial.amount / tasa if tasa else 0.0
                    
                    date_str = format_date(self.env, counterpart_line.date)
                    
                    payments_html += f"""
                        <div style="font-style: italic; color: #555; font-size: 0.9em; margin-bottom: 2px;">
                            <i class="fa fa-info-circle"></i> Pagado el {date_str}: 
                            <span style="font-weight: bold;">{symbol} {pay_amount:,.2f}</span>
                        </div>
                    """
                payments_html += '</div>'

            # Ensamblaje Final
            move.dual_summary_html = f"""
                <div class="o_dual_summary_box" style="border: 1px solid #ccc; padding: 15px; border-radius: 5px; background-color: #f9f9f9; margin-top: 20px;">
                    <div class="o_dual_title" style="font-weight: bold; color: #212529; border-bottom: 2px solid #0056b3; padding-bottom: 5px; margin-bottom: 10px; font-size: 1.1em;">
                        TOTALES DE REFERENCIA
                    </div>
                    <table style="width: 100%; border-collapse: collapse;">
                        {rows}
                    </table>
                    {payments_html}
                </div>
            """

    # Mantengo los campos viejos temporalmente para no romper la vista hasta que la actualice, 
    # pero ya no se usan para lógica
    display_untaxed_ref = fields.Char()
    display_tax_ref = fields.Char()
    display_tax_details = fields.Html()
    display_total_ref = fields.Char()
    display_residual_ref = fields.Char()
    dual_total_text = fields.Char()
    dual_untaxed_text = fields.Char()
    dual_tax_text = fields.Char()
    dual_residual_text = fields.Char()



