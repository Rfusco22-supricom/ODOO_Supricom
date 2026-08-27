# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.depends('has_tracking', 'picking_type_id.use_create_lots', 'picking_type_id.use_existing_lots', 'product_id')
    def _compute_display_assign_serial(self):
        super()._compute_display_assign_serial()
        for move in self:
            if move.has_tracking != 'none' and move.product_id and not move.origin_returned_move_id.id and move.state not in ('done', 'cancel'):
                # Habilitar únicamente "Importar números de serie o lote"
                move.display_import_lot = True

                # Para Ventas / Despachos (salida), ocultar "Generar números de serie o lote"
                if move.picking_code == 'outgoing' or (move.picking_type_id and move.picking_type_id.use_existing_lots and not move.picking_type_id.use_create_lots):
                    move.display_assign_serial = False
                elif move.has_tracking == 'serial':
                    move.display_assign_serial = move.display_import_lot

    def _create_lot_ids_from_move_line_vals(self, vals_list, product_id, company_id):
        """En operaciones de Ventas/Despachos (salida), validar estrictamente que todos los seriales importados existan en inventario."""
        def _extract_id(val):
            if isinstance(val, dict):
                return val.get('id')
            if isinstance(val, (tuple, list)) and val:
                return val[0]
            if isinstance(val, int):
                return val
            if hasattr(val, 'id'):
                return val.id
            return False

        is_outgoing = False

        if vals_list:
            first_vals = vals_list[0]
            pt_id = _extract_id(first_vals.get('picking_type_id'))
            p_id = _extract_id(first_vals.get('picking_id'))

            picking = self.env['stock.picking'].browse(p_id) if p_id else False
            picking_type = picking.picking_type_id if picking else (self.env['stock.picking.type'].browse(pt_id) if pt_id else False)

            if picking_type:
                is_outgoing = (picking_type.code == 'outgoing') or (picking_type.use_existing_lots and not picking_type.use_create_lots)

            if not is_outgoing and first_vals.get('location_dest_id'):
                ld_id = _extract_id(first_vals.get('location_dest_id'))
                if ld_id:
                    dest_loc = self.env['stock.location'].browse(ld_id)
                    if dest_loc.usage in ('customer', 'supplier'):
                        is_outgoing = True

        if not is_outgoing and self:
            is_outgoing = any(m.picking_code == 'outgoing' or (m.picking_type_id and m.picking_type_id.use_existing_lots and not m.picking_type_id.use_create_lots) for m in self)

        if is_outgoing:
            lot_names = {vals['lot_name'] for vals in vals_list if vals.get('lot_name')}
            if lot_names:
                existing_lots = self.env['stock.lot'].search([
                    ('product_id', '=', product_id),
                    ('company_id', '=', company_id),
                    ('name', 'in', list(lot_names)),
                ])
                existing_names = set(existing_lots.mapped('name'))
                missing_lots = lot_names - existing_names
                if missing_lots:
                    product = self.env['product.product'].browse(product_id)
                    raise UserError(_(
                        "No se puede realizar la importación. Los siguientes números de serie/lote no existen en el inventario para el producto '%s':\n\n%s\n\nEn las ventas y despachos solo se permite asignar números de serie previamente existentes en el sistema."
                    ) % (product.display_name, '\n'.join(sorted(missing_lots))))

        return super()._create_lot_ids_from_move_line_vals(vals_list, product_id, company_id)
