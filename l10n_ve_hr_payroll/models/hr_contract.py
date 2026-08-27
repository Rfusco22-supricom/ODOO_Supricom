# -*- coding: utf-8 -*-
from odoo import models, fields

class HrContract(models.Model):
    _inherit = 'hr.contract'

    usd_salary = fields.Float(string='Salario USD', digits=(16, 2), help="Salario pactado en USD")
    usd_additional = fields.Float(string='Adicional USD', digits=(16, 2), help="Adicional pactado en USD")
