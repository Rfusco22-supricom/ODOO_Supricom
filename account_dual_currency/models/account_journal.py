from odoo import models, fields

class AccountJournal(models.Model):
    _inherit = "account.journal"

    exclude_from_dual_currency = fields.Boolean(
        string="Excluir de Cálculos Duales",
        help="Si está marcado, los apuntes de este diario tendrán sus valores en USD (debit_usd, credit_usd, tax_today) forzados a 0. Útil para diarios de Diferencia de Cambio o Ajustes."
    )
