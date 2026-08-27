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

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

class FelPAToolsProductUnspscCategory(models.Model):
    _name = "fel_pa.tools.product_unspsc_category"
    _description = "Panamá FEL Product UNSPSC Category"

    name = fields.Char(string="Name")
    fel_pa_code = fields.Char(string="FEL PA Code")