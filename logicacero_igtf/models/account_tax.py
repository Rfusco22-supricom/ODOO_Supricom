from odoo import models, fields

class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_ve_is_igtf = fields.Boolean(
        string='¿Es IGTF?',
        help='Marque esta casilla si este impuesto representa el IGTF (Impuesto a las Grandes Transacciones Financieras).'
    )
