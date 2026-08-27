# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.tools import config
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval
from odoo.http import request
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Optional dependency: advanced_web_domain_widget
try:
    from odoo.addons.advanced_web_domain_widget.models.domain_prepare import prepare_domain_v2
except ImportError:
    def prepare_domain_v2(dom_tuple):
        """Fallback: just return the tuple as a list if advanced_web_domain_widget is not installed."""
        return [dom_tuple]


def _mcp_access_tables_ready(cr):
    """Return True only once this module's access tables exist.

    The override below runs raw SQL / ORM searches against access_management and
    access_domain_ah. Those overrides can fire during module install/upgrade
    (e.g. ir.rule._compute_domain while load_modules searches ir.module.module)
    before the tables are created, which would abort the whole load transaction.
    ``to_regclass`` returns NULL (no error) when the table is absent, so this is
    safe to call inside a live transaction.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_access_management'), to_regclass('rag_mcp_access_domain_ah')")
        row = cr.fetchone()
        return bool(row and row[0] and row[1])
    except Exception:
        return False


class ir_rule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    @tools.conditional(
        'xml' not in config['dev_mode'],
        tools.ormcache('self.env.uid', 'self.env.su', 'model_name', 'mode',
                       'tuple(self._compute_domain_context_values())'),
    )
    def _compute_domain(self, model_name, mode="read"):
        res = super(ir_rule, self)._compute_domain(model_name, mode)

        # During install/upgrade this can run before the access tables exist;
        # bail out cleanly so module loading never crashes.
        if not _mcp_access_tables_ready(self._cr):
            return res

        read_value = True
        self._cr.execute("SELECT state FROM ir_module_module WHERE name='rag_odoo_mcp_server'")
        data = self._cr.fetchone() or False

        self._cr.execute("SELECT id FROM ir_module_module WHERE state IN ('to upgrade', 'to remove','to install')")
        all_data = self._cr.fetchone() or False

        if data and data[0] != 'installed':
            read_value = False
        model_list = ['mail.activity', 'res.users.log', 'res.users', 'mail.channel', 'mail.alias', 'bus.presence',
                      'res.lang']

        if self.env.user.id and read_value and not all_data:
            if model_name not in model_list:
                self._cr.execute("""SELECT am.id FROM rag_mcp_access_management as am
                                    WHERE active='t' AND readonly = True AND am.id
                                    IN (SELECT au.access_management_id
                                        FROM rag_mcp_access_management_users_rel_ah as au
                                        WHERE user_id = %s AND am.id
                                        IN (SELECT ac.access_management_id
                                            FROM rag_mcp_access_management_comapnay_rel as ac)) """, (self.env.user.id,))
                a = self._cr.fetchall()
                if bool(a):
                    if mode != 'read' and model_name not in ['mail.channel.partner']:
                        raise UserError(
                            _('%s is a read-only user. So you can not make any changes in the system!') % self.env.user.name)

        value = self._cr.execute(
            """SELECT value from ir_config_parameter where key='uninstall_rag_odoo_mcp_server' """)
        value = self._cr.fetchone()
        if not value:
            value = self._cr.execute("""select state from ir_module_module where name = 'rag_odoo_mcp_server'""")
            value = self._cr.fetchone()
            value = value and value[0] or False
            if model_name and value == 'installed':
                self._cr.execute("SELECT id FROM ir_model WHERE model=%s", (model_name,))
                model_numeric_id = self._cr.fetchone()
                model_numeric_id = model_numeric_id and model_numeric_id[0] or False
                if model_numeric_id and isinstance(model_numeric_id, int) and self.env.user:
                    try:
                        self._cr.execute("""
                                        SELECT dm.id
                                        FROM rag_mcp_access_domain_ah as dm
                                        WHERE dm.model_id=%s AND dm.apply_domain AND dm.access_management_id
                                        IN (SELECT am.id
                                            FROM rag_mcp_access_management as am
                                            WHERE active='t' AND am.id
                                            IN (SELECT amusr.access_management_id
                                                FROM rag_mcp_access_management_users_rel_ah as amusr
                                                WHERE amusr.user_id=%s ))
                                        """, [model_numeric_id, self.env.user.id])
                        access_domain_ah_ids = self.env['rag.mcp.access.domain.ah'].browse(
                            row[0] for row in self._cr.fetchall()).filtered(
                            lambda line: self.env.company in line.access_management_id.company_ids)
                    except:
                        access_domain_ah_ids = False
                    if access_domain_ah_ids:
                        domain_list = []
                        if model_name == 'res.partner':
                            self._cr.execute("""SELECT partner_id FROM res_users""")
                            partner_ids = [row[0] for row in self._cr.fetchall()]
                            domain_list = ['|', ('id', 'in', partner_ids)]
                        eval_context = self._eval_context()
                        length = len(access_domain_ah_ids.sudo()) if access_domain_ah_ids.sudo() else 0
                        for access in access_domain_ah_ids.sudo():
                            dom = safe_eval(access.domain, eval_context) if access.domain else []
                            if dom:
                                dom = expression.normalize_domain(dom)
                                for dom_tuple in dom:
                                    if isinstance(dom_tuple, (tuple, list)) and len(dom_tuple) == 3:
                                        left_value = dom_tuple[0]
                                        operator_value = dom_tuple[1]
                                        right_value = dom_tuple[2]

                                        # Guard: a malformed domain leaf may
                                        # have a non-string left-hand side.
                                        # Pass it through untouched instead
                                        # of crashing on .split('.').
                                        if not isinstance(left_value, str):
                                            domain_list.append(dom_tuple)
                                            continue

                                        left_value_split_list = left_value.split('.')
                                        model_string = model_name
                                        left_user = False
                                        left_company = False
                                        try:
                                            for field in left_value_split_list:
                                                left_user = False
                                                left_company = False
                                                model_obj = self.env[model_string]
                                                fields_def = model_obj.fields_get()
                                                if field not in fields_def:
                                                    break
                                                field_type = fields_def[field]['type']
                                                if field_type in ['many2one', 'many2many', 'one2many']:
                                                    field_relation = fields_def[field]['relation']
                                                    model_string = field_relation
                                                    if model_string == 'res.users':
                                                        left_user = True
                                                    if model_string == 'res.company':
                                                        left_company = True
                                        except Exception:
                                            domain_list.append(dom_tuple)
                                            continue

                                        if left_user:
                                            if operator_value in ['in', 'not in']:
                                                if isinstance(right_value, list) and 0 in right_value:
                                                    zero_index = right_value.index(0)
                                                    right_value[zero_index] = self.env.user.id

                                        if left_company:
                                            if operator_value in ['in', 'not in']:
                                                if isinstance(right_value, list) and 0 in right_value:
                                                    zero_index = right_value.index(0)
                                                    right_value[zero_index] = self.env.company.id

                                        if operator_value == 'date_filter':
                                            domain_list += prepare_domain_v2(dom_tuple)
                                        else:
                                            domain_list.append(dom_tuple)
                                    else:
                                        domain_list.append(dom_tuple)
                                if length > 1:
                                    domain_list.insert(0, '|')
                                    length -= 1
                        if domain_list:
                            return domain_list

        return res
