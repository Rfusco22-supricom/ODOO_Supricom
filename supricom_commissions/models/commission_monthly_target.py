from odoo import models, fields, api


class CommissionMonthlyTarget(models.Model):
    _name = "commission.monthly.target"
    _description = "Commission Monthly Target"
    _rec_name = "name"

    _sql_constraints = [
        (
            "vendedor_date_company_unique",
            "unique(vendedor_id, date_from, company_id)",
            "Ya existe una meta para este vendedor en este periodo y compañía.",
        ),
        (
            "team_date_company_unique",
            "unique(team_id, date_from, company_id)",
            "Ya existe una meta para esta sucursal en este periodo y compañía.",
        )
    ]

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)

    @api.depends("date_from", "vendedor_id", "team_id", "target_type")
    def _compute_name(self):
        # Month mapping
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
        for record in self:
            if record.date_from:
                month = record.date_from.month
                year = record.date_from.year
                month_str = month_names.get(month, "")
                if record.target_type == 'individual' and record.vendedor_id:
                    record.name = f"Meta {month_str} {year} - {record.vendedor_id.name}"
                elif record.target_type == 'branch' and record.team_id:
                    record.name = f"Meta {month_str} {year} - {record.team_id.name}"
                else:
                    record.name = f"Meta {month_str} {year}"
            else:
                record.name = "Meta Mensual"

    target_type = fields.Selection(
        [("individual", "Individual"), ("branch", "Sucursal")],
        string="Tipo de Meta",
        default="individual",
        required=True,
    )
    vendedor_id = fields.Many2one(
        "res.partner",
        string="Vendedor",
        help="Vendedor al que se le asigna esta meta mensual (Aplica si el tipo es Individual).",
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Sucursal / Equipo",
        help="Sucursal a la que se le asigna esta meta (Aplica si el tipo es Sucursal).",
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("done", "Cerrado")],
        string="Estado",
        default="draft",
        help="Las metas cerradas no pueden ser modificadas para proteger el historial de comisiones.",
    )
    achievement_percentage = fields.Float(
        string="% Cumplimiento Alcanzado",
        help="Porcentaje de cumplimiento registrado al momento del cierre del mes.",
        readonly=True,
    )
    date_from = fields.Date(
        string="Fecha Inicio",
        required=True,
        help="Fecha de inicio del periodo de la meta.",
    )
    date_to = fields.Date(
        string="Fecha Fin", required=True, help="Fecha de fin del periodo de la meta."
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
        required=True,
        help="Moneda en la que se expresa el monto de la meta.",
    )
    amount_target = fields.Monetary(
        string="Monto Meta",
        currency_field="currency_id",
        help="Monto objetivo de ventas a cobrar para este periodo.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía a la que pertenece esta meta.",
    )
