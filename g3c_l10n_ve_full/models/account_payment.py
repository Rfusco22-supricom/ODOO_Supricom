# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    sent_to_bank = fields.Boolean(
        string='Enviado a Banco (Compat)',
        compute='_compute_dummy_sent_to_bank',
        store=False,
    )

    payment_registration_date = fields.Date(
        string='Fecha de Registro (Confirmación)',
        readonly=True,
        copy=False,
        help='Fecha en la que el pago fue confirmado.'
    )

    def action_post(self):
        res = super(AccountPayment, self).action_post()
        for payment in self:
            if not payment.payment_registration_date:
                payment.payment_registration_date = fields.Date.context_today(self)
        return res

    def _compute_dummy_sent_to_bank(self):
        for rec in self:
            rec.sent_to_bank = False

    def get_tax_today(self):
        id_usd = self.env['res.currency'].search([('name','=','USD')], limit=1)
        tax = self.env['res.currency.rate'].search([('currency_id', '=', id_usd.id)], limit=1, order='name desc')
        return tax.inverse_company_rate

    # @api.model
    # def default_get(self, fields_list):
    #     print('SE EJECUTA')
    #     res = super(AccountPayment, self).default_get(fields_list)
    #     if 'tax_today' in fields_list:
    #         res['tax_today'] = self.get_tax_today()
    #         print(res['tax_today'])
    #     return res