# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import fields, models, _

class FelPACounty(models.Model):
    _name = "fel_pa.tools.county"
    _description = "Panamá FEL County"

    name = fields.Char(string="Name")
    fel_pa_code = fields.Char(string="Panamá FEL County Code")
    city_id = fields.Many2one('res.city', string="City")