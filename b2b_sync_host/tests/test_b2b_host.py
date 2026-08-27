# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestB2bSyncHost(TransactionCase):

    def setUp(self):
        super(TestB2bSyncHost, self).setUp()
        self.Partner = self.env["res.partner"]
        self.Pricelist = self.env["product.pricelist"]
        self.ClientConfig = self.env["b2b.client.config"]

        self.partner = self.Partner.create({"name": "Digiflex Cliente Test", "customer_rank": 1})
        self.pricelist = self.Pricelist.create({"name": "Tarifa B2B Test"})
        self.config = self.ClientConfig.create({
            "name": "Digiflex Test",
            "partner_id": self.partner.id,
            "pricelist_id": self.pricelist.id,
            "auto_confirm_orders": True,
        })

    def test_client_config_key_generation(self):
        """Verifica la generación de la API Key única para el cliente."""
        self.assertTrue(bool(self.config.api_key))
        old_key = self.config.api_key
        self.config.action_generate_new_key()
        self.assertNotEqual(old_key, self.config.api_key)
