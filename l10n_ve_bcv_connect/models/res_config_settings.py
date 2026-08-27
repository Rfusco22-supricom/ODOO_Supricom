# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bcv_usd_currency_id = fields.Many2one(
        related='company_id.bcv_usd_currency_id',
        readonly=False,
        string="BCV USD Currency"
    )
    bcv_eur_currency_id = fields.Many2one(
        related='company_id.bcv_eur_currency_id',
        readonly=False,
        string="BCV EUR Currency"
    )
