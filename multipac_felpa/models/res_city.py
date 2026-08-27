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

from odoo import models, fields, _

class ResCity(models.Model):
    _inherit = "res.city"

    fel_pa_code = fields.Char(string="Panamá FEL City Code")