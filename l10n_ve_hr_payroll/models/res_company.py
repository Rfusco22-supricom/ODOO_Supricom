# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    bcv_interest_rate = fields.Float(string='Tasa interés BCV', digits=(16, 4))
