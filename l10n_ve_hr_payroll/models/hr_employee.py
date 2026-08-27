# -*- coding: utf-8 -*-
from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    benefits_balance = fields.Float(string='Saldo prestaciones', digits=(16, 2), help="Saldo de prestaciones acumuladas")
    bcv_interest_rate = fields.Float(string='Tasa interés BCV', compute='_compute_bcv_interest_rate', store=False, digits=(16, 4), help="Tasa de interés del BCV (Mes actual)")
    paid_vacation_days = fields.Integer(string='Días pagados vacaciones', help="Días pagados vacaciones para localización de nómina")

    def _compute_bcv_interest_rate(self):
        today = fields.Date.context_today(self)
        current_year = str(today.year)
        current_month = str(today.month).zfill(2)
        
        for record in self:
            monthly_rate = self.env['hr.bcv.interest.rate'].search([
                ('year', '=', current_year),
                ('month', '=', current_month),
                ('company_id', '=', record.company_id.id)
            ], limit=1)
            
            if monthly_rate:
                record.bcv_interest_rate = monthly_rate.rate
            else:
                record.bcv_interest_rate = 0.0
