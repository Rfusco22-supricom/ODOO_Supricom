# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    operation_status = fields.Selection([
        ('draft', 'Presupuesto'),
        ('pending', 'Pendiente'),
        ('in_progress', 'En Proceso'),
        ('fully_operated', 'Operado Totalmente'),
        ('partially_operated', 'Operado Parcialmente'),
        ('cancelled', 'Cancelado'),
    ], string='Estado Operativo', compute='_compute_operation_status', store=True, tracking=True, index=True,
       help='Indica el estado operativo del pedido (e.g. Operado Parcialmente si fue facturado pero tiene devoluciones).')

    is_partially_operated = fields.Boolean(
        string='Operado Parcialmente',
        compute='_compute_operation_status',
        store=True,
        index=True,
        help='Indica si el pedido ya fue facturado y cuenta con alguna devolución o nota de crédito.',
    )

    has_refund_or_return = fields.Boolean(
        string='Tiene Devolución / NC',
        compute='_compute_operation_status',
        store=True,
        help='Indica si el pedido tiene al menos una nota de crédito o albarán de devolución completado.',
    )

    @api.depends(
        'state',
        'invoice_status',
        'invoice_ids',
        'invoice_ids.state',
        'invoice_ids.move_type',
        'picking_ids',
        'picking_ids.state',
        'picking_ids.picking_type_id.code',
        'order_line.qty_invoiced',
        'order_line.qty_delivered',
        'order_line.product_uom_qty',
    )
    def _compute_operation_status(self):
        for order in self:
            if order.state == 'cancel':
                order.operation_status = 'cancelled'
                order.is_partially_operated = False
                order.has_refund_or_return = False
                continue

            if order.state in ('draft', 'sent'):
                order.operation_status = 'draft'
                order.is_partially_operated = False
                order.has_refund_or_return = False
                continue

            # Invoices & Credit Notes
            posted_invoices = order.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type == 'out_invoice')
            posted_refunds = order.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type == 'out_refund')

            # Stock Pickings (Returns)
            return_pickings = order.picking_ids.filtered(
                lambda p: p.state == 'done' and (
                    p.picking_type_id.code == 'incoming' or
                    any(m.origin_returned_move_id for m in p.move_ids)
                )
            )

            has_return = bool(posted_refunds or return_pickings)
            order.has_refund_or_return = has_return

            # Determine if fully invoiced
            is_invoiced = (
                order.invoice_status == 'invoiced' or
                (bool(posted_invoices) and all(
                    l.qty_invoiced >= l.product_uom_qty
                    for l in order.order_line
                    if l.product_id and not l.display_type and l.product_uom_qty > 0
                ))
            )

            if is_invoiced and has_return:
                order.operation_status = 'partially_operated'
                order.is_partially_operated = True
            elif is_invoiced:
                order.operation_status = 'fully_operated'
                order.is_partially_operated = False
            elif any(l.qty_invoiced > 0 or l.qty_delivered > 0 for l in order.order_line if not l.display_type):
                order.operation_status = 'in_progress'
                order.is_partially_operated = False
            else:
                order.operation_status = 'pending'
                order.is_partially_operated = False
