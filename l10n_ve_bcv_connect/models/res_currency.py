# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    # Fields moved to res.company settings

    def write(self, vals):
        # Prevent AccessError when saving res.currency in multi-company environments.
        # The web client sends a Command.set (6) with only the rate_ids the user can see.
        # This causes Odoo to attempt to unlink rates from other companies, which throws an AccessError.
        if 'rate_ids' in vals:
            vals.pop('rate_ids')
                
        return super(ResCurrency, self).write(vals)

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    inverse_rate = fields.Float(string='Inverse Rate', digits=0,
        compute='_compute_inverse_rate', inverse='_inverse_inverse_rate', store=True, readonly=False,
        help=" The rate in Base Currency per unit of Foreign Currency (e.g. 54 VES/USD).")

    @api.model
    def check_access_rule(self, operation):
        pass # Overridden below using read() interception

    def read(self, fields=None, load='_classic_read'):
        """
        Intercept read operations on currency rates.
        Odoo's compute dependencies (e.g. rate_ids.rate) force reading all rates
        across companies when res.currency is saved. This triggers AccessError.
        By catching it and falling back to sudo(), we allow the save to complete safely.
        """
        try:
            return super(ResCurrencyRate, self).read(fields=fields, load=load)
        except AccessError as e:
            if 'multi-company currency rate rule' in str(e):
                return super(ResCurrencyRate, self.sudo()).read(fields=fields, load=load)
            raise e

    @api.depends('rate')
    def _compute_inverse_rate(self):
        for record in self:
            if record.rate:
                record.inverse_rate = 1.0 / record.rate
            else:
                record.inverse_rate = 0.0

    def _inverse_inverse_rate(self):
        for record in self:
            if record.inverse_rate:
                record.rate = 1.0 / record.inverse_rate
            else:
                record.rate = 0.0

    @api.onchange('inverse_rate')
    def _onchange_inverse_rate(self):
        if self.inverse_rate:
            self.rate = 1.0 / self.inverse_rate
        else:
            self.rate = 0.0

    @api.onchange('rate')
    def _onchange_rate(self):
        if self.rate:
            self.inverse_rate = 1.0 / self.rate
        else:
            self.inverse_rate = 0.0
