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

class FelPAToolsCreateContingency(models.TransientModel):
    _name = 'fel_pa.tools.create_contingency_wizard'
    _description = "Panamá FEL Create Contingency"

    motive = fields.Char(string="Motive", required=True)
    journal_id = fields.Many2one('account.journal', string="Journal", required=True, default=lambda self: self.env.context.get('active_id', False))

    def action_create_contingency(self):
        self.ensure_one()

        contingency = self.env['fel_pa.tools.contingency'].create({
            'motive': self.motive,
            'journal_id': self.journal_id.id,
            'active': True,
        })

        self.journal_id.write({
            'fel_pa_active_contingency_id': contingency.id,
        })

        return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Contingency Created Successfully'),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
