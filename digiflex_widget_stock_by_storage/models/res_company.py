# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    storage_location_id = fields.Many2one(
        'stock.location',
        string='Ubicación de Almacenamiento Principal',
        domain="[('usage', '=', 'internal')]",
        help='Ubicación por defecto utilizada para calcular el stock a la mano en el botón inteligente de ubicación.'
    )
