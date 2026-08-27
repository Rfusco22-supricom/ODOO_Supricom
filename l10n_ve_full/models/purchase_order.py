# coding: utf-8
import ast
import datetime, time

from odoo.tools.translate import _
from odoo import models, fields, api, exceptions
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_ve_company = fields.Boolean(
        related='company_id.is_ve_company',
        string='Empresa VE'
    )

    rif = fields.Char(string="RIF", related='partner_id.rif', store=True)

    identification_id = fields.Char('Documento de Identidad', related='partner_id.identification_id', size=20,
                                    store=True)

    nationality = fields.Selection(string="Tipo Documento", related='partner_id.nationality', store=True
                                   )

    people_type_company = fields.Selection(string='Tipo de Persona', related='partner_id.people_type_company')

    people_type_individual = fields.Selection(string='Tipo de Persona', related='partner_id.people_type_individual')

    company_type = fields.Selection(string='Company Type',
                                    related='partner_id.company_type')

    def write(self, vals):
        res = {}
        if vals.get('partner_id'):
            partner_id = vals.get('partner_id')
            partner_obj = self.env['res.partner'].search([('id', '=', partner_id)])
            if (partner_obj.company_type == 'person' and not partner_obj.identification_id):
                raise UserError(
                    'El Proveedor no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(
                        partner_obj.name))
            if (partner_obj.company_type == 'company'):
                if (partner_obj.people_type_company == 'pjdo' and not partner_obj.rif):
                    raise UserError(
                        'El Proveedor no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(
                            partner_obj.name))

        res = super(PurchaseOrder, self).write(vals)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            res = {}
            if vals.get('partner_id'):
                partner_id = vals.get('partner_id')
                partner_obj = self.env['res.partner'].search([('id', '=', partner_id)])
                if (partner_obj.company_type == 'person' and not partner_obj.identification_id):
                    raise UserError(
                        'El Proveedor no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(
                            partner_obj.name))
                if (partner_obj.company_type == 'company'):
                    if (partner_obj.people_type_company == 'pjdo' and not partner_obj.rif):
                        raise UserError(
                            'El Proveedor no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(
                                partner_obj.name))

        res = super(PurchaseOrder, self).create(vals)
        return res
