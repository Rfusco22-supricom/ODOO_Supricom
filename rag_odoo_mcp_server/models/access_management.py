# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.http import request


class access_management(models.Model):
    _name = 'rag.mcp.access.management'
    _description = "Access Management"

    name = fields.Char('Name')
    user_ids = fields.Many2many('res.users', 'rag_mcp_access_management_users_rel_ah', 'access_management_id', 'user_id',
                                'Users')

    readonly = fields.Boolean('Read-Only')
    active = fields.Boolean('Active', default=True)

    hide_menu_ids = fields.Many2many('rag.mcp.menu.item', 'rag_mcp_access_management_menu_rel_ah', 'access_management_id', 'menu_id',
                                     'Hide Menu')
    hide_field_ids = fields.One2many('rag.mcp.hide.field', 'access_management_id', 'Hide Field', copy=True)

    remove_action_ids = fields.One2many('rag.mcp.remove.action', 'access_management_id', 'Remove Action', copy=True)

    access_domain_ah_ids = fields.One2many('rag.mcp.access.domain.ah', 'access_management_id', 'Access Domain', copy=True)
    hide_view_nodes_ids = fields.One2many('rag.mcp.hide.view.nodes', 'access_management_id', 'Button/Tab Access', copy=True)

    total_rules = fields.Integer('Access Rules', compute="_count_total_rules")

    # Chatter
    hide_chatter_ids = fields.One2many('rag.mcp.hide.chatter', 'access_management_id', 'Hide Chatter', copy=True)

    hide_chatter = fields.Boolean('Hide Chatter')
    hide_send_mail = fields.Boolean('Hide Send Message')
    hide_log_notes = fields.Boolean('Hide Log Notes')
    hide_schedule_activity = fields.Boolean('Hide Schedule Activity')

    hide_export = fields.Boolean()
    hide_import = fields.Boolean()
    hide_spreadsheet = fields.Boolean()
    hide_add_property = fields.Boolean()
    disable_login = fields.Boolean('Disable Login')

    disable_debug_mode = fields.Boolean('Disable Developer Mode')

    company_ids = fields.Many2many('res.company', 'rag_mcp_access_management_comapnay_rel', 'access_management_id',
                                   'company_id', 'Companies', required=True, default=lambda self: self.env.company)

    hide_filters_groups_ids = fields.One2many('rag.mcp.hide.filters.groups', 'access_management_id', 'Hide Filters/Group By',
                                              copy=True)

    def _count_total_rules(self):
        for rec in self:
            rule = 0
            rule = rule + len(rec.hide_menu_ids) + len(rec.hide_field_ids) + len(rec.remove_action_ids) + len(
                rec.access_domain_ah_ids) + len(rec.hide_view_nodes_ids)
            rec.total_rules = rule

    def toggle_active_value(self):
        for record in self:
            record.write({'active': not record.active})
        return True

    @api.model_create_multi
    def create(self, vals_list):
        res = super(access_management, self).create(vals_list)
        try:
            request.registry.clear_cache()
        except Exception:
            pass
        for record in res:
            if record.readonly:
                for user in record.user_ids:
                    if user.has_group('base.group_system') or user.has_group('base.group_erp_manager'):
                        raise UserError(_('Admin user can not be set as a read-only..!'))
        return res

    def unlink(self):
        res = super(access_management, self).unlink()
        try:
            request.env.registry.clear_cache()
        except Exception:
            pass
        return res

    def write(self, vals):
        res = super(access_management, self).write(vals)
        if self.readonly:
            for user in self.user_ids:
                if user.has_group('base.group_system') or user.has_group('base.group_erp_manager'):
                    raise UserError(_('Admin user can not be set as a read-only..!'))
        try:
            request.env.registry.clear_cache()
        except Exception:
            pass
        return res

    def get_remove_options(self, model):
        restrict_export = self.env['rag.mcp.access.management'].search([('company_ids', 'in', self.env.company.id),
                                                                ('active', '=', True),
                                                                ('user_ids', 'in', self.env.user.id),
                                                                ('hide_export', '=', True)], limit=1).id
        remove_action = self.env['rag.mcp.remove.action'].sudo().search(
            [('access_management_id.company_ids', 'in', self.env.company.id),
             ('access_management_id', 'in', self.env.user.rag_mcp_access_management_ids.ids), ('model_id.model', '=', model)])
        options = []
        added_export = False
        if restrict_export:
            options.append(_('Export'))
            added_export = True
        for action in remove_action:
            if not added_export and action.restrict_export:
                options.append(_('Export'))
            if action.restrict_archive_unarchive:
                options.append(_('Archive'))
                options.append(_('Unarchive'))
            if action.restrict_duplicate:
                options.append(_('Duplicate'))
        return options

    @api.model
    def get_chatter_hide_details(self, user_id, company_id, model=False):
        hide_send_mail = True
        hide_log_notes = True
        hide_schedule_activity = True

        access_ids = self.search([('user_ids', 'in', user_id), ('company_ids', 'in', company_id)])
        for access in access_ids:
            if access.hide_chatter:
                hide_send_mail = False
                hide_log_notes = False
                hide_schedule_activity = False
                break
            if access.hide_send_mail:
                hide_send_mail = False
            if access.hide_log_notes:
                hide_log_notes = False
            if access.hide_schedule_activity:
                hide_schedule_activity = False

        if model and hide_send_mail or hide_log_notes or hide_schedule_activity:
            hide_ids = self.env['rag.mcp.hide.chatter'].search([('access_management_id.company_ids', 'in', company_id),
                                                        ('access_management_id.active', '=', True),
                                                        ('access_management_id.user_ids', 'in', user_id),
                                                        ('model_id.model', '=', model)])
            if hide_ids:
                if hide_send_mail and hide_ids.filtered(lambda x: x.hide_send_mail):
                    hide_send_mail = False
                if hide_log_notes and hide_ids.filtered(lambda x: x.hide_log_notes):
                    hide_log_notes = False
                if hide_schedule_activity and hide_ids.filtered(lambda x: x.hide_schedule_activity):
                    hide_schedule_activity = False

        return {
            'hide_send_mail': hide_send_mail,
            'hide_log_notes': hide_log_notes,
            'hide_schedule_activity': hide_schedule_activity
        }

    def is_spread_sheet_available(self, action_model, action_id):
        model = self.env[action_model].sudo().browse(action_id).res_model
        if self.search([('user_ids', 'in', self.env.user.id), ('company_ids', 'in', self.env.company.id),
                        ('active', '=', True), ('hide_spreadsheet', '=', True)]):
            return True
        if model:
            if self.env['rag.mcp.remove.action'].search([('access_management_id.active', '=', True),
                                                 ('access_management_id.user_ids', 'in', self.env.user.id),
                                                 ('access_management_id.company_ids', 'in', self.env.company.id),
                                                 ('model_id.model', '=', model),
                                                 ('restrict_spreadsheet', '=', True)]):
                return True
        return False

    def is_add_property_available(self, model):
        if self.search([('user_ids', 'in', self.env.user.id), ('company_ids', 'in', self.env.company.id),
                        ('active', '=', True), ('hide_add_property', '=', True)]):
            return True
        return False

    def get_hidden_field(self, model=False):
        """Field names hidden for the current user on ``model``.

        Called from the web client (field/domain selector) to filter out
        fields the user is not allowed to see.
        """
        if not model:
            return []
        hide_fields = self.env['rag.mcp.hide.field'].sudo().search([
            ('access_management_id.active', '=', True),
            ('access_management_id.user_ids', 'in', self.env.user.id),
            ('access_management_id.company_ids', 'in', self.env.company.id),
            ('model_id.model', '=', model),
            ('invisible', '=', True),
        ])
        return list({field.name for field in hide_fields.field_id})

    def is_export_hide(self, model=False):
        if self.search([('user_ids', 'in', self.env.user.id), ('company_ids', 'in', self.env.company.id),
                        ('active', '=', True), ('hide_export', '=', True)]):
            return True
        if model:
            if self.env['rag.mcp.remove.action'].search([('access_management_id.active', '=', True),
                                                 ('access_management_id.user_ids', 'in', self.env.user.id),
                                                 ('access_management_id.company_ids', 'in', self.env.company.id),
                                                 ('model_id.model', '=', model),
                                                 ('restrict_export', '=', True)]):
                return True
        return False
