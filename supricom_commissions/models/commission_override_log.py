from odoo import models, fields


class CommissionOverrideLog(models.Model):
    _name = "commission.override.log"
    _description = "Log de Excepción de Comisiones"
    _order = "date desc"

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        required=True,
        default=lambda self: self.env.user,
        help="Usuario que realizó la modificación.",
    )
    date = fields.Datetime(
        string="Fecha",
        default=fields.Datetime.now,
        required=True,
        help="Fecha y hora del evento.",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Factura",
        required=True,
        help="Factura relacionada con el evento.",
    )
    partner_id = fields.Many2one(
        "res.partner", string="Vendedor (Partner)", help="Vendedor afectado por el cambio."
    )
    salesperson_id = fields.Many2one(
        "res.users",
        string="Vendedor (Usuario)",
        help="Usuario vendedor asociado a la comisión.",
    )
    payment_id = fields.Many2one(
        "account.payment",
        string="Abono (Pago)",
        help="Pago específico que genera esta comisión.",
    )
    commission_amount = fields.Monetary(
        string="Comisión Resultante",
        currency_field="currency_id",
        help="Monto de comisión calculado para este evento.",
    )
    amount_paid = fields.Monetary(
        string="Monto Cobrado",
        currency_field="currency_id",
        help="Monto del abono que generó esta comisión.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
    )
    description = fields.Text(
        string="Descripción del Cambio",
        help="Detalle de la modificación realizada o alerta generada.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
        help="Compañía donde se generó el evento.",
    )
    note = fields.Char(
        string="Nota Autorización",
        help="Nota u observación ingresada al autorizar la excepción.",
    )
