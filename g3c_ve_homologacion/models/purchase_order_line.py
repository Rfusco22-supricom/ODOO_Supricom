from odoo import models, api, _
from odoo.exceptions import UserError

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.onchange('product_id')
    def onchange_product_id(self):
        res = super(PurchaseOrderLine, self).onchange_product_id()
        for line in self:
            if line.product_id:
                # Forzar los impuestos de proveedor del producto filtrados por compañía
                line.taxes_id = line.product_id.supplier_taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                # Forzar impuestos del producto (proveedor) filtrados por compañía
                if 'taxes_id' in vals:
                    order = self.env['purchase.order'].browse(vals.get('order_id'))
                    company = order.company_id if order else self.env.company
                    vals['taxes_id'] = [(6, 0, product.supplier_taxes_id.sudo().filtered(lambda t: t.company_id == company).ids)]
        return super(PurchaseOrderLine, self).create(vals_list)

    def write(self, vals):
        if 'taxes_id' in vals:
            for line in self:
                if line.product_id:
                    new_taxes = vals['taxes_id']
                    if isinstance(new_taxes, list) and new_taxes and new_taxes[0][0] == 6:
                        correct_taxes = line.product_id.supplier_taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id).ids
                        if set(new_taxes[0][2]) != set(correct_taxes):
                             vals['taxes_id'] = [(6, 0, correct_taxes)]
        return super(PurchaseOrderLine, self).write(vals)
