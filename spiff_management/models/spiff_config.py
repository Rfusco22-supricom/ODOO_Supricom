# models/spiff_config.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SpiffIncentive(models.Model):
    _name = "spiff.incentive"
    _description = "SPIFF Configuration Rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Referencia", required=True, tracking=True)
    start_date = fields.Date(required=True, tracking=True)
    end_date = fields.Date(required=True, tracking=True)
    active = fields.Boolean(default=True)

    # Logic Configuration [cite: 9]
    rule_type = fields.Selection(
        [
            ("product", "Por Producto (Cantidad)"),
            ("brand", "Por Marca (Monto Monetario)"),
        ],
        string="Tipo de Regla",
        required=True,
        default="product",
        tracking=True,
    )

    # Product Specifics [cite: 18]
    product_id = fields.Many2one("product.product", string="Producto")
    incentive_per_unit = fields.Monetary(
        string="Incentivo por Unidad", currency_field="currency_id"
    )

    # Brand Specifics
    brand_id = fields.Many2one(
        "spiff.brand", string="Marca", help="Coincidencia exacta con Marca del Producto"
    )
    target_amount = fields.Monetary(
        string="Bloque de Monto Objetivo", help="Ej. Cada $5000"
    )
    incentive_amount = fields.Monetary(
        string="Incentivo por Bloque", help="Ej. Recibe $100"
    )

    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company
    )

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for record in self:
            if record.start_date > record.end_date:
                raise ValidationError(
                    "La Fecha de Inicio no puede ser posterior a la Fecha Fin"
                )
