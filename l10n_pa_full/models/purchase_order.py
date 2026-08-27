# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_panama = fields.Boolean(
        string='Es Panamá',
        related='partner_id.is_panama',
        store=True
    )
    ruc = fields.Char(
        string='RUC',
        related='partner_id.ruc',
        store=False
    )
