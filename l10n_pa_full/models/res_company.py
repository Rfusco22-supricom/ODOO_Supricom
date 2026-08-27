# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import re


class ResCompany(models.Model):
    _inherit = 'res.company'

    is_panama = fields.Boolean(
        string='Es Panamá',
        compute='_compute_is_panama',
        store=True,
        help='Indica si el país de la compañía es Panamá'
    )
    ruc = fields.Char(
        string='RUC',
        related='partner_id.vat',
        store=True,
        readonly=False,
        help='Registro Único de Contribuyente de Panamá (relacionado con VAT del partner)'
    )

    @api.depends('partner_id.country_id')
    def _compute_is_panama(self):
        for company in self:
            company.is_panama = company.partner_id.country_id and company.partner_id.country_id.code == 'PA'
