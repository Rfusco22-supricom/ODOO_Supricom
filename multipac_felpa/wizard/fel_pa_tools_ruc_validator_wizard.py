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

from odoo import fields, models, _

class FelPAToolsCancelWizard(models.TransientModel):
    _name = 'fel_pa.tools.ruc_validator_wizard'
    _description = "Panamá FEL RUC Validator Wizard"

    def get_ruc_default(self):
        if self.env.context.get("vat", False):
            return self.env.context.get("vat")
        return False
    
    def get_recipient_type_default(self):
        if self.env.context.get("fel_pa_recipient_type", False):
            return self.env.context.get("fel_pa_recipient_type")
        return False
    
    def get_fel_pa_taxpayer_type_default(self):
        if self.env.context.get("fel_pa_taxpayer_type", False):
            return self.env.context.get("fel_pa_taxpayer_type")
        return False

    partner_id = fields.Many2one('res.partner', string="Partner", required=True, default=lambda self: self._context.get('active_id'), readonly=True)
    fel_pa_ruc = fields.Char(string="RUC", required=True, default=get_ruc_default)
    fel_pa_recipient_type = fields.Selection([('01', "Taxpayer"), ('02', "Normal Consumer"), ('03', "Government"), ('04', "Foreign")], string="Receipentent Type", default=get_recipient_type_default, required=True)
    fel_pa_taxpayer_type = fields.Selection([('1', "Person"), ('2', "Business")], string="Taxpayer Type", required=True, default=get_fel_pa_taxpayer_type_default)

    def action_validate_ruc(self):
        result = self.partner_id.ruc_validation(self.fel_pa_ruc, self.fel_pa_taxpayer_type)
        if result:
            ruc, fel_pa_company_name, fel_pa_dv, fel_pa_affiliated_fe, fel_pa_taxpayer_type = result
            vals = {}
            vals['fel_pa_company_name'] = fel_pa_company_name
            vals['fel_pa_dv'] = fel_pa_dv
            vals['fel_pa_affiliated_fe'] = fel_pa_affiliated_fe
            vals['fel_pa_taxpayer_type'] = fel_pa_taxpayer_type
            vals['fel_pa_recipient_type'] = self.fel_pa_recipient_type
            vals['name'] = fel_pa_company_name
            vals['vat'] = ruc
            self.partner_id.write(vals)
            return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('RUC Validated'),
                        'type': 'success',
                        'sticky': False,
                        'message': _('The RUC has been validated successfuly: %s') % ruc,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
        else:
            return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('RUC Validation Failed'),
                        'type': 'warning',
                        'sticky': False,
                        'message': _('The RUC validation failed. Please check the RUC and try again.'),
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
