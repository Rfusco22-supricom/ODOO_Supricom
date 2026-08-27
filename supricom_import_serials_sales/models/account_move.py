# -*- coding: utf-8 -*-
from odoo import models, _

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_open_import_serials_wizard(self):
        self.ensure_one()
        return {
            'name': _('Importar Seriales desde Excel'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.serials.sales.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_import_type': 'invoice',
            }
        }
