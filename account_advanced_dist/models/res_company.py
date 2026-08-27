# models/res_company.py
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = "res.company"

    # Cuentas globales para operaciones Inter-Compañía
    intercompany_receivable_account_id = fields.Many2one(
        "account.account", 
        string="Cuenta a Cobrar Inter-Cía (Global)",
        help="Cuenta utilizada cuando esta compañía debe cobrarle a otra (Activo)."
    )
    intercompany_payable_account_id = fields.Many2one(
        "account.account", 
        string="Cuenta a Pagar Inter-Cía (Global)",
        help="Cuenta utilizada cuando esta compañía le debe a otra (Pasivo)."
    )

    intercompany_payment_journal_id = fields.Many2one(
        "account.journal",
        string="Diario para Pagos Inter-Cía/Terceros",
        domain=[("type", "=", "general")],
        help="Diario contable utilizado para registrar los asientos de reclasificación de pagos de terceros y transferencias inter-compañía."
    )

    exchange_diff_transit_account_id = fields.Many2one(
        "account.account",
        string="Cuenta Tránsito Diferencial",
        help="Cuenta temporal para alojar la diferencia en cambio antes de aplicarla a la factura."
    )
