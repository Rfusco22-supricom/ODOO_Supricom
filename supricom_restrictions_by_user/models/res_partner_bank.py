# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group('supricom_restrictions_by_user.group_supricom_restricted'):
            raise UserError(_("No tiene permisos para crear nuevas cuentas de banco."))
        return super(ResPartnerBank, self).create(vals_list)
