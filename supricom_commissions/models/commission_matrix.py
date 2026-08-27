from odoo import models, fields


class CommissionMatrix(models.Model):
    _name = "commission.matrix"
    _description = "Commission Matrix"
    _rec_name = "vendor_type_id"

    target_achievement_pct = fields.Float(
        string="% Cumplimiento Meta",
        required=True,
        default=0.0,
        help="Nivel mínimo de cumplimiento de la meta para que aplique esta regla (ej. 0.8 = 80%).",
    )

    vendor_type_id = fields.Many2one(
        "commission.vendor.type",
        string="Tipo de Vendedor",
        required=True,
        help="Tipo de vendedor al que aplica esta regla de comisión.",
    )
    commission_percentage = fields.Float(
        string="% Comisión",
        required=True,
        help="Porcentaje de comisión a pagar sobre la venta cobrada.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía a la que aplica esta regla.",
    )
