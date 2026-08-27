# -*- coding: utf-8 -*-

from odoo import fields, models


class GenerateApiKeyWizard(models.TransientModel):
    _name = 'rag_odoo_mcp_server.generate_api_key_wizard'
    _description = 'Show generated MCP API key once'

    token_type = fields.Char(
        string='Token type',
        readonly=True,
        help='User token = read-only; Admin token = read+write.',
    )

    api_key_display = fields.Char(
        string='API key',
        readonly=True,
        help='Copy this key and use it in Claude/Cursor MCP config. It will not be shown again.',
    )
