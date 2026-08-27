from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    hide_sale_confirm = fields.Boolean(
        related='company_id.hide_sale_confirm',
        string='Ocultar botón de Confirmar'
    )

    homologacion_activa = fields.Boolean(
        related='company_id.homologacion_activa',
        string='Homologación Activa'
    )

    def action_confirm(self):
        # Restricción de Inventario: Bloqueo de Ventas en Negativo al confirmar pedido
        for order in self:
            if not order.company_id.homologacion_activa:
                continue
            for line in order.order_line:
                if line.product_id and line.product_id.type == 'product':
                    # Excepción para productos fabricados (MTO / Manufactura)
                    # Si el producto tiene una ruta de 'Manufacture' o 'Fabricar', permitimos la venta sin stock
                    # ya que se espera que se produzca bajo pedido.
                    is_manufactured = False
                    if line.product_id.route_ids:
                        for route in line.product_id.route_ids:
                            # Buscamos por nombre (más seguro si no tenemos ID exacto o mrp instalado)
                            # Odoo estándar usa 'Manufacture' en inglés, localizaciones pueden usar 'Fabricar'
                            if 'manufacture' in route.name.lower() or 'fabricar' in route.name.lower() or 'producción' in route.name.lower():
                                is_manufactured = True
                                break
                    
                    if is_manufactured:
                        continue

                    # Verificar stock físico en el almacén del pedido
                    # Tomamos el stock de la ubicación de salida del almacén
                    location = order.warehouse_id.lot_stock_id
                    product_ctx = line.product_id.with_context(location=location.id)
                    
                    # Stock disponible en la unidad de medida de referencia del producto
                    # qty_available = A mano
                    # virtual_available = Pronosticado (A mano - Reservado + Por recibir)
                    qty_available = product_ctx.qty_available
                    virtual_available = product_ctx.virtual_available
                    
                    # Convertir la cantidad solicitada a la unidad de referencia del producto para comparación correcta
                    qty_needed = line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id)

                    # 1. Validación de Stock Físico (On Hand)
                    if qty_available <= 0.0 or qty_needed > qty_available:
                         raise UserError(_(
                            "Restricción de Inventario (Homologación): No hay suficiente stock FÍSICO para el producto '%s' "
                            "en la ubicación '%s'.\n\n"
                            "Stock Físico: %s %s\n"
                            "Solicitado: %s %s (Equivalente a %s %s)\n\n"
                            "Debe tener existencias físicas para confirmar."
                        ) % (
                            line.product_id.display_name,
                            location.display_name,
                            qty_available, line.product_id.uom_id.name,
                            line.product_uom_qty, line.product_uom.name,
                            qty_needed, line.product_id.uom_id.name
                        ))

                    # 2. Validación de Stock Pronosticado (Forecasted)
                    # Si el pronosticado es menor a lo solicitado, significa que aunque haya físico,
                    # ya está comprometido en otros pedidos.
                    if virtual_available <= 0.0 or qty_needed > virtual_available:
                        raise UserError(_(
                            "Restricción de Inventario (Homologación): No hay suficiente stock PRONOSTICADO para el producto '%s' "
                            "en la ubicación '%s'.\n\n"
                            "El stock físico existe (%s %s), pero ya está comprometido o reservado en otros pedidos.\n"
                            "Stock Pronosticado (Disponible Real): %s %s\n"
                            "Solicitado: %s %s\n\n"
                            "No se puede vender mercancía que ya está reservada para otros clientes."
                        ) % (
                            line.product_id.display_name,
                            location.display_name,
                            qty_available, line.product_id.uom_id.name,
                            virtual_available, line.product_id.uom_id.name,
                            qty_needed, line.product_id.uom_id.name
                        ))
        return super(SaleOrder, self).action_confirm()
