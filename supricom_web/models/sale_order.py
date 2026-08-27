# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


def _normalize_phone_by_country(phone, phone_code):
    if not phone:
        return False
    # Dejar solo dígitos
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if not phone_code:
        return digits
    phone_code_str = str(phone_code)
    # Si ya empieza con el código de país, no hacemos nada
    if digits.startswith(phone_code_str):
        return digits
    # Si empieza con 0, removerlo y anteponer el código de país
    if digits.startswith('0'):
        return f"{phone_code_str}{digits[1:]}"
    # De lo contrario, anteponer el código de país
    return f"{phone_code_str}{digits}"


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _notify_seller_by_whatsapp(self):
        self.ensure_one()
        try:
            # Verificar si hay un conector de WhatsApp activo
            Connector = self.env['acrux.chat.connector'].sudo()
            connector = Connector.search([('ca_status', '=', True)], limit=1) or Connector.search([], limit=1)
            if not connector:
                _logger.warning("No WhatsApp connector found to send notification.")
                return False

            # Ubicar al vendedor de la orden
            user = self.user_id
            if not user:
                _logger.warning("No salesperson assigned to the order %s.", self.name)
                return False

            # Buscar el teléfono del vendedor (empleado o usuario/partner)
            phone = False
            if self.env['ir.module.module'].sudo().search([('name', '=', 'hr'), ('state', '=', 'installed')], limit=1):
                employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
                if employee:
                    phone = employee.mobile_phone or employee.work_phone
            
            if not phone:
                phone = user.partner_id.mobile or user.partner_id.phone

            if not phone:
                _logger.warning("No phone number found for salesperson %s.", user.name)
                return False

            # Obtener el prefijo del país de la empresa
            phone_code = self.company_id.country_id.phone_code
            # Normalizar el número de teléfono basado en el país de la empresa
            normalized_phone = _normalize_phone_by_country(phone, phone_code)
            # Limpiar el número de teléfono con el conector
            cleaned_phone = connector.clean_id(normalized_phone)
            if not cleaned_phone:
                _logger.warning("Salesperson phone number %s is not valid.", phone)
                return False

            # Buscar o crear la conversación
            Conversation = self.env['acrux.chat.conversation'].sudo()
            conv = Conversation.search([
                ('number', '=', cleaned_phone),
                ('connector_id', '=', connector.id)
            ], limit=1)
            if not conv:
                conv = Conversation.conversation_create(
                    partner_id=user.partner_id,
                    connector_id=connector.id,
                    number=cleaned_phone
                )

            # Generar el resumen de la orden/cotización
            currency = self.currency_id.symbol or "$"
            msg_text = f"📝 *Nueva Solicitud de Cotización Recibida (Web)*\n\n"
            msg_text += f"*Cotización:* {self.name}\n"
            msg_text += f"*Cliente:* {self.partner_id.name}\n"
            msg_text += f"*Total:* {currency}{self.amount_total:.2f}\n\n"
            msg_text += f"*Resumen de Productos:*\n"
            for line in self.order_line.filtered(lambda l: not l.display_type):
                msg_text += f"• {line.product_id.display_name.strip()} (Qty: {int(line.product_uom_qty)}) - {currency}{line.price_subtotal:.2f}\n"

            # Enviar el mensaje
            conv.send_message({
                'text': msg_text,
                'from_me': True,
                'ttype': 'text',
                'contact_id': conv.id,
            }, check_access=False)
            _logger.info("WhatsApp notification sent to salesperson %s for order %s", user.name, self.name)
            return True
        except Exception as e:
            _logger.error("Error in WhatsApp notification for order %s: %s", self.name, str(e))
            return False
