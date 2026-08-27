# coding: utf-8
from odoo import models, fields, api
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_ve_company = fields.Boolean(
        related='company_id.is_ve_company',
        string='Empresa VE'
    )

    rif = fields.Char(string="RIF", related='partner_id.rif', store=True)

    identification_id = fields.Char('Documento de Identidad', related='partner_id.identification_id', size=20,
                                     store=True)

    nationality = fields.Selection(string="Tipo Documento", related='partner_id.nationality', store=True)

    people_type_company = fields.Selection(string='Tipo de Persona', related='partner_id.people_type_company')


    people_type_individual = fields.Selection(string='Tipo de Persona', related='partner_id.people_type_individual')

    company_type = fields.Selection(string='Company Type',
                                    related='partner_id.company_type')


    def _prepare_invoice(self):
        res = super(SaleOrder, self)._prepare_invoice()
        res.update({'pricelist_id': self.pricelist_id.id})
        return res

    # def write(self, vals):
    #     res = {}
    #     if vals.get('partner_id'):
    #             partner_id = vals.get('partner_id')
    #             partner_obj =self.env['res.partner'].search([('id', '=', partner_id)])
    #             if (partner_obj.company_type == 'person' and not partner_obj.identification_id):
    #                 raise UserError('El Cliente no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(partner_obj.name))
    #             if (partner_obj.company_type == 'company'):
    #                 if (partner_obj.people_type_company == 'pjdo' and not partner_obj.rif):
    #                     raise UserError('El Cliente no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(partner_obj.name))

    #     res = super(SaleOrder, self).write(vals)
    #     return res

    # @api.model
    # def create(self, vals):
    #     res = {}
    #     if vals.get('partner_id'):
    #         partner_id = vals.get('partner_id')
    #         partner_obj =self.env['res.partner'].search([('id', '=', partner_id)])
    #         if (partner_obj.company_type == 'person' and not partner_obj.identification_id):
    #             raise UserError('El Cliente no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(partner_obj.name))

    #         if (partner_obj.company_type == 'company'):
    #             if (partner_obj.people_type_company == 'pjdo' and not partner_obj.rif):
    #                 raise UserError('El Cliente no posee Documento Fiscal, por favor diríjase a la configuación de %s, y realice el registro correctamente para poder continuar' % str(partner_obj.name))

    #     res = super(SaleOrder, self).create(vals)
    #     return res