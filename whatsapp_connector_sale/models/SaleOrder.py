# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import base64
import uuid

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    conversation_id = fields.Many2one('acrux.chat.conversation', 'ChatRoom', ondelete='set null', copy=False)

    def action_confirm(self):
        result = super(SaleOrder, self).action_confirm()
        for order in self:
            order._send_pdf_via_whatsapp_if_website()
        return result

    def _send_pdf_via_whatsapp_if_website(self):
        self.ensure_one()
        
        # 1. Corrección: Validar contra el campo medium_id (utm.medium) según la imagen
        if self.medium_id and self.medium_id.name.lower() in ['sitio web', 'website']:
            if not self.conversation_id:
                # Intentar obtener la conversación del partner (Lógica típica de Acrux)
                if self.partner_id.contact_ids:
                    self.conversation_id = self.partner_id.contact_ids[0]
            
            if self.conversation_id:
                self._send_order_pdf_via_whatsapp()
            else:
                # Log warning pero no bloquear la confirmación
                self.message_post(
                    body=_('No se encontró conversación de WhatsApp para el cliente %s. '
                           'No se envió el PDF del pedido.') % self.partner_id.name
                )

    def _send_order_pdf_via_whatsapp(self):
        self.ensure_one()
        try:
            # Generar el PDF del pedido
            report_name = 'sale.report_saleorder'
            
            # CORRECCIÓN: Usamos 'report_type' en lugar de '_' para no sobreescribir la función de traducción
            pdf_content, report_type = self.env['ir.actions.report']._render_qweb_pdf(report_name, self.ids)
            
            # Crear el attachment
            attachment_name = _('Pedido_%s.pdf') % self.name
            attachment = self.env['ir.attachment'].sudo().create({
                'name': attachment_name,
                'datas': base64.b64encode(pdf_content),
                'res_model': 'sale.order',
                'res_id': self.id,
                'type': 'binary',
                'mimetype': 'application/pdf',
                'public': True,  # <-- ESTO ES CLAVE PARA QUE LA API LO PUEDA DESCARGAR
                'access_token': str(uuid.uuid4()),  # <-- Garantiza que el token exista de inmediato
            })
            
            # Crear el wizard para enviar el mensaje
            MessageWizard = self.env['acrux.chat.message.wizard']
            wizard = MessageWizard.create({
                'conversation_id': self.conversation_id.id,
                'text': _('Su pedido %s ha sido confirmado. Adjuntamos el PDF.') % self.name,
                'attachment_ids': [(4, attachment.id)],
            })
            
            # ¡CLAVE! Forzar el guardado en la base de datos antes de hacer la petición HTTP
            # Esto hace que el archivo sea visible para cuando WhatsApp venga a buscarlo
            self.env.cr.commit()
            
            # Enviar el mensaje
            wizard.send_message_wizard()
            
            # Log del envío
            self.message_post(
                body=_('PDF del pedido %s enviado por WhatsApp al cliente %s.') % (self.name, self.partner_id.name)
            )
            
        except Exception as e:
            # Log error pero no bloquear la confirmación
            self.message_post(
                body=_('Error al enviar PDF del pedido %s por WhatsApp: %s') % (self.name, str(e))
            )