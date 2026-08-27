# -*- coding: utf-8 -*-
from odoo import fields, models


class action_data(models.Model):
    _name = 'rag.mcp.action.data'
    _description = "Action Data"

    name = fields.Char('Name')
    action_id = fields.Many2one('ir.actions.actions', 'Action')
