# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

class AccountJournal(models.Model):
    _inherit = "account.journal"

    # Compatibility fields for other modules
    exclude_from_dual_currency = fields.Boolean(string='Exclude from Dual Currency', default=False, help='Compatibility field')
    inbound_transfer_auth_user_ids = fields.Many2many('res.users', string='Inbound Transfer Auth Users', help='Compatibility field')
    outbound_transfer_auth_user_ids = fields.Many2many('res.users', 'account_journal_outbound_auth_rel', string='Outbound Transfer Auth Users', help='Compatibility field')
    
    fel_pa_pac = fields.Selection(related='company_id.fel_pa_pac', string="Panamá FEL PAC")
    fel_pa_active = fields.Boolean(string="Panamá FEL Active", default=False)
    fel_pa_document_type_ids = fields.One2many('fel_pa.tools.document_type', 'journal_id', string="Panamá FEL Document Types")
    fel_pa_default_document_type_id = fields.Many2one('fel_pa.tools.document_type', string="Panamá FEL Default Document Type", domain="[('journal_id', '=', id)]")
    fel_pa_contingency_ids = fields.One2many('fel_pa.tools.contingency', 'journal_id', string="Panamá FEL Contingencies", context={'active_test': False})
    fel_pa_active_contingency_id = fields.Many2one('fel_pa.tools.contingency', string="Panamá FEL Active Contingency")
    fel_pa_certify = fields.Boolean(string="Panamá FEL Certify", default=True)

    def create_fel_pa_contingency(self):
        for rec in self:
            if not rec.fel_pa_active_contingency_id:
                action = self.env.ref('multipac_felpa.action_create_contingency_wizard').read()[0]
                action['context'] = {
                    'motive': rec.company_id.fel_pa_default_contingency_motive if rec.company_id.fel_pa_default_contingency_motive else _('Auto-generated contingency'),
                }
                return action
            else:
                return rec.action_open_active_conticency()

    def action_open_active_conticency(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Panamá FEL Contingency'),
            'res_model': 'fel_pa.tools.contingency',
            'res_id': self.fel_pa_active_contingency_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_close_contingency(self):
        self.ensure_one()
        if self.fel_pa_active_contingency_id:
            self.fel_pa_document_type_ids.write({'active': False, 'end_date': fields.Datetime.now()})
        return True

    def create_fel_pa_document_types(self):
        for rec in self:
            document_types = {
                '01': "Internal bill",
                '02': "Import bill",
                '03': "Export bill",
                '04': "Credit note referring to a E-bill",
                '05': "Debit note referring to a E-bill",
                '06': "Generic credit note",
                '07': "Generic debit note",
                '08': "Free Zone bill",
                '09': "Reimbursement",
            }
            existing_document_types = rec.fel_pa_document_type_ids.mapped('document_type')
            for doc_type, doc_name in document_types.items():
                if doc_type not in existing_document_types:
                    rec.env['fel_pa.tools.document_type'].create({
                        "name": f"{rec.name} - {doc_name}",
                        "company_id": rec.company_id.id,
                        "journal_id": rec.id,
                        "document_type": doc_type,
                        "code": rec.code,
                        "sequence_actual_number": 1
                    })

    fel_pa_branch_type = fields.Selection([('1', "Retail location"), ('2', "Business to business location")], string="Panamá FEL Branch Type", default='2')

    fel_pa_cafe_format = fields.Selection([('1', "No CAFE issuing"),
                                           ('2', 'Ticket printer. 3: 8 ½” X 11” paper')], string="Panamá FEL CAFE Format", default='1')
    
    fel_pa_cafe_delivery = fields.Selection([('1', " No CAFE issuing"),
                                             ('2', 'CAFE issued on paper'),
                                             ('3', 'CAFE sent as an electronic document')], string="Panamá FEL CAFE Delivery", default='1')
    
    fel_pa_container_sent = fields.Selection([('1', "Normal"),
                                              ('2', 'The receiver exempts the sender from the obligation of sending the container')], string="Panamá FEL Container Sent", default='1')
    
    fel_pa_payment_method = fields.Selection([('01', "Credit"),
                                                ('02', 'Cash'),
                                                ('03', 'Credit Card'),
                                                ('04', 'Debit Card'),
                                                ('05', 'Loyalty Card'),
                                                ('06', 'Voucher'),
                                                ('07', 'Gift Card'),
                                                ('08', 'Transfer/Deposit to Bank Account'),
                                                ('99', 'Other')], string="Panamá FEL Payment Method", default='01')
    
    fel_pa_other_payment_description = fields.Char(string="Panamá FEL Other Payment Description")

    fel_pa_code_branch_issuer = fields.Char(string="Panamá FEL Code Branch Issuer", help="Code of the branch issuer of the document")

    fel_pa_custom_logo = fields.Boolean(string="Panamá FEL Custom Logo", default=False)
    fel_pa_invoice_custom_logo = fields.Binary(string='Panamá FEL Invoice Custom Logo', attachment=True)

    fel_pa_coordinates = fields.Char(string="Panamá FEL Coordinates", help="Coordinates of the establishment")

    