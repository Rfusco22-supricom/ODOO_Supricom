# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCountry(models.Model):
    _inherit = "res.country"
    
    nacionality = fields.Char(string="Nacionalidad", translate=True)