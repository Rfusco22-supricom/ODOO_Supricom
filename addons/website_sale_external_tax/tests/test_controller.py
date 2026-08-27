# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from unittest.mock import patch

from odoo.addons.website_sale_external_tax.controllers.main import WebsiteSaleExternalTaxCalculation
from odoo.addons.website_sale.controllers.delivery import WebsiteSaleDelivery as WebsiteSaleDeliveryController
from odoo.exceptions import ValidationError, UserError
from odoo.tests import tagged
from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.website.tools import MockRequest


@tagged('post_install', '-at_install')
class TestWebsiteSaleExternalTaxCalculation(PaymentHttpCommon):
    def setUp(self):
        super().setUp()
        self.website = self.env.ref('website.default_website')
        self.Controller = WebsiteSaleExternalTaxCalculation()

    def test_validate_payment_with_error_from_external_provider(self):
        """
        Payment should be blocked if external tax provider raises an error
        (invalid address, connection issue, etc ...)
        """
        with patch(
            'odoo.addons.account_external_tax.models.account_external_tax_mixin.AccountExternalTaxMixin._get_external_taxes',
            side_effect=UserError('bim bam boom')
        ):
            with MockRequest(self.env, website=self.website):
                self.website.sale_get_order(force_create=True)
                with self.assertRaisesRegex(ValidationError, 'bim bam boom'):
                    self.Controller.shop_payment_validate()

    def test_external_taxes_apply_on_express_checkout(self):
        """Ensure external taxes are computed during express checkout route call."""
        published_product = self.env['product.product'].search(
            [('website_published', '=', True)],
            limit=1,
        )
        self.make_jsonrpc_request("/shop/cart/update_json", {
            'product_id': published_product.id,
            'add_qty': 1,
        })

        with patch.object(
            self.env.registry['sale.order'],
            '_get_and_set_external_taxes_on_eligible_records',
        ) as mock:
            self.make_jsonrpc_request(
                WebsiteSaleDeliveryController._express_checkout_shipping_route + '/compute_taxes', {}
            )
            self.assertEqual(mock.call_count, 1)
