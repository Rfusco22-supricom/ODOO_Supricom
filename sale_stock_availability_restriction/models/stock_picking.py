from odoo import models, fields, api
from odoo.osv import expression

import logging
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    despacho_oculto = fields.Boolean(
        string="Despacho Oculto",
        default=False,
        copy=False,
        help="Cuando está activo, el picking no es visible en las vistas de inventario. "
             "Se activa cuando la orden de venta no tiene autorizado el despacho."
    )

    def _register_hook(self):
        """Desactivar y neutralizar la ir.rule antigua cada vez que se carga el módulo.
        Esto es necesario porque la regla fue creada con noupdate=1 y el
        cambio en el XML podría no surtir efecto en la BD."""
        super()._register_hook()
        self.env.cr.execute("""
            UPDATE ir_rule 
            SET active = false, domain_force = '[(1, ''='', 1)]'
            WHERE id IN (
                SELECT res_id FROM ir_model_data
                WHERE module = 'sale_stock_availability_restriction'
                  AND name = 'rule_stock_picking_despacho_oculto'
            )
        """)
        if self.env.cr.rowcount:
            _logger.info(
                "sale_stock_availability_restriction: ir.rule "
                "'rule_stock_picking_despacho_oculto' neutralizada exitosamente."
            )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        """Filtrar pickings con despacho_oculto=True de los resultados de búsqueda
        normales (vistas de inventario).

        Se omite el filtro cuando:
        - self.env.su = True  → modo superusuario (sudo)
        - access_rights_uid != None → verificación interna de reglas de acceso
        - El dominio incluye búsqueda por 'id' (lecturas relacionales, pronósticos)
        - El dominio ya contiene filtro de despacho_oculto
        """
        is_internal = (
            self.env.su
            or access_rights_uid is not None
        )
        if not is_internal:
            has_despacho_filter = False
            has_id_filter = False
            
            for leaf in (domain or []):
                if isinstance(leaf, (list, tuple)) and len(leaf) >= 1:
                    if leaf[0] == 'despacho_oculto':
                        has_despacho_filter = True
                    elif leaf[0] == 'id':
                        has_id_filter = True
                        
            if not has_despacho_filter and not has_id_filter:
                domain = expression.AND([domain or [], [('despacho_oculto', '=', False)]])
                
        return super()._search(
            domain, offset=offset, limit=limit,
            order=order, access_rights_uid=access_rights_uid
        )

    def button_validate(self):
        # Auto-enlace de movimientos de stock sin sale_line_id a las líneas del pedido original
        for picking in self:
            if picking.sale_id:
                for move in picking.move_ids:
                    if not move.sale_line_id:
                        sale_lines = picking.sale_id.order_line.filtered(
                            lambda l: l.product_id == move.product_id
                        )
                        if sale_lines:
                            # Selecciona la línea que aún no se haya entregado por completo, o la primera disponible
                            best_line = sale_lines[0]
                            for line in sale_lines:
                                if line.qty_delivered < line.product_uom_qty:
                                    best_line = line
                                    break
                            move.write({'sale_line_id': best_line.id})
        return super(StockPicking, self).button_validate()
