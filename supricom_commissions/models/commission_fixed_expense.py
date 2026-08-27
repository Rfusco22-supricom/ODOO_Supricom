from odoo import models, fields, api


class CommissionFixedExpense(models.Model):
    _name = "commission.fixed.expense"
    _description = "Commission Fixed Expense"

    name = fields.Char(
        string="Referencia",
        compute="_compute_name",
        store=True,
    )
    date_from = fields.Date(
        string="Fecha Inicio",
        required=True,
        help="Inicio del periodo para el cálculo del gasto fijo.",
    )

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        month_map = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        }
        for record in self:
            if record.date_from:
                month_name = month_map.get(record.date_from.month, "")
                year = record.date_from.year
                record.name = f"{month_name} {year}"
            else:
                record.name = "Nuevo Gasto Fijo"
    date_to = fields.Date(
        string="Fecha Fin",
        required=True,
        help="Fin del periodo para el cálculo del gasto fijo.",
    )
    amount = fields.Monetary(
        string="Monto Gasto Fijo",
        currency_field="currency_id",
        required=True,
        help="Monto total de gastos fijos de la empresa en este periodo.",
    )
    deduction_percentage = fields.Float(
        string="% Deducción",
        readonly=True,
        help="Porcentaje calculado que se descontará de las comisiones (Gasto / Ventas Totales).",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    def action_calculate_deduction(self):
        for record in self:
            sales_domain = [
                ("date", ">=", record.date_from),
                ("date", "<=", record.date_to),
                ("move_type", "in", ["out_invoice"]),
                ("state", "=", "posted"),
                ("company_id", "=", record.company_id.id),
            ]
            invoices = self.env["account.move"].search(sales_domain)
            
            # Convert each invoice amount to the expense currency
            total_sales = 0.0
            for inv in invoices:
                if inv.currency_id == record.currency_id:
                    total_sales += inv.amount_untaxed
                else:
                    converted = inv.currency_id._convert(
                        inv.amount_untaxed,
                        record.currency_id,
                        record.company_id,
                        inv.date or fields.Date.today(),
                    )
                    total_sales += converted

            if total_sales > 0:
                record.deduction_percentage = record.amount / total_sales
            else:
                record.deduction_percentage = 0.0

