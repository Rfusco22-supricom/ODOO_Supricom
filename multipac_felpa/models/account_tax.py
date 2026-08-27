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

from odoo import models, fields


class AccountTax(models.Model):
    _inherit = "account.tax"

    # Compatibility fields for Venezuelan localization
    l10n_ve_is_igtf = fields.Boolean(
        string='Is IGTF Tax',
        default=False,
        help='Compatibility field - Venezuelan IGTF (Impuesto a las Grandes Transacciones Financieras)'
    )
