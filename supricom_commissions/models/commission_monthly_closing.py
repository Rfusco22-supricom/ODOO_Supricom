from odoo import models, fields


class CommissionMonthlyClosing(models.Model):
    _name = "commission.monthly.closing"
    _description = "Cierre Mensual de Comisiones"
    _order = "date desc"

    salesperson_id = fields.Many2one(
        "res.users", string="Vendedor", required=True, index=True
    )
    date = fields.Date(
        string="Mes de Cierre", required=True, help="Primer día del mes cerrado."
    )
    target_amount = fields.Float(string="Meta del Mes")
    total_collected = fields.Float(string="Total Cobrado")
    total_invoiced = fields.Float(string="Total Facturado (Ventas)")
    achievement_pct = fields.Float(string="% Cumplimiento Final")
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        help="Compañía a la que pertenece este cierre.",
    )

    _sql_constraints = [
        (
            "unique_salesperson_month",
            "unique(salesperson_id, date)",
            "Ya existe un cierre para este vendedor en este mes.",
        )
    ]
