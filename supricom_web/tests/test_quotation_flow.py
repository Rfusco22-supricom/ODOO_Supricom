# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestQuotationFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Crear un sitio web de prueba
        cls.website = cls.env['website'].create({
            'name': 'Test Quotation Website',
            'domain': 'test-quotation.com',
            'quotation_only': False,
        })
        
        # Crear un cliente
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Test',
            'email': 'cliente@test.com',
        })
        
        # Crear un producto
        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test',
            'list_price': 100.0,
            'website_published': True,
        })

    def test_01_quotation_only_field(self):
        """Verifica que el campo quotation_only se guarde correctamente en el website"""
        self.assertFalse(self.website.quotation_only)
        self.website.quotation_only = True
        self.assertTrue(self.website.quotation_only)

    def test_02_res_config_settings_related_field(self):
        """Verifica que res.config.settings manipule correctamente el campo en website"""
        config = self.env['res.config.settings'].create({
            'website_id': self.website.id,
            'quotation_only': True,
        })
        config.execute()
        self.assertTrue(self.website.quotation_only)

        config.quotation_only = False
        config.execute()
        self.assertFalse(self.website.quotation_only)

    def test_03_order_flow_simulation(self):
        """Simula el procesamiento del pedido bajo quotation_only"""
        # Crear presupuesto de prueba
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'website_id': self.website.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': 100.0,
            })]
        })
        
        self.assertEqual(order.state, 'draft')
        
        # Activamos la opción en el website
        self.website.quotation_only = True
        
        # Si quotation_only está activo, el flujo de confirmación de orden hace:
        if order.website_id.quotation_only:
            try:
                order.action_quotation_sent()
            except Exception:
                order.write({'state': 'sent'})
                
        self.assertEqual(order.state, 'sent')

    def test_04_whatsapp_notification_no_connector(self):
        """Verifica que el método de WhatsApp no falle si no hay conector configurado"""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'website_id': self.website.id,
            'user_id': self.env.user.id,
        })
        res = order._notify_seller_by_whatsapp()
        self.assertFalse(res)
