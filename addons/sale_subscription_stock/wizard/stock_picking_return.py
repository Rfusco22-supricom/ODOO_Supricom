# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking"

    def _prepare_move_default_values(self, return_line, new_picking):
        vals = super()._prepare_move_default_values(return_line, new_picking)
        origin_move = return_line.move_id
        if origin_move.sale_line_id.recurring_invoice:
            vals.update({'date_deadline': origin_move.date_deadline})
        return vals
