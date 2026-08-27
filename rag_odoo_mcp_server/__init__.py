# -*- coding: utf-8 -*-
# MCP is exposed via the Odoo HTTP server at /mcp/sse and /mcp/messages (no separate process).
# Optional standalone: python -m rag_odoo_mcp_server.mcp_server --host 0.0.0.0 --port 8000
# Patch request handling first so session.db is set from URL/header/token before routing (fixes 404).
from . import patch_http
patch_http.apply_patch()

from . import controllers
from . import models


def _post_init_fix_body_arch(env):
    """Fix existing mailing records missing <style id="design-element"> or o_editable.

    In Odoo 17 the post_init_hook signature changed to take env directly (was cr, registry).
    """
    # 1) Add <style id="design-element"> inside .o_layout if missing
    env.cr.execute("""
        UPDATE mailing_mailing
        SET body_arch = REGEXP_REPLACE(
            body_arch,
            '(<div[^>]*class="o_layout[^"]*"[^>]*>)',
            E'\\1\n  <style id="design-element"></style>',
            'g'
        )
        WHERE body_arch LIKE '%%o_layout%%'
          AND body_arch NOT LIKE '%%design-element%%'
    """)
    # 2) Add o_editable on oe_structure div if missing (required as drop zone)
    env.cr.execute("""
        UPDATE mailing_mailing
        SET body_arch = REPLACE(body_arch, 'oe_structure', 'oe_structure o_editable')
        WHERE body_arch LIKE '%%oe_structure%%'
          AND body_arch NOT LIKE '%%o_editable%%'
    """)

    # 3) Access Manager: snapshot existing actions/menus into rag.mcp.action.data and
    # rag.mcp.menu.item so access rules can reference them without a dedicated admin UI.
    # (Ported from rag_odoo_mcp_server_access.post_install_action_dup_hook.)
    action_data_obj = env['rag.mcp.action.data']
    menu_item_obj = env['rag.mcp.menu.item']
    existing_actions = set(action_data_obj.search([]).mapped('action_id.id'))
    for action in env['ir.actions.actions'].search([]):
        if action.id in existing_actions:
            continue
        action_data_obj.create({'name': action.name, 'action_id': action.id})
    existing_menus = set(menu_item_obj.search([]).mapped('menu_id'))
    for menu in env['ir.ui.menu'].search([]):
        if menu.id in existing_menus:
            continue
        menu_item_obj.create({'name': menu.display_name, 'menu_id': menu.id})
