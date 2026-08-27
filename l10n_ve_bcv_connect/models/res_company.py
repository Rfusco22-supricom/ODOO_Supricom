# -*- coding: utf-8 -*-
from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    bcv_usd_currency_id = fields.Many2one(
        'res.currency',
        string="BCV USD Currency",
        help="Currency to be updated with the BCV USD rate."
    )
    bcv_eur_currency_id = fields.Many2one(
        'res.currency',
        string="BCV EUR Currency",
        help="Currency to be updated with the BCV EUR rate."
    )
