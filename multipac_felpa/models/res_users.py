# -*- coding: utf-8 -*-

from odoo import models, fields, api

class Users(models.Model):
    _inherit = "res.users"

    # Compatibility fields for other modules
    acrux_chat_active = fields.Boolean(string='Acrux Chat Active', compute='_compute_dummy_compat', store=False, help='Compatibility field')
    chatroom_signing = fields.Char(string='Chatroom Signing', compute='_compute_dummy_compat', store=False, help='Compatibility field')
    chatroom_signing_active = fields.Boolean(string='Chatroom Signing Active', compute='_compute_dummy_compat', store=False, help='Compatibility field')
    is_chatroom_group = fields.Boolean(string='Is Chatroom Group', compute='_compute_dummy_compat', store=False, help='Compatibility field')

    def _compute_dummy_compat(self):
        for rec in self:
            rec.acrux_chat_active = False
            rec.chatroom_signing = False
            rec.chatroom_signing_active = False
            rec.is_chatroom_group = False


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['fel_pa_ignore_verificartion'] = True
        return super(Users, self).create(vals_list)