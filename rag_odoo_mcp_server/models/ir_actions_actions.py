# -*- coding: utf-8 -*-
from odoo import api, models


def _mcp_access_tables_ready(cr):
    """Return True only once this module's tables exist.

    These overrides create rag.mcp.action.data rows for every ir.actions.actions record.
    During module install/upgrade they can fire before action_data exists, which
    would abort the load transaction. ``to_regclass`` returns NULL (no error)
    when the table is absent, so this is safe inside a live transaction.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_action_data')")
        row = cr.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


class ir_actions_actions(models.Model):
    _inherit = 'ir.actions.actions'

    @api.model_create_multi
    def create(self, vals_list):
        res = super(ir_actions_actions, self).create(vals_list)
        if not _mcp_access_tables_ready(self._cr):
            return res
        action_data_obj = self.env['rag.mcp.action.data']
        for record in res:
            action_data_obj.create({'name': record.name, 'action_id': record.id})
        return res

    def unlink(self):
        if _mcp_access_tables_ready(self._cr):
            action_data_obj = self.env['rag.mcp.action.data']
            for record in self:
                action_data_obj.search([('action_id', '=', record.id)]).unlink()
        return super(ir_actions_actions, self).unlink()
