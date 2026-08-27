from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_assign(self, force_qty=False):
        """
        Evita la asignación automática indeseada de lotes en transferencias directas,
        pero hereda/conserva los lotes/seriales cuando el movimiento proviene de
        una transferencia previa encadenada (ej. Recepción en 2 pasos: Entrada -> Stock).
        """
        res = super()._action_assign(force_qty=force_qty)
        for move in self:
            # Si el movimiento tiene origen encadenado (ej. paso 2 de recepción),
            # heredamos/mantenemos los seriales asignados en el paso 1.
            if move.move_orig_ids:
                orig_move_lines = move.move_orig_ids.move_line_ids.filtered(lambda ml: ml.lot_id or ml.lot_name)
                if orig_move_lines:
                    for ml in move.move_line_ids:
                        if not ml.lot_id and not ml.lot_name:
                            matching_orig = orig_move_lines.filtered(
                                lambda o_ml: o_ml.product_id == ml.product_id and o_ml.lot_id
                            )
                            if matching_orig:
                                # Asignar el lote del paso de origen
                                unused_orig = matching_orig.filtered(
                                    lambda o_ml: o_ml.lot_id.id not in move.move_line_ids.mapped('lot_id').ids
                                )
                                target_orig = unused_orig[0] if unused_orig else matching_orig[0]
                                ml.write({
                                    'lot_id': target_orig.lot_id.id,
                                })
                continue

            # Para movimientos sin origen encadenado, se remueve la autoasignación de lotes
            tracked_lines = move.move_line_ids.filtered(
                lambda ml: ml.product_id.tracking != 'none' and (ml.lot_id or ml.lot_name)
            )
            if tracked_lines:
                tracked_lines.write({
                    'lot_id': False,
                    'lot_name': False,
                })
        return res
