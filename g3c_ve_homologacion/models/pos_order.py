from odoo import models, api, fields, _
from odoo.exceptions import UserError

class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    @api.constrains('qty')
    def _check_pos_qty(self):
        for line in self:
            if not line.company_id.homologacion_activa:
                continue
            # Restricciones de Cantidad (Homologación):
            # 1. Cantidad CERO: Siempre prohibida.
            # 2. Cantidad NEGATIVA: Permitida únicamente si es una DEVOLUCIÓN (vínculo a línea previa).
            
            if line.qty == 0:
                raise UserError(_(
                    "Restricción de Punto de Venta (Homologación): No se permite la facturación de productos "
                    "con cantidad cero.\n\n"
                    "Producto: %s"
                ) % (line.product_id.display_name))
            
            if line.price_unit <= 0:
                raise UserError(_(
                    "Restricción de Punto de Venta (Homologación): No se permite la facturación de productos "
                    "con precio cero o negativo.\n\n"
                    "Producto: %s\n"
                    "Precio: %s"
                ) % (line.product_id.display_name, line.price_unit))
            
            if line.qty < 0 and not line.refunded_orderline_id:
                raise UserError(_(
                    "Restricción de Punto de Venta (Homologación): No se permite la facturación de productos "
                    "con cantidad negativa de forma manual.\n\n"
                    "Producto: %s\n"
                    "Cantidad: %s\n\n"
                    "Para devoluciones, utilice el proceso oficial de 'Reembolso'."
                ) % (line.product_id.display_name, line.qty))
