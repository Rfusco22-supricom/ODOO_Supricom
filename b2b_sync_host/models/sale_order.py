# -*- coding: utf-8 -*-
import logging
import requests
from odoo import fields, models, _

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    b2b_client_po_ref = fields.Char(
        string="Ref. PO Cliente (Digiflex)",
        readonly=True,
        copy=False,
    )
    b2b_client_callback_url = fields.Char(
        string="Webhook Callback URL Cliente",
        readonly=True,
        copy=False,
    )

    def _get_b2b_effective_status(self):
        """Calcula el estado B2B real considerando despachos y facturación."""
        self.ensure_one()
        if self.state == "cancel":
            return "cancel"
        if self.state in ("draft", "sent"):
            return "draft"

        # 1. Verificar si todas las entregas/despachos del pedido están realizadas
        pickings = self.picking_ids.filtered(lambda p: p.state != "cancel")
        if pickings and all(p.state == "done" for p in pickings):
            return "delivered"
        if hasattr(self, "delivery_status") and self.delivery_status == "full":
            return "delivered"

        # 2. Verificar si las facturas del cliente están publicadas y cubren el pedido
        posted_invoices = self.invoice_ids.filtered(lambda m: m.move_type == "out_invoice" and m.state == "posted")
        if posted_invoices:
            if hasattr(self, "invoice_status") and self.invoice_status == "invoiced":
                return "invoiced"
            order_lines = self.order_line.filtered(lambda l: not l.display_type and l.product_id)
            if order_lines and all(l.qty_invoiced >= l.product_uom_qty for l in order_lines):
                return "invoiced"

        return "sale"

    def _notify_b2b_status_update(self, status=False, carrier_name=False, tracking_ref=False):
        """Notifica automáticamente al cliente (Digiflex) los cambios en el estado del pedido mediante webhook JSON-RPC."""
        for order in self:
            po_ref = order.b2b_client_po_ref
            if not po_ref:
                continue

            eff_status = status or order._get_b2b_effective_status()

            commercial_partner = order.partner_id.commercial_partner_id or order.partner_id
            client_config = self.env["b2b.client.config"].sudo().search([
                "|",
                ("partner_id", "=", order.partner_id.id),
                ("partner_id", "=", commercial_partner.id),
            ], limit=1)

            callback_url = order.b2b_client_callback_url
            if not callback_url and client_config and hasattr(client_config, "client_url") and client_config.client_url:
                callback_url = f"{client_config.client_url.rstrip('/')}/api/b2b/client/order_status_update"

            if not callback_url:
                _logger.warning("No se pudo notificar a Digiflex para el pedido %s: callback_url ausente.", order.name)
                continue

            api_key = client_config.api_key if client_config else ""

            payload = {
                "client_po_ref": po_ref,
                "host_sale_order_ref": order.name,
                "status": eff_status,
                "api_key": api_key,
            }
            if carrier_name:
                payload["carrier_name"] = carrier_name
            if tracking_ref:
                payload["tracking_ref"] = tracking_ref

            jsonrpc_payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": payload,
            }

            try:
                headers = {"Content-Type": "application/json"}
                res = requests.post(callback_url, json=jsonrpc_payload, headers=headers, timeout=10)
                _logger.info("Notificación Webhook B2B enviada a %s (%s -> %s): HTTP %s", callback_url, order.name, eff_status, res.status_code)
            except Exception as e:
                _logger.error("Error al enviar notificación Webhook B2B para %s a %s: %s", order.name, callback_url, str(e))

    def action_confirm(self):
        res = super(SaleOrder, self).action_confirm()
        self._notify_b2b_status_update()
        return res

    def action_cancel(self):
        res = super(SaleOrder, self).action_cancel()
        self._notify_b2b_status_update()
        return res

    def write(self, vals):
        res = super(SaleOrder, self).write(vals)
        if "state" in vals:
            for order in self:
                if order.b2b_client_po_ref:
                    order._notify_b2b_status_update()
        return res


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        res = super(StockPicking, self)._action_done()
        for picking in self:
            sale_order = picking.sale_id or (picking.group_id and hasattr(picking.group_id, "mto_sale_order_id") and picking.group_id.mto_sale_order_id)
            if sale_order and sale_order.b2b_client_po_ref:
                carrier_name = getattr(picking.carrier_id, "name", False) if hasattr(picking, "carrier_id") else False
                tracking_ref = getattr(picking, "carrier_tracking_ref", False) or getattr(picking, "tracking_ref", False) or False
                sale_order._notify_b2b_status_update(carrier_name=carrier_name, tracking_ref=tracking_ref)
        return res


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        res = super(AccountMove, self).action_post()
        for move in self:
            if move.move_type == "out_invoice":
                sale_orders = move.invoice_line_ids.mapped("sale_line_ids.order_id")
                for order in sale_orders:
                    if order.b2b_client_po_ref:
                        order._notify_b2b_status_update()
        return res
