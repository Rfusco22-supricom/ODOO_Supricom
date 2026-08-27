# -*- coding: utf-8 -*-
from odoo import fields, models, tools
import datetime

class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    currency_id_dif = fields.Many2one("res.currency",
                                     string="Divisa de Referencia",
                                     default=lambda self: self.env.company.currency_id_dif )
    unit_cost_usd = fields.Monetary('Valor unitario $', readonly=True, default=0,currency_field='currency_id_dif')
    value_usd = fields.Monetary('Valor Total $', readonly=True, default=0,currency_field='currency_id_dif')

    remaining_value_usd = fields.Monetary('Valor Restante $', readonly=True, default=0,currency_field='currency_id_dif')

    tasa = fields.Float('Tasa de Referencia', readonly=True, force_save=True, digits='Dual_Currency_rate')

