# -*- coding: utf-8 -*-
from odoo.addons.web.controllers.utils import ensure_db
from odoo.addons.web.controllers.action import Action
from odoo.addons.web.controllers.home import Home
from odoo.tools.translate import _
from odoo.http import request
from odoo.exceptions import UserError
from odoo import http
from urllib.parse import urlencode


def _mcp_access_tables_ready(cr):
    """Return True only once this module's access tables exist.

    These controllers run on every /web and /web/action request and query the
    access_management / remove_action tables. If the module is in a half-installed
    state (registered but tables not yet created), querying them raises
    UndefinedTable and 500s the whole web client. ``to_regclass`` returns NULL
    (no error) when the table is absent, so we can degrade gracefully instead.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_access_management'), to_regclass('rag_mcp_remove_action')")
        row = cr.fetchone()
        return bool(row and row[0] and row[1])
    except Exception:
        return False


class AccessAction(Action):

    @http.route('/web/action/run', type='json', auth="user")
    def run(self, action_id, context=None):
        res = super(AccessAction, self).run(action_id, context)
        actions_and_prints = []
        if res and _mcp_access_tables_ready(request.env.cr):
            for access in request.env['rag.mcp.remove.action'].search(
                    [('access_management_id.company_ids', 'in', request.env.company.id),
                     ('access_management_id', 'in', request.env.user.rag_mcp_access_management_ids.ids),
                     ('model_id.model', '=', res.get('res_model'))]):
                actions_and_prints = actions_and_prints + access.mapped('report_action_ids.action_id').ids
                actions_and_prints = actions_and_prints + access.mapped('server_action_ids.action_id').ids
                for view_data in access.view_data_ids:
                    for b_view in res['views']:
                        if b_view[1] == view_data.techname:
                            res['views'].pop(res['views'].index(b_view))
        return res

    @http.route('/web/action/load', type='json', auth="user")
    def load(self, action_id, additional_context=None):
        res = super(AccessAction, self).load(action_id, additional_context=additional_context)
        if res and _mcp_access_tables_ready(request.env.cr):
            cids = request.httprequest.cookies.get('cids') and \
                   request.httprequest.cookies.get('cids').split(',')[0] or request.env.company.id
            for view_data in set(request.env['rag.mcp.remove.action'].sudo().search(
                    [('view_data_ids', '!=', False),
                     ('access_management_id.company_ids', 'in', int(cids)),
                     ('access_management_id', 'in', request.env.user.rag_mcp_access_management_ids.ids),
                     ('model_id.model', '=', res.get('res_model'))]).mapped('view_data_ids.techname')):
                for views_data_list in res.get('views'):
                    if view_data == views_data_list[1]:
                        res['views'].pop(res['views'].index(views_data_list))
            if 'views' in res.keys() and not len(res.get('views')):
                raise UserError(
                    _("You don't have the permission to access any views. Please contact to administrator."))
        return res


class AccessHome(Home):

    # Odoo 17's Home.web_client only registers '/web'. Mirror that decorator
    # exactly — extending route patterns is what would silently break controller
    # inheritance, not matching them.
    @http.route('/web', type='http', auth="none")
    def web_client(self, s_action=None, **kw):
        ensure_db()
        # NOTE: we intentionally do NOT clear the registry caches on every /web
        # request — that defeats Odoo's menu/view/rule/field caching for the
        # whole system on every page load. Access-pack changes already invalidate
        # caches in rag.mcp.access.management create/write/unlink and in res.users.write
        # (when rag_mcp_access_management_ids changes), which covers every edit path.

        if request.session.uid and _mcp_access_tables_ready(request.env.cr):
            # Inspect *every* debug value, not just the first. Company switching
            # (and repeated redirects) can leave several ``debug`` keys in the
            # query string; reading only the first one meant the guard below
            # never saw the ``debug=0`` we appended, so it redirected forever
            # ("Too many redirects"). Dev mode is only actually "on" when some
            # value is neither '0' nor empty.
            debug_vals = request.httprequest.args.getlist('debug')
            debug_on = any(v not in ('0', '') for v in debug_vals)
            if debug_on:
                cids = request.httprequest.cookies.get('cids') and \
                       request.httprequest.cookies.get('cids').split(',')[0] or 1
                access_management = request.env['rag.mcp.access.management'].sudo().search(
                    [('active', '=', True), ('company_ids', 'in', int(cids)),
                     ('disable_debug_mode', '=', True),
                     ('user_ids', 'in', request.session.uid)], limit=1)
                if access_management:
                    # Rewrite the query so ``debug`` is a single '0' value —
                    # never append, or we stack params and loop. Preserves all
                    # other args (action/model/cids/etc.).
                    args = request.httprequest.args.copy()
                    args.setlist('debug', ['0'])
                    return request.redirect(
                        '%s?%s' % (request.httprequest.path,
                                   urlencode(list(args.items(multi=True)))))

        return super(AccessHome, self).web_client(s_action=s_action, **kw)
