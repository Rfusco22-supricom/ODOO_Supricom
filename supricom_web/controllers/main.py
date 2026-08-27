# -*- coding: utf-8 -*-

import logging
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)


class SupricomWebsiteSale(WebsiteSale):

    @http.route(['/shop/confirm_order'], type='http', auth="public", website=True, sitemap=False)
    def confirm_order(self, **post):
        res = super(SupricomWebsiteSale, self).confirm_order(**post)
        
        website = request.website
        if website.quotation_only:
            # Si el controlador padre redirige a la página de pago, significa que la orden es válida y está lista.
            # Verificamos si la respuesta es una redirección (código 302 o 303) a '/shop/payment'
            status_code = getattr(res, 'status_code', None) or (res.status if isinstance(res.status, int) else 302)
            location = res.headers.get('Location', '') if hasattr(res, 'headers') else ''
            
            if (status_code in (302, 303) or 'payment' in location) and '/shop/payment' in location:
                order = website.sale_get_order()
                if order:
                    # Pasar la orden a estado 'sent' (presupuesto enviado)
                    try:
                        order.action_quotation_sent()
                    except Exception:
                        order.write({'state': 'sent'})
                    
                    # Notificar al vendedor asignado vía WhatsApp
                    try:
                        order._notify_seller_by_whatsapp()
                    except Exception as e:
                        # Log error safely using controller logger
                        _logger.warning("WhatsApp notification failed: %s", str(e))
                    
                    # Guardamos la orden confirmada en la sesión para que /shop/confirmation la pueda renderizar
                    request.session['sale_last_order_id'] = order.id
                    # Reseteamos el carrito del sitio web actual
                    website.sale_reset()
                    # Redirigimos a la página de confirmación
                    return request.redirect('/shop/confirmation')
        return res

    @http.route(['/shop/payment'], type='http', auth="public", website=True, sitemap=False)
    def shop_payment(self, **post):
        # Impedir el acceso manual a la pantalla de pago si estamos en modo sólo cotización
        if request.website.quotation_only:
            return request.redirect('/shop/cart')
        return super(SupricomWebsiteSale, self).shop_payment(**post)
