from odoo import models, fields

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    is_cash_payment = fields.Boolean(string="Pago de Contado", help="Marque esta casilla si este término de pago es de contado.")
