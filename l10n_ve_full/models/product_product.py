# coding: utf-8
from odoo import fields, models, api
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.onchange('type')
    def _onchange_type(self):
        #res = super(ProductProduct, self)._onchange_type()
        if not self.env.company.is_ve_company:
            return {}
        
        concept_id = False
        if self.type == 'service':
            concept_obj = self.env['account.wh.islr.concept'].sudo()

            concept_id = concept_obj.search([('withholdable', '=', False)], limit=1)
            concept_id = concept_id and concept_id[0] or False
            if not concept_id:
                raise UserError("Invalid action! \nDebe crear el concepto de retención de ingresos")
        #self.concept_id = concept_id or False
        return {'value': {'concept_id': concept_id or False}}
