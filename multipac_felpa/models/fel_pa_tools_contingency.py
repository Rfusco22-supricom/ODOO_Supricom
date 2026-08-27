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

from odoo import fields, models, _, api
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError

class FelPAContingency(models.Model):
    _name = "fel_pa.tools.contingency"
    _description = "Panamá FEL Contingency"
    _rec_name = "motive"

    start_date = fields.Datetime(string="Start Date", default=fields.Datetime.now)
    end_date = fields.Datetime(string="End Date")
    motive = fields.Char(string="Motive", required=True)
    move_ids = fields.One2many('account.move', 'fel_pa_contingency_id', string="Invoices")
    journal_id = fields.Many2one('account.journal', string="Journal", required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Company', store=True)
    fel_pa_pac = fields.Selection(related='journal_id.fel_pa_pac', string="Panamá FEL PAC")
    active = fields.Boolean(string="Active")

    @api.constrains('active', 'journal_id')
    def _check_unique_active_contingency(self):
        for record in self:
            if record.active:
                existing = self.search([
                    ('journal_id', '=', record.journal_id.id),
                    ('active', '=', True),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(_('There is already an active contingency for this journal.'))

    def close_old_contingencies(self, hours_limit=24):
        limit_time = datetime.now() - timedelta(hours=hours_limit)
        old_contingencies = self.search([('active', '=', True), ('start_date', '<=', limit_time)])

        for contingency in old_contingencies:
            contingency.write({'active': False, 'end_date': fields.Datetime.now()})
            contingency.journal_id.write({'fel_pa_active_contingency_id': False})

        return True
    
    def close_contingency(self):
        self.ensure_one()
        self.write({'active': False, 'end_date': fields.Datetime.now()})
        self.journal_id.write({'fel_pa_active_contingency_id': False})
        return True