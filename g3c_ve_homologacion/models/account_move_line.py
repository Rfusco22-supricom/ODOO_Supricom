from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    move_type = fields.Selection(related='move_id.move_type', store=True, readonly=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        res = super(AccountMoveLine, self)._onchange_product_id()
        for line in self:
            if line.product_id:
                # Forzar impuestos según el tipo de factura
                if line.move_id.is_sale_document():
                    line.tax_ids = line.product_id.taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id)
                elif line.move_id.is_purchase_document():
                    line.tax_ids = line.product_id.supplier_taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_id') and 'tax_ids' in vals:
                product = self.env['product.product'].browse(vals['product_id'])
                # Necesitamos saber el tipo de movimiento. Si no viene en vals, es difícil
                # Pero usualmente viene o se asume de cliente si no se especifica.
                # En Odoo 17 move_id suele estar en vals.
                move = self.env['account.move'].browse(vals.get('move_id'))
                if move:
                    if move.is_sale_document():
                        # No sobreescribir impuestos si ya hay una posición fiscal (debe mapearse automáticamente)
                        if not move.fiscal_position_id:
                            vals['tax_ids'] = [(6, 0, product.taxes_id.sudo().filtered(lambda t: t.company_id == move.company_id).ids)]
                    elif move.is_purchase_document():
                        vals['tax_ids'] = [(6, 0, product.supplier_taxes_id.sudo().filtered(lambda t: t.company_id == move.company_id).ids)]
        return super(AccountMoveLine, self).create(vals_list)

    def write(self, vals):
        if 'tax_ids' in vals:
            for line in self:
                if line.product_id:
                    product = line.product_id
                    if line.move_id.is_sale_document():
                        # Si existe posición fiscal en la factura, respetarla (no forzar impuestos del producto)
                        if line.move_id.fiscal_position_id:
                            continue
                        correct_taxes = product.taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id).ids
                    elif line.move_id.is_purchase_document():
                        correct_taxes = product.supplier_taxes_id.sudo().filtered(lambda t: t.company_id == line.company_id).ids
                    else:
                        continue
                        
                    new_taxes = vals['tax_ids']
                    if isinstance(new_taxes, list) and new_taxes and new_taxes[0][0] == 6:
                        if set(new_taxes[0][2]) != set(correct_taxes):
                             vals['tax_ids'] = [(6, 0, correct_taxes)]
        return super(AccountMoveLine, self).write(vals)
    @api.constrains('product_id')
    def _check_product_service_manual(self):
        for line in self:
            # Sin restricción si la homologación no está activa
            if not line.move_id.homologacion_activa:
                continue
            # Solo aplicar a facturas de cliente y notas de crédito de cliente
            if line.move_id.move_type in ['out_invoice', 'out_refund']:

                # Si el producto está seteado y no es de tipo servicio
                if line.product_id and line.product_id.type != 'service':
                    # En Odoo 17, las líneas facturadas desde preventa tienen sale_line_ids
                    # pero en algunos flujos (o si no se guarda correctamente en caché antes del constrains)
                    # usamos invoice_origin a nivel del documento como mecanismo de seguridad.
                    if not line.sale_line_ids and not line.move_id.invoice_origin:
                        # Obtener el label del tipo de producto
                        product_type_label = {
                            'product': 'Almacenable',
                            'consu': 'Consumible',
                            'service': 'Servicio'
                        }.get(line.product_id.type, line.product_id.type)
                        
                        raise UserError(_(
                            "Restricción de Facturación (Homologación): No se permite el registro manual de productos "
                            "almacenables o consumibles en facturas.\n\n"
                            "Producto: %s\n"
                            "Tipo: %s\n\n"
                            "Para productos físicos, debe realizar el proceso desde un Pedido de Venta. "
                            "En facturación manual solo se permiten Servicios."
                        ) % (line.product_id.display_name, product_type_label))
