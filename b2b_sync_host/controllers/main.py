# -*- coding: utf-8 -*-
import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class B2bHostController(http.Controller):

    def _authenticate_client(self):
        """Valida la cabecera Bearer Token y retorna el registro b2b.client.config o raise error dict."""
        auth_header = request.httprequest.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ", 1)[1].strip()

        if not token:
            return None, {"status": "error", "message": "Autenticación requerida. Token Bearer ausente."}

        client_config = request.env["b2b.client.config"].sudo().search([
            ("api_key", "=", token),
            ("active", "=", True),
        ], limit=1)

        if not client_config:
            return None, {"status": "error", "message": "Token / API Key B2B no autorizada."}

        return client_config, None

    def _get_request_params(self, kwargs):
        """Extrae de forma transparente los parámetros enviados vía kwargs o JSON-RPC params."""
        req_json = getattr(request.dispatcher, "jsonrequest", {}) or {}
        if isinstance(req_json, dict) and "params" in req_json:
            return req_json["params"]
        return kwargs or req_json

    @http.route("/api/b2b/v1/pricelist", type="json", auth="none", methods=["GET", "POST"], csrf=False)
    def get_pricelist(self, **kwargs):
        """Devuelve el catálogo completo de productos, precios y existencias (sin imágenes para máxima velocidad)."""
        client_config, error = self._authenticate_client()
        if error:
            return error

        data = self._get_request_params(kwargs)
        search_query = data.get("query", "")
        limit = data.get("limit", 0)  # 0 significa sin límite (retorna todos los productos)

        # Establecer compañía activa para evitar errores SQL en la conversión de moneda
        company = client_config.partner_id.company_id or request.env["res.company"].sudo().search([], limit=1)
        
        pricelist = client_config.pricelist_id.sudo().with_company(company)
        partner = client_config.partner_id.sudo().with_company(company)

        domain = [
            ("sale_ok", "=", True),
            ("default_code", "!=", False),
        ]
        if search_query:
            domain.append("|")
            domain.append(("name", "ilike", search_query))
            domain.append(("default_code", "ilike", search_query))

        products = request.env["product.product"].sudo().with_company(company).search(domain, limit=limit if limit and limit > 0 else None)

        product_list = []
        for product in products:
            price = 0.0
            if hasattr(pricelist, "_get_product_price"):
                try:
                    price = pricelist._get_product_price(product, 1.0, partner=partner)
                except TypeError:
                    price = pricelist._get_product_price(product, 1.0)
            elif hasattr(pricelist, "get_product_price"):
                price = pricelist.get_product_price(product, 1.0, partner)
            else:
                price = product.lst_price

            product_list.append({
                "supplier_ref": product.default_code,
                "name": product.name,
                "price": price,
                "qty_available": product.qty_available,
                "currency": pricelist.currency_id.name if pricelist.currency_id else "",
                "image_1920": False,
            })

        return {
            "status": "success",
            "client": client_config.name,
            "pricelist": pricelist.name,
            "products": product_list,
        }

    @http.route("/api/b2b/v1/stock", type="json", auth="none", methods=["GET", "POST"], csrf=False)
    def get_stock(self, **kwargs):
        """Devuelve las existencias disponibles de los productos."""
        client_config, error = self._authenticate_client()
        if error:
            return error

        company = client_config.partner_id.company_id or request.env["res.company"].sudo().search([], limit=1)

        products = request.env["product.product"].sudo().with_company(company).search([
            ("type", "in", ["product", "consu"]),
            ("default_code", "!=", False),
        ])

        stock_data = []
        for product in products:
            stock_data.append({
                "supplier_ref": product.default_code,
                "qty_available": product.qty_available,
            })

        return {
            "status": "success",
            "client": client_config.name,
            "stock_data": stock_data,
        }

    @http.route("/api/b2b/v1/order_status", type="json", auth="none", methods=["GET", "POST"], csrf=False)
    def get_order_status(self, **kwargs):
        """Devuelve el estado actual de un pedido de venta en Supricom."""
        client_config, error = self._authenticate_client()
        if error:
            return error

        data = self._get_request_params(kwargs)
        client_po_ref = data.get("client_po_ref")
        sale_order_ref = data.get("sale_order_ref")

        commercial_partner_id = client_config.partner_id.commercial_partner_id.id or client_config.partner_id.id
        domain = [("partner_id.commercial_partner_id", "=", commercial_partner_id)]

        if sale_order_ref:
            domain.append(("name", "=", sale_order_ref))
        elif client_po_ref:
            domain.append(("b2b_client_po_ref", "=", client_po_ref))
        else:
            return {"status": "error", "message": "Debe proporcionar 'client_po_ref' o 'sale_order_ref'."}

        sale_order = request.env["sale.order"].sudo().search(domain, limit=1)
        if not sale_order:
            return {"status": "error", "message": "Pedido de venta no encontrado en Supricom."}

        return {
            "status": "success",
            "sale_order_name": sale_order.name,
            "b2b_client_po_ref": sale_order.b2b_client_po_ref,
            "order_state": sale_order._get_b2b_effective_status(),
        }

    @http.route("/api/b2b/v1/create_sale_order", type="json", auth="none", methods=["POST"], csrf=False)
    def create_sale_order(self, **kwargs):
        """Recibe la orden de compra de Digiflex y crea un Pedido de Venta en Supricom."""
        client_config, error = self._authenticate_client()
        if error:
            return error

        data = self._get_request_params(kwargs)
        client_po_ref = data.get("client_po_ref")
        callback_url = data.get("callback_url")
        lines = data.get("lines", [])

        if not client_po_ref or not lines:
            return {"status": "error", "message": "Datos incompletos ('client_po_ref' y 'lines' son obligatorios)."}

        company = client_config.partner_id.company_id or request.env["res.company"].sudo().search([], limit=1)
        SaleOrder = request.env["sale.order"].sudo().with_company(company)
        ProductProduct = request.env["product.product"].sudo().with_company(company)

        # Verificar si ya existe el pedido para evitar duplicados
        existing = SaleOrder.search([
            ("partner_id", "=", client_config.partner_id.id),
            ("b2b_client_po_ref", "=", client_po_ref),
        ], limit=1)
        if existing:
            return {
                "status": "success",
                "sale_order_name": existing.name,
                "is_confirmed": existing.state == "sale",
                "message": f"Pedido ya existente en Supricom ({existing.name}).",
            }

        order_line_vals = []
        for line in lines:
            supplier_ref = line.get("supplier_ref")
            qty = float(line.get("product_qty", 1.0))

            product = ProductProduct.search([("default_code", "=", supplier_ref)], limit=1)
            if not product:
                return {"status": "error", "message": f"Producto con referencia '{supplier_ref}' no encontrado en Supricom."}

            order_line_vals.append((0, 0, {
                "product_id": product.id,
                "product_uom_qty": qty,
                "price_unit": line.get("price_unit", product.lst_price),
                "name": line.get("name") or product.name,
            }))

        sale_order = SaleOrder.create({
            "partner_id": client_config.partner_id.id,
            "pricelist_id": client_config.pricelist_id.id,
            "b2b_client_po_ref": client_po_ref,
            "b2b_client_callback_url": callback_url,
            "order_line": order_line_vals,
        })

        is_confirmed = False
        if client_config.auto_confirm_orders:
            try:
                sale_order.action_confirm()
                is_confirmed = True
            except Exception as e:
                _logger.warning("No se pudo auto-confirmar el pedido %s en Supricom: %s", sale_order.name, str(e))
                is_confirmed = False

        msg = _("Pedido de venta %s creado en Supricom.") % sale_order.name
        if not is_confirmed and client_config.auto_confirm_orders:
            msg += _(" (Quedó en borrador pendiente por asignación de almacén/stock en Supricom)")

        return {
            "status": "success",
            "sale_order_name": sale_order.name,
            "is_confirmed": is_confirmed,
            "message": msg,
        }
