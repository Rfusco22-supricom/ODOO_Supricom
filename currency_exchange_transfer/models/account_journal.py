from odoo import models, fields

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    inbound_transfer_auth_user_ids = fields.Many2many(
        'res.users', 
        string='Usuarios Autorizados para Recibir (Transferencias)',
        help="Usuarios autorizados para validar la recepción de dinero en este diario desde el módulo de Compra/Transferencia."
    )
