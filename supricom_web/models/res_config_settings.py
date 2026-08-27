# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    quotation_only = fields.Boolean(
        related='website_id.quotation_only',
        readonly=False,
        string='Solo Cotización',
        help="Si está marcado, se desactivará el flujo de pago y facturación y se convertirá en un flujo de cotizaciones para el sitio web seleccionado.",
    )
