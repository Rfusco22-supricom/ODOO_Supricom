# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, AccessError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval

# Optional dependency
try:
    from odoo.addons.advanced_web_domain_widget.models.domain_prepare import prepare_domain_v2
except ImportError:
    def prepare_domain_v2(dom_tuple):
        return [dom_tuple]


def _mcp_access_tables_ready(cr):
    """Return True only once this module's access tables exist.

    These overrides inherit ``base`` so they run for every model, querying the
    access_management / access_domain_ah tables. During module install/upgrade
    they can fire before those tables are created, which would abort the load
    transaction. ``to_regclass`` returns NULL (no error) when the table is
    absent, so this is safe to call inside a live transaction.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_access_management'), to_regclass('rag_mcp_access_domain_ah')")
        row = cr.fetchone()
        return bool(row and row[0] and row[1])
    except Exception:
        return False


class BaseModel(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def get_views(self, views, options=None):
        res = super().get_views(views, options)
        if not _mcp_access_tables_ready(self._cr):
            return res
        form_toolbar = res['views'].get('form', {}).get('toolbar') or False
        tree_toolbar = res['views'].get('list', {}).get('toolbar') or False
        remove_action = self.env['rag.mcp.remove.action'].search(
            [('access_management_id.company_ids', 'in', self.env.company.id),
             ('access_management_id', 'in', self.env.user.rag_mcp_access_management_ids.ids),
             ('model_id.model', '=', self._name)])
        if form_toolbar or tree_toolbar:
            remove_server_action = remove_action.mapped('server_action_ids.action_id').ids
            remove_print_action = remove_action.mapped('report_action_ids.action_id').ids
        if form_toolbar:
            if res['views']['form']['toolbar'].get('action', False):
                action = [rec for rec in res['views']['form']['toolbar']['action'] if
                          rec.get('id', False) not in remove_server_action]
                res['views']['form']['toolbar']['action'] = action
            if res['views']['form']['toolbar'].get('print', False):
                prints = [rec for rec in res['views']['form']['toolbar']['print'] if
                          rec.get('id', False) not in remove_print_action]
                res['views']['form']['toolbar']['print'] = prints
        if tree_toolbar:
            if res['views']['list']['toolbar'].get('action', False):
                action = [rec for rec in res['views']['list']['toolbar']['action'] if
                          rec.get('id', False) not in remove_server_action]
                res['views']['list']['toolbar']['action'] = action
            if res['views']['list']['toolbar'].get('print', False):
                prints = [rec for rec in res['views']['list']['toolbar']['print'] if
                          rec.get('id', False) not in remove_print_action]
                res['views']['list']['toolbar']['print'] = prints
        return res

    @api.model
    def load_views(self, views, options=None):
        if not _mcp_access_tables_ready(self._cr):
            return super(BaseModel, self).load_views(views, options=options)
        actions_and_prints = []
        for access in self.env['rag.mcp.remove.action'].search([('access_management_id.company_ids', 'in', self.env.company.id),
                                                        ('access_management_id', 'in',
                                                         self.env.user.rag_mcp_access_management_ids.ids),
                                                        ('model_id.model', '=', self._name)]):
            actions_and_prints = actions_and_prints + access.mapped('report_action_ids.action_id').ids
            actions_and_prints = actions_and_prints + access.mapped('server_action_ids.action_id').ids
            for view_data in access.view_data_ids:
                for view_data_list in views:
                    if view_data.techname == view_data_list[1]:
                        views.pop(views.index(view_data_list))

        res = super(BaseModel, self).load_views(views, options=options)

        if 'fields_views' in res.keys():
            for view in ['list', 'form']:
                if view in res['fields_views'].keys():
                    if 'toolbar' in res['fields_views'][view].keys():
                        if 'print' in res['fields_views'][view]['toolbar'].keys():
                            prints = res['fields_views'][view]['toolbar']['print'][:]
                            for pri in prints:
                                if pri['id'] in actions_and_prints:
                                    res['fields_views'][view]['toolbar']['print'].remove(pri)
                        if 'print' in res['fields_views'][view]['toolbar'].keys():
                            action = res['fields_views'][view]['toolbar']['action'][:]
                            for act in action:
                                if act['id'] in actions_and_prints:
                                    res['fields_views'][view]['toolbar']['action'].remove(act)
        return res

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if not _mcp_access_tables_ready(self._cr):
            return arch, view
        access_management_obj = self.env['rag.mcp.access.management']
        readonly_access_id = access_management_obj.search(
            [('company_ids', 'in', self.env.company.id), ('active', '=', True), ('user_ids', 'in', self.env.user.id),
             ('readonly', '=', True)])

        access_recs = self.env['rag.mcp.access.domain.ah'].search(
            [('access_management_id.company_ids', 'in', self.env.company.id),
             ('access_management_id.user_ids', 'in', self.env.user.id), ('access_management_id.active', '=', True),
             ('model_id.model', '=', self._name)])

        access_model_recs = self.env['rag.mcp.remove.action'].search(
            [('access_management_id.company_ids', 'in', self.env.company.id),
             ('access_management_id.user_ids', 'in', self.env.user.id),
             ('access_management_id.active', '=', True),
             ('model_id.model', '=', self._name)])

        if view_type == 'form':
            access_management_id = access_management_obj.search([('company_ids', 'in', self.env.company.id),
                                                                 ('active', '=', True),
                                                                 ('user_ids', 'in', self.env.user.id),
                                                                 ('hide_chatter', '=', True)],
                                                                limit=1).id
            if access_management_id:
                for div in arch.xpath("//div[@class='oe_chatter']"):
                    div.getparent().remove(div)
            else:
                if self.env['rag.mcp.hide.chatter'].search([('access_management_id.company_ids', 'in', self.env.company.id),
                                                    ('access_management_id.active', '=', True),
                                                    ('access_management_id.user_ids', 'in', self.env.user.id),
                                                    ('model_id.model', '=', self._name),
                                                    ('hide_chatter', '=', True)],
                                                   limit=1):
                    for div in arch.xpath("//div[@class='oe_chatter']"):
                        div.getparent().remove(div)

        if view_type in ['kanban', 'tree']:
            restrict_import = access_management_obj.search([('company_ids', 'in', self.env.company.id),
                                                            ('active', '=', True),
                                                            ('user_ids', 'in', self.env.user.id),
                                                            ('hide_import', '=', True)], limit=1).id
            if access_model_recs.filtered(lambda x: x.restrict_import) or restrict_import:
                arch.attrib.update({'import': 'false'})

            restrict_export = access_management_obj.search([('company_ids', 'in', self.env.company.id),
                                                            ('active', '=', True),
                                                            ('user_ids', 'in', self.env.user.id),
                                                            ('hide_export', '=', True)], limit=1).id
            if access_model_recs.filtered(lambda x: x.restrict_export) or restrict_export:
                arch.attrib.update({'export_xlsx': 'false'})

        if readonly_access_id:
            if view_type in ['form', 'tree', 'kanban']:
                arch.attrib.update({'create': 'false', 'delete': 'false', 'edit': 'false'})
        else:
            if access_model_recs:
                delete = 'true'
                edit = 'true'
                create = 'true'
                for access_model in access_model_recs:
                    if access_model.restrict_create:
                        create = 'false'
                    if access_model.restrict_edit:
                        edit = 'false'
                    if access_model.restrict_delete:
                        delete = 'false'
                if view_type in ['form', 'tree', 'kanban']:
                    arch.attrib.update({'create': create, 'delete': delete, 'edit': edit})

            if access_recs:
                delete = 'false'
                edit = 'false'
                create = 'false'
                for access_rec in access_recs:
                    if access_rec.create_right:
                        create = 'true'
                    if access_rec.write_right:
                        edit = 'true'
                    if access_rec.delete_right:
                        delete = 'true'
                if view_type in ['form', 'tree', 'kanban']:
                    arch.attrib.update({'create': create, 'delete': delete, 'edit': edit})

        return arch, view

    def _rag_mcp_get_access_domain_record(self, model=False):
        records = None
        try:
            if model:
                self._cr.execute("SELECT id FROM ir_model WHERE model=%s", (model,))
                model_numeric_id = self._cr.fetchone()
                if model_numeric_id:
                    model_numeric_id = model_numeric_id[0]
                if model_numeric_id and isinstance(model_numeric_id, int) and self.env.user:
                    self._cr.execute("""
                                    SELECT dm.id
                                    FROM rag_mcp_access_domain_ah as dm
                                    WHERE dm.model_id=%s AND dm.access_management_id
                                    IN (SELECT am.id
                                        FROM rag_mcp_access_management as am
                                        WHERE am.active='t' AND am.id
                                        IN (SELECT amusr.access_management_id
                                            FROM rag_mcp_access_management_users_rel_ah as amusr
                                            WHERE amusr.user_id=%s))
                                    """, [model_numeric_id, self.env.user.id])
                    records = self.env['rag.mcp.access.domain.ah'].browse(row[0] for row in self._cr.fetchall())
        except:
            pass
        return records

    def _rag_mcp_check_access_right(self, mode=False, records=False):
        access_flag = False
        access_rule = None
        length = len(records.sudo()) if records.sudo() else 0
        partner_ids = self.env['res.users'].sudo().search([]).mapped("partner_id.id")
        partner_domain = ['|', ('id', 'in', partner_ids)]
        for record in records.sudo():
            if mode == 'create' and record.create_right:
                access_flag = True
                break
            elif mode in ['write', 'unlink']:
                access = False
                if mode == 'unlink':
                    access = record.delete_right
                elif mode == 'write':
                    access = record.write_right

                domain_list = []
                if self.sudo()._name == "res.partner":
                    domain_list += partner_domain
                dom = safe_eval(record.domain) if record.domain else []
                dom = expression.normalize_domain(dom)
                model_name = self._name
                if isinstance(dom, list):
                    for dom_tuple in dom:
                        # Odoo domains can be tuples OR lists of 3 elements
                        # (e.g. '[["id","=",5]]' decodes to a list of lists).
                        # Accept both shapes.
                        if isinstance(dom_tuple, (tuple, list)) and len(dom_tuple) == 3:
                            left_value = dom_tuple[0]
                            operator_value = dom_tuple[1]
                            right_value = dom_tuple[2]

                            # left_value may not be a string when a malformed
                            # or programmatic domain slips in (e.g. integer
                            # literals, False, expression combinators).
                            # In that case there is no field path to walk —
                            # just pass the leaf through untouched.
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
                                        # Unknown field — skip the walk and
                                        # keep the original leaf as-is.
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
                                # Any introspection error: fall back to
                                # appending the raw leaf and keep going.
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
                            # combinators like '&', '|', '!' or already
                            # pre-normalized scalars pass through unchanged
                            domain_list.append(dom_tuple)
                search_domain = domain_list
                if 'active' in self._fields:
                    search_domain = ['|', ('active', '=', False), ('active', '=', True)] + search_domain
                record_ids = self.search(search_domain)

                if self in record_ids and access:
                    access_flag = access
                    break
            access_rule = record.access_management_id.name
        return {'access_flag': access_flag, 'access_rule': access_rule}

    def _rag_mcp_display_access_error(self, mode=None, rule=None):
        if mode and rule:
            msg_heads = {
                'unlink': _(
                    "Due to access management rule,\nYou are not allowed to delete record '%(record)s' from (%(document_model)s) model.",
                    record=self.display_name, document_model=self._name),
                'write': _(
                    "Due to access management rule,\nYou are not allowed to edit record '%(record)s' from (%(document_model)s) model.",
                    record=self.display_name, document_model=self._name),
                'create': _(
                    "Due to access management rule,\nYou are not allowed to create records from (%(document_model)s) model.",
                    document_model=self.display_name),
            }
            operation_error = msg_heads[mode]
            resolution_info = _("Check Applied Rule on Access Management:\n %(access_name)s", access_name=rule)
            msg = """{operation_error}

{resolution_info}""".format(operation_error=operation_error, resolution_info=resolution_info)
            raise AccessError(msg)

    def unlink(self):
        value = self.env['ir.config_parameter'].sudo().search([('key', '=', 'uninstall_rag_odoo_mcp_server')],
                                                              limit=1).value
        if not value and _mcp_access_tables_ready(self._cr):
            for rec in self:
                if rec._name:
                    access_domain_ah_ids = rec._rag_mcp_get_access_domain_record(model=rec._name)
                    if access_domain_ah_ids:
                        access_domain_ah_ids = access_domain_ah_ids.filtered(
                            lambda line: self.env.company in line.access_management_id.company_ids)
                    if access_domain_ah_ids:
                        flag = rec._rag_mcp_check_access_right(mode='unlink', records=access_domain_ah_ids)
                        unlink_flag = flag['access_flag']
                        access_rule = flag['access_rule']
                        if not unlink_flag:
                            rec._rag_mcp_display_access_error(mode='unlink', rule=access_rule)
        return super().unlink()

    def write(self, vals):
        value = self.env['ir.config_parameter'].sudo().search([('key', '=', 'uninstall_rag_odoo_mcp_server')],
                                                              limit=1).value
        if not value and _mcp_access_tables_ready(self._cr):
            for rec in self:
                if rec._name:
                    access_domain_ah_ids = rec._rag_mcp_get_access_domain_record(model=rec._name)
                    if access_domain_ah_ids:
                        access_domain_ah_ids = access_domain_ah_ids.filtered(
                            lambda line: self.env.company in line.access_management_id.company_ids)
                    if access_domain_ah_ids:
                        flag = rec._rag_mcp_check_access_right(mode='write', records=access_domain_ah_ids)
                        write_flag = flag['access_flag']
                        access_rule = flag['access_rule']
                        if not write_flag:
                            rec._rag_mcp_display_access_error(mode='write', rule=access_rule)
        return super().write(vals)
