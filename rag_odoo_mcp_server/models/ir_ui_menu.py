# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.http import request


def _mcp_access_tables_ready(cr):
    """Return True only once this module's access tables exist.

    These overrides read rag.mcp.access.management / create rag.mcp.menu.item rows. During
    module install/upgrade they can fire before the tables are created, which
    would abort the load transaction. ``to_regclass`` returns NULL (no error)
    when the table is absent, so this is safe inside a live transaction.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_access_management'), to_regclass('rag_mcp_menu_item')")
        row = cr.fetchone()
        return bool(row and row[0] and row[1])
    except Exception:
        return False


class ir_ui_menu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def search(self, args, offset=0, limit=None, order=None):
        ids = super(ir_ui_menu, self).search(args, offset=0, limit=None, order=order)
        if not _mcp_access_tables_ready(self._cr):
            if offset:
                ids = ids[offset:]
            if limit:
                ids = ids[:limit]
            return ids
        user = self.env.user
        # No HTTP request during CLI install/upgrade (-i/-u), crons, tests and odoo shell:
        # fall back to the environment's company instead of crashing on the unbound proxy.
        cookie_cids = None
        if request and getattr(request, 'httprequest', None):
            cookie_cids = request.httprequest.cookies.get('cids')
        cids = cookie_cids and cookie_cids.split(',')[0] or self.env.company.id
        for menu_id in user.rag_mcp_access_management_ids.filtered(
                lambda line: int(cids) in line.company_ids.ids).mapped('hide_menu_ids.menu_id'):
            menu_id = self.browse(menu_id)
            if menu_id in ids:
                ids = ids - menu_id
        if offset:
            ids = ids[offset:]
        if limit:
            ids = ids[:limit]
        return ids

    @api.model_create_multi
    def create(self, vals_list):
        res = super(ir_ui_menu, self).create(vals_list)
        if not _mcp_access_tables_ready(self._cr):
            return res
        menu_item_obj = self.env['rag.mcp.menu.item']
        for record in res:
            menu_item_obj.create({'name': record.display_name, 'menu_id': record.id})
        return res

    def unlink(self):
        if _mcp_access_tables_ready(self._cr):
            menu_item_obj = self.env['rag.mcp.menu.item']
            for record in self:
                menu_item_obj.search([('menu_id', '=', record.id)]).unlink()
        return super(ir_ui_menu, self).unlink()
