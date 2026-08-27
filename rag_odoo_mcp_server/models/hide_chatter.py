# -*- coding: utf-8 -*-
from odoo import fields, models


class hide_chatter(models.Model):
    _name = 'rag.mcp.hide.chatter'
    _description = "Chatter Rights"

    access_management_id = fields.Many2one('rag.mcp.access.management', 'Access Management')
    model_id = fields.Many2one('ir.model', 'Model')

    hide_chatter = fields.Boolean('Chatter')
    hide_send_mail = fields.Boolean('Send Message')
    hide_log_notes = fields.Boolean('Log Notes')
    hide_schedule_activity = fields.Boolean('Schedule Activity')
