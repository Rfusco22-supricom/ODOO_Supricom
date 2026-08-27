# models/sale_order_credit.py
from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class SaleOrderCreditExtension(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        """Override to extend payment terms based on brand credit extension days."""
        for order in self:
            try:
                order._apply_brand_credit_extension()
            except Exception as e:
                _logger.warning(
                    "Error applying brand credit extension on SO %s: %s",
                    order.name, e,
                )
        return super().action_confirm()

    def _apply_brand_credit_extension(self):
        """
        Si todos los productos del pedido pertenecen a una sola marca con
        extensión de crédito, se modifica el término de pago sumando los días
        adicionales. Si hay múltiples marcas con extensión, se notifica en el
        chatter sin modificar.
        """
        self.ensure_one()

        if not self.order_line:
            return

        # Filtrar líneas que tienen producto (ignorar secciones y notas)
        all_product_lines = self.order_line.filtered(lambda l: l.product_id)

        if not all_product_lines:
            return

        # Recolectar marcas SPIFF únicas con extensión de crédito
        brands_with_extension = self.env['spiff.brand']
        for line in all_product_lines:
            tmpl = line.product_id.product_tmpl_id
            brand = tmpl.spiff_brand_id if hasattr(tmpl, 'spiff_brand_id') else False
            if brand and brand.credit_extension_days > 0:
                brands_with_extension |= brand

        if not brands_with_extension:
            # Ninguna marca tiene extensión de crédito configurada
            return

        if len(brands_with_extension) > 1:
            # Múltiples marcas con extensión → no aplica, notificar
            brand_names = ", ".join(brands_with_extension.mapped('name'))
            self.message_post(
                body=_(
                    "⚠️ <b>Extensión de crédito no aplicada:</b> El pedido contiene "
                    "productos de múltiples marcas con extensión de crédito (%s). "
                    "La extensión solo aplica cuando el pedido contiene exclusivamente "
                    "productos de una sola marca con extensión.",
                    brand_names,
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            return

        # Una sola marca con extensión encontrada
        brand = brands_with_extension[0]

        # Verificar que NO haya productos de OTRA marca distinta
        for line in all_product_lines:
            tmpl = line.product_id.product_tmpl_id
            line_brand = tmpl.spiff_brand_id if hasattr(tmpl, 'spiff_brand_id') else False
            if line_brand and line_brand != brand:
                self.message_post(
                    body=_(
                        "⚠️ <b>Extensión de crédito no aplicada:</b> El pedido contiene "
                        "productos de la marca '%s' (con extensión de %d días) pero también "
                        "tiene productos de otras marcas. La extensión solo aplica si el "
                        "pedido contiene exclusivamente productos de esa marca.",
                        brand.name,
                        brand.credit_extension_days,
                    ),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
                return

        # Verificar que haya un término de pago asignado
        if not self.payment_term_id:
            return

        extra_days = brand.credit_extension_days
        original_term = self.payment_term_id

        # Crear o buscar un término de pago extendido
        new_term = self._get_or_create_extended_payment_term(
            original_term, extra_days, brand
        )
        if new_term and new_term != original_term:
            self.payment_term_id = new_term
            self.message_post(
                body=_(
                    "✅ <b>Extensión de crédito aplicada:</b> La marca '%s' extiende "
                    "%d días adicionales de crédito. Término de pago cambiado de '%s' a '%s'.",
                    brand.name,
                    extra_days,
                    original_term.name,
                    new_term.name,
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def _get_or_create_extended_payment_term(self, original_term, extra_days, brand):
        """
        Busca o crea un account.payment.term extendido sumando extra_days
        a cada línea del término original.
        """
        PaymentTerm = self.env['account.payment.term']
        extended_name = "%s + %d días (%s)" % (original_term.name, extra_days, brand.name)

        # Buscar si ya existe un término con ese nombre
        existing = PaymentTerm.search([('name', '=', extended_name)], limit=1)
        if existing:
            return existing

        # Preparar líneas del nuevo término copiando estructura del original
        line_vals = []
        for line in original_term.line_ids:
            vals = {
                'value': line.value,
                'value_amount': line.value_amount,
                'nb_days': line.nb_days + extra_days,
            }
            # Copiar delay_type si existe (Odoo 17+)
            if hasattr(line, 'delay_type') and line.delay_type:
                vals['delay_type'] = line.delay_type
            line_vals.append((0, 0, vals))

        new_term_vals = {
            'name': extended_name,
            'note': "Generado automáticamente. Término original: %s, "
                    "con extensión de %d días por marca %s." % (
                        original_term.name, extra_days, brand.name
                    ),
            'line_ids': line_vals,
        }

        # Copiar company_id si existe en el modelo
        if hasattr(original_term, 'company_id') and original_term.company_id:
            new_term_vals['company_id'] = original_term.company_id.id

        try:
            new_term = PaymentTerm.sudo().create(new_term_vals)
            _logger.info(
                "Created extended payment term '%s' from '%s' (+%d days for brand %s)",
                extended_name, original_term.name, extra_days, brand.name,
            )
            return new_term
        except Exception as e:
            _logger.error("Error creating extended payment term: %s", e)
            return original_term
