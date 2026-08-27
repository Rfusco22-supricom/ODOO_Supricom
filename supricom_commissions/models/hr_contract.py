from odoo import models, fields


class HrContract(models.Model):
    _inherit = "hr.contract"

    commission_vendor_type_id = fields.Many2one(
        "commission.vendor.type",
        string="Tipo de Vendedor (Comisiones)",
        help="Tipo de vendedor aplicado para el cálculo de comisiones durante la vigencia de este contrato.",
    )
    fix_commission_rate = fields.Float(
        string="Tasa de Comisión Fija (%)",
        help="Si se establece (> 0.0), esta tasa fija tendrá prioridad sobre la matriz del Tipo de Vendedor.",
    )
