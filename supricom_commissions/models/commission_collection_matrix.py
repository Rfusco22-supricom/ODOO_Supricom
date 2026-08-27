from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CommissionCollectionMatrix(models.Model):
    """
    Modelo para la Matriz de Cobranza (Penalización por Morosidad).
    Define los rangos de días de retraso post-vencimiento y el porcentaje
    de comisión a reconocer (ej. 100%, 50%, 30%, 0%).
    
    Soporta configuración General (por Empresa) y Especial (por Vendedor).
    """
    _name = "commission.collection.matrix"
    _description = "Matriz de Cobranza (Días de Retraso)"
    _order = "company_id, user_id, days_from asc"

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
        help="Descripción generada automáticamente del rango de días."
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía a la que aplica esta regla de cobranza."
    )
    user_id = fields.Many2one(
        "res.users",
        string="Vendedor Especial",
        help="Si se especifica, esta regla aplicará únicamente a este vendedor "
             "(Configuración Especial). Si está vacío, aplica como regla General "
             "de la empresa."
    )
    days_from = fields.Integer(
        string="Días Retraso Desde",
        required=True,
        default=0,
        help="Días de retraso iniciales tras la fecha de vencimiento."
    )
    days_to = fields.Integer(
        string="Días Retraso Hasta",
        required=True,
        default=15,
        help="Días de retraso finales (usar un valor alto como 999 para sin límite)."
    )
    commission_factor_pct = fields.Float(
        string="% Comisión a Reconocer",
        required=True,
        default=100.0,
        help="Porcentaje de la comisión a pagar (ej. 100 para 100%, 50 para 50%, 30 para 30%, 0 para 0%)."
    )
    payment_type = fields.Selection(
        [
            ("all", "Contado y Crédito"),
            ("cash", "Solo Contado"),
            ("credit", "Solo Crédito"),
        ],
        string="Aplica a",
        default="all",
        required=True,
        help="Condición de pago a la que aplica esta escala."
    )
    notes = fields.Char(
        string="Notas",
        help="Observaciones sobre esta regla de mora."
    )

    @api.depends("days_from", "days_to", "commission_factor_pct", "user_id")
    def _compute_name(self):
        for record in self:
            scope = f"Vendedor: {record.user_id.name}" if record.user_id else "General (Empresa)"
            if record.days_to >= 999:
                days_str = f"A partir de {record.days_from} días"
            else:
                days_str = f"De {record.days_from} a {record.days_to} días"
            record.name = f"{scope} | {days_str} -> {record.commission_factor_pct:.1f}% Comisión"

    @api.constrains("days_from", "days_to")
    def _check_days_range(self):
        for record in self:
            if record.days_from < 0:
                raise ValidationError("Los días de retraso iniciales no pueden ser negativos.")
            if record.days_to < record.days_from:
                raise ValidationError("Los días de retraso finales deben ser mayores o iguales a los días iniciales.")
