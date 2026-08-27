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
from odoo.exceptions import ValidationError

class FelPADocumentType(models.Model):
    _name = "fel_pa.tools.document_type"
    _description = "Panamá FEL Document Type"

    name = fields.Char(string="Name")

    company_id = fields.Many2one('res.company', string="Company", ondelete='cascade')

    journal_id = fields.Many2one('account.journal', string="Journal", required=True, ondelete='cascade')

    company_id = fields.Many2one('res.company', related='journal_id.company_id', string='Company', store=True)

    code = fields.Char(string="Code", help="Code for the document number")
    
    document_type = fields.Selection([('01', "Internal bill"),
                                      ('02', "Import bill"),
                                      ('03', "Export bill"),
                                      ('04', "Credit note referring to a E-bill"),
                                      ('05', "Debit note referring to a E-bill"),
                                      ('06', "Generic credit note"),
                                      ('07', "Generic debit note"),
                                      ('08', "Free Zone bill"),
                                      ('09', "Reimbursement"),
                                      ], string="Document Type", default='01')

    sequence_actual_number = fields.Integer(string='Sequence Actual Number', default=1)

    active = fields.Boolean(string="Active", default=True)

    def _get_next_number(self):
        for rec in self:
            rec.sequence_actual_number += 1
            
            if rec.journal_id.type == 'sale':
                other_doc_type = False
                if rec.document_type in ['04', '06']:
                    other_doc_type = '06' if rec.document_type == '04' else '04'
                elif rec.document_type in ['01', '03']:
                    other_doc_type = '03' if rec.document_type == '01' else '01'
                
                if other_doc_type:
                    related_docs = self.search([
                        ('journal_id', '=', rec.journal_id.id),
                        ('document_type', '=', other_doc_type)
                    ])
                    if related_docs:
                        related_docs.write({'sequence_actual_number': rec.sequence_actual_number})

            next_number = f"{rec.sequence_actual_number:010}"
            return next_number

    _sql_constraints = [
        ('unique_active_journal_document_type', 
         'UNIQUE(journal_id, document_type, active)', 
         'Only one active document type per journal and document type is allowed.')
    ]

    @api.constrains('journal_id', 'document_type', 'active')
    def _check_unique_active(self):
        for record in self:
            if record.active:
                domain = [
                    ('id', '!=', record.id),
                    ('journal_id', '=', record.journal_id.id),
                    ('document_type', '=', record.document_type),
                    ('active', '=', True)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_('Only one active document type per journal and document type is allowed.'))