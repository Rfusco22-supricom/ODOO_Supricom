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
    _name = 'fel_pa.tools.cancel_wizard'
    _description = "Panamá FEL Cancel Wizard"

    def get_default(self):
        if self.env.context.get("motive", False):
            return self.env.context.get("motive")
        return False

    invoices_ids = fields.Many2many("account.move", string="Invoices", required=True, default=lambda self: self.env.context.get("active_ids", []))
    name = fields.Text(string="Cancel Motive", required=True, default=get_default)

    def action_cancel(self):
        for rec in self:
            for invoice in rec.invoices_ids.filtered(lambda x: x.state in ('posted','draft') and x.fel_pa_state in ('accepted')):
                invoice.fel_pa_cancel(motive=self.name)

        return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Invoices Cancelled Successfully'),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }