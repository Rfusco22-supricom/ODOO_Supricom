# -*- coding: utf-8 -*-
from odoo import fields, models, api, SUPERUSER_ID, _
from odoo.exceptions import UserError, AccessDenied
import logging

_logger = logging.getLogger(__name__)


def _mcp_access_tables_ready(cr):
    """Return True only once this module's access tables exist.

    These overrides read the rag.mcp.access.management relation. During module
    install/upgrade (e.g. when default users are created/written) they can fire
    before the tables are created, which would abort the load transaction.
    ``to_regclass`` returns NULL (no error) when the table is absent, so this is
    safe to call inside a live transaction.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_access_management'), to_regclass('rag_mcp_access_domain_ah')")
        row = cr.fetchone()
        return bool(row and row[0] and row[1])
    except Exception:
        return False


class res_users(models.Model):
    _inherit = 'res.users'

    rag_mcp_access_management_ids = fields.Many2many('rag.mcp.access.management', 'rag_mcp_access_management_users_rel_ah', 'user_id',
                                             'access_management_id', 'Access Pack')

    def write(self, vals):
        res = super(res_users, self).write(vals)
        # Assigning/removing a user's access packs from the *user* form does not
        # go through rag.mcp.access.management.write, so invalidate here too. This is the
        # targeted replacement for the old per-/web-request clear_all_caches().
        if 'rag_mcp_access_management_ids' in vals:
            try:
                self.env.registry.clear_all_caches()
            except Exception:
                pass
        if not _mcp_access_tables_ready(self._cr):
            return res
        for access in self.rag_mcp_access_management_ids:
            if self.env.company in access.company_ids and access.readonly:
                if self.has_group('base.group_system') or self.has_group('base.group_erp_manager'):
                    raise UserError(_('Admin user can not be set as a read-only..!'))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super(res_users, self).create(vals_list)
        if not _mcp_access_tables_ready(self._cr):
            return res
        for record in self:
            for access in record.rag_mcp_access_management_ids:
                if self.env.company in access.company_ids and access.readonly:
                    if record.has_group('base.group_system') or record.has_group('base.group_erp_manager'):
                        raise UserError(_('Admin user can not be set as a read-only..!'))
        return res

    @classmethod
    def _login(cls, db, login, password, user_agent_env):
        res = super(res_users, cls)._login(db, login, password, user_agent_env=user_agent_env)
        try:
            with cls.pool.cursor() as cr:
                if not _mcp_access_tables_ready(cr):
                    return res
                self = api.Environment(cr, SUPERUSER_ID, {})[cls._name]
                access_management_obj = self.env['rag.mcp.access.management']
                if access_management_obj.search([('user_ids', 'in', res), ('disable_login', '=', True)]).id:
                    raise AccessDenied()
        except AccessDenied:
            _logger.info("Login failed for db:%s login:%s from ", db, login)
            raise
        return res
