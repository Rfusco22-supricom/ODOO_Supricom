from odoo import models, api, _
from odoo.exceptions import UserError

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_id_warning(self):
        res = super(SaleOrderLine, self)._onchange_product_id_warning()
        for line in self:
            if line.product_id:
                line.tax_id = line.product_id.taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                if 'tax_id' in vals:
                    # Intentar obtener la compañía desde el pedido si no está en vals
                    order = self.env['sale.order'].browse(vals.get('order_id'))
                    company = order.company_id if order else self.env.company
                    # Si el pedido tiene posición fiscal, respetarla y no forzar taxes del producto
                    if order and order.fiscal_position_id:
                        pass
                    else:
                        vals['tax_id'] = [(6, 0, product.taxes_id.sudo().filtered(lambda t: t.company_id == company).ids)]
        return super(SaleOrderLine, self).create(vals_list)

    def write(self, vals):
        if 'tax_id' in vals:
            for line in self:
                if line.product_id:
                    new_taxes = vals['tax_id']
                    if isinstance(new_taxes, list) and new_taxes and new_taxes[0][0] == 6:
                        # Respetar la posición fiscal si existe en el pedido
                        if line.order_id and line.order_id.fiscal_position_id:
                            continue
                        correct_taxes = line.product_id.taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id).ids
                        if set(new_taxes[0][2]) != set(correct_taxes):
                            vals['tax_id'] = [(6, 0, correct_taxes)]
        return super(SaleOrderLine, self).write(vals)
