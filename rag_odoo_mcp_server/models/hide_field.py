# -*- coding: utf-8 -*-
from odoo import fields, models


class hide_field(models.Model):
    _name = 'rag.mcp.hide.field'
    _description = "Fields Rights"

    access_management_id = fields.Many2one('rag.mcp.access.management', 'Access Management')
    model_id = fields.Many2one('ir.model', 'Model')
    field_id = fields.Many2many('ir.model.fields', 'rag_mcp_hide_field_ir_model_fields_rel', 'hide_field_id', 'ir_field_id',
                                'Field')
    invisible = fields.Boolean('Invisible')
    readonly = fields.Boolean('Read-Only')
    required = fields.Boolean('Required')
    external_link = fields.Boolean('Remove External Link')
