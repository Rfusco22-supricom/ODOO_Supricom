# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    storage_location_id = fields.Many2one(
        related='company_id.storage_location_id',
        readonly=False,
        string='Ubicación de Almacenamiento Principal',
        domain="[('usage', '=', 'internal')]",
        help='Ubicación por defecto utilizada para calcular el stock a la mano en el botón inteligente de ubicación.'
    )
