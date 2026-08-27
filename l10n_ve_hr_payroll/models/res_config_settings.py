# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bcv_interest_rate = fields.Float(
        related='company_id.bcv_interest_rate',
        readonly=False,
        string="Tasa interés BCV"
    )
