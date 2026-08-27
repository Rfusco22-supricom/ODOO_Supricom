# wizard/credit_extension_wizard.py
from odoo import models, fields, api, _

class SpiffCreditExtensionWizard(models.TransientModel):
    _name = 'spiff.credit.extension.wizard'
    _description = 'Asistente de Extensión de Crédito'

    order_id = fields.Many2one('sale.order', string="Pedido de Ventas", required=True)
    brand_id = fields.Many2one('spiff.brand', string="Marca que origina extensión")
    current_term_id = fields.Many2one('account.payment.term', string="Término Actual")
    new_days = fields.Integer(string="Nuevos Días de Crédito", required=True)
    extension_days = fields.Integer(string="Días Extra")
    
    def action_create_term_and_confirm(self):
        self.ensure_one()
        # Create new payment term
        term_name = _('%s días') % self.new_days
        new_term = self.env['account.payment.term'].create({
            'name': term_name,
            'line_ids': [(0, 0, {
                'value': 'percent',
                'value_amount': 100,
                'nb_days': self.new_days,
            })]
        })
        
        # Update order and confirm
        self.order_id.payment_term_id = new_term
        self.order_id.message_post(body=_(
            "📅 Términos de pago extendidos por la marca %s (+%s días extra).",
            self.brand_id.name, self.extension_days
        ))
        return self.order_id.with_context(skip_credit_extension=True).action_confirm()

    def action_confirm_without_extension(self):
        self.ensure_one()
        # Bypass my own check in action_confirm by using context or calling super
        return self.order_id.with_context(skip_credit_extension=True).action_confirm()
