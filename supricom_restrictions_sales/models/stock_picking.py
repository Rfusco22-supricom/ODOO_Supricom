# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        for picking in self:
            # Aplicar restricción en despachos de salida o provenientes de órdenes de venta
            if picking.picking_type_code == 'outgoing' or picking.sale_id:
                sale_orders = picking.sale_id
                if not sale_orders and picking.move_ids:
                    sale_orders = picking.move_ids.mapped('sale_line_id.order_id')

                if sale_orders:
                    for sale in sale_orders:
                        posted_invoices = sale.invoice_ids.filtered(
                            lambda inv: inv.move_type == 'out_invoice'
                            and inv.state == 'posted'
                            and (not inv.company_id or not picking.company_id or inv.company_id == picking.company_id)
                        )
                        if not posted_invoices:
                            raise UserError(_(
                                "No está permitido realizar el despacho %s sin que la orden de venta %s "
                                "haya sido facturada y emitida previamente en la empresa."
                            ) % (picking.name or '', sale.name or ''))

        return super(StockPicking, self).button_validate()

    def action_cancel(self):
        for picking in self.sudo():
            if picking.state == 'done':
                raise UserError(_(
                    "No está permitido cancelar un despacho que ya ha sido validado (%s). "
                    "El proceso correcto requiere realizar una Devolución (Return) de mercancía."
                ) % picking.name)
        return super(StockPicking, self).action_cancel()
