from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CommissionManagerVolumeRange(models.Model):
    """
    Modelo para la Escala de Comisiones de Gerencia por Volumen de Venta/Cobranza.
    Implementa la tabla de la Imagen 1 para la Gerencia de Valencia:
      - < $800k: 0.20%
      - $800k - $1.49M: 0.30%
      - $1.5M - $1.99M: 0.40%
      - >= $2M: 0.50%
    """
    _name = "commission.manager.volume.range"
    _description = "Escala Gerencial por Volumen de Venta/Cobranza"
    _order = "company_id, vendor_type_id, amount_from asc"

    name = fields.Char(
        string="Nombre",
        compute="_compute_name",
        store=True,
        help="Descripción de la regla de volumen."
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía a la que aplica esta regla."
    )
    vendor_type_id = fields.Many2one(
        "commission.vendor.type",
        string="Tipo de Cargo / Rol",
        required=True,
        help="Tipo de vendedor gerencial al que aplica esta regla (ej. Gerente de Ventas Valencia)."
    )
    amount_from = fields.Float(
        string="Monto Cobrado Desde",
        required=True,
        default=0.0,
        help="Monto cobrado/facturado inicial del equipo en el mes."
    )
    amount_to = fields.Float(
        string="Monto Cobrado Hasta",
        required=True,
        default=799999.99,
        help="Monto cobrado/facturado final del equipo (usar 0 para sin límite)."
    )
    commission_percentage = fields.Float(
        string="% Comisión Gerente",
        required=True,
        default=0.20,
        help="Porcentaje de comisión a pagar sobre el total cobrado (ej. 0.20 para 0.20%)."
    )

    @api.depends("vendor_type_id", "amount_from", "amount_to", "commission_percentage")
    def _compute_name(self):
        for record in self:
            role_name = record.vendor_type_id.name if record.vendor_type_id else "Gerencia"
            if record.amount_to <= 0:
                amount_str = f"≥ ${record.amount_from:,.2f}"
            else:
                amount_str = f"${record.amount_from:,.2f} – ${record.amount_to:,.2f}"
            record.name = f"{role_name} | Volumen: {amount_str} -> {record.commission_percentage:.2f}%"

    @api.constrains("amount_from", "amount_to")
    def _check_amount_range(self):
        for record in self:
            if record.amount_from < 0:
                raise ValidationError("El monto inicial no puede ser negativo.")
            if record.amount_to > 0 and record.amount_to < record.amount_from:
                raise ValidationError("El monto final debe ser mayor al monto inicial.")
