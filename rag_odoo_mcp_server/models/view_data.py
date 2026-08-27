# -*- coding: utf-8 -*-
from odoo import fields, models


class view_data(models.Model):
    _name = 'rag.mcp.view.data'
    _description = "View Data"

    name = fields.Char('Name')
    techname = fields.Char('Tech Name')
