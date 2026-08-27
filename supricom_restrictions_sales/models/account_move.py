# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _check_picking_done_cancellation_restriction(self):
        for move in self:
            if move.is_invoice(include_receipts=True):
                # 1. Buscar despachos por líneas de venta de la factura (filtrando por la misma empresa de la factura)
                sale_orders = (move.line_ids | move.invoice_line_ids).sudo().sale_line_ids.order_id
                done_pickings = sale_orders.picking_ids.filtered(
                    lambda p: p.state == 'done' and (not p.company_id or not move.company_id or p.company_id == move.company_id)
                )

                # 2. Buscar por origin dentro de la misma empresa de la factura
                if not done_pickings and move.invoice_origin:
                    domain = [
                        ('state', '=', 'done'),
                        '|',
                        ('origin', '=', move.invoice_origin),
                        ('group_id.name', '=', move.invoice_origin)
                    ]
                    if move.company_id:
                        domain.append(('company_id', '=', move.company_id.id))
                    done_pickings = self.env['stock.picking'].sudo().search(domain)

                # 3. Buscar por stock.move vinculados por origin dentro de la misma empresa
                if not done_pickings and move.invoice_origin:
                    sm_domain = [
                        ('state', '=', 'done'),
                        ('origin', '=', move.invoice_origin)
                    ]
                    if move.company_id:
                        sm_domain.append(('company_id', '=', move.company_id.id))
                    done_stock_moves = self.env['stock.move'].sudo().search(sm_domain)
                    if done_stock_moves:
                        done_pickings = done_stock_moves.picking_id

                if done_pickings:
                    picking_names = ', '.join(done_pickings.mapped('name'))
                    raise UserError(_(
                        "No está permitido cancelar la factura %s porque cuenta con despachos o entregas validadas en su empresa (%s). "
                        "El proceso correcto requiere la emisión de una Nota de Crédito."
                    ) % (move.name or '', picking_names))

    def button_cancel(self):
        self._check_picking_done_cancellation_restriction()
        return super(AccountMove, self).button_cancel()

    def write(self, vals):
        if vals.get('state') == 'cancel':
            moves_to_check = self.filtered(lambda m: m.state != 'cancel')
            moves_to_check._check_picking_done_cancellation_restriction()
        return super(AccountMove, self).write(vals)
