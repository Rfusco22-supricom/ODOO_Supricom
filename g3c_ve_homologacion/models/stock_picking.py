from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Restricción de Inventario: Bloqueo total de Ventas en Negativo
        for picking in self:
            if not picking.company_id.homologacion_activa:
                continue
            # NUEVA RESTRICCIÓN: Bloquear entregas manuales (sin orden de venta)
            if picking.picking_type_code == 'outgoing' and not picking.sale_id:
                raise UserError(_(
                    "Restricción de Homologación: No se permite validar entregas de mercancía "
                    "que no provengan de una Orden de Venta.\n\n"
                    "Transferencia: %s\n\n"
                    "Todas las salidas de inventario deben estar respaldadas por un pedido de venta."
                ) % (picking.name))
            
            # NUEVA RESTRICCIÓN: Bloquear recepciones manuales (sin orden de compra)
            if picking.picking_type_code == 'incoming' and not picking.purchase_id:
                raise UserError(_(
                    "Restricción de Homologación: No se permite validar recepciones de mercancía "
                    "que no provengan de una Orden de Compra.\n\n"
                    "Transferencia: %s\n\n"
                    "Todas las entradas de inventario deben estar respaldadas por una orden de compra."
                ) % (picking.name))
            
            # Solo aplicamos a salidas o transferencias internas (donde sale mercancía)
            if picking.picking_type_code in ('outgoing', 'internal'):
                for move in picking.move_ids_without_package:
                    if move.product_id.type == 'product': # Solo productos almacenables
                        # Cantidad que se intenta validar (marcada como hecha)
                        qty_to_validate = move.quantity
                        
                        # Cantidad disponible físicamente en la ubicación de origen
                        # Usamos with_context para obtener el stock específico de la ubicación de salida
                        product_ctx = move.product_id.with_context(location=picking.location_id.id)
                        available_qty = product_ctx.qty_available
                        
                        if qty_to_validate > available_qty:
                            raise UserError(_(
                                "Restricción de Inventario (Homologación): No hay suficiente stock físico para el producto '%s' "
                                "en la ubicación '%s'.\n\n"
                                "Disponible: %s %s\n"
                                "Intentando validar: %s %s\n\n"
                                "El sistema tiene prohibido procesar ventas o entregas en negativo."
                            ) % (
                                move.product_id.display_name, 
                                picking.location_id.display_name,
                                available_qty, move.product_uom.name,
                                qty_to_validate, move.product_uom.name
                            ))
                            
        return super(StockPicking, self).button_validate()
