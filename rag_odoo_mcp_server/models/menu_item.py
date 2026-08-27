# -*- coding: utf-8 -*-
from odoo import fields, models


class menu_item(models.Model):
    _name = 'rag.mcp.menu.item'
    _description = "Menu Item"

    name = fields.Char('Menu')
    menu_id = fields.Integer('Menu ID')
