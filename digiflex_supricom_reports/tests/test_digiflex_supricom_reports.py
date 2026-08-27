# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from datetime import date


class TestDigiflexSupricomReports(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson = cls.env['res.users'].create({
            'name': 'Vendedor Test',
            'login': 'vendedor_test@example.com',
            'email': 'vendedor_test@example.com',
        })
        cls.customer = cls.env['res.partner'].create({
            'name': 'Cliente Test',
            'ref': 'CLI001',
            'user_id': cls.salesperson.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test',
            'list_price': 100.0,
            'standard_price': 60.0,
            'type': 'product',
        })

    def test_01_payment_salesperson_computation(self):
        """Test: salesperson_id on account.payment is correctly computed."""
        journal = self.env['account.journal'].search([('type', 'in', ('bank', 'cash'))], limit=1)
        if not journal:
            return

        payment = self.env['account.payment'].create({
            'partner_id': self.customer.id,
            'partner_type': 'customer',
            'payment_type': 'inbound',
            'amount': 100.0,
            'journal_id': journal.id,
            'date': date.today(),
        })
        self.assertEqual(payment.salesperson_id, self.salesperson)

    def test_02_sale_order_operation_status(self):
        """Test: sale.order operation_status computation."""
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'user_id': self.salesperson.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 2.0,
                'price_unit': 100.0,
            })],
        })
        self.assertEqual(order.operation_status, 'draft')
        self.assertFalse(order.is_partially_operated)

    def test_03_margin_wizard_domain(self):
        """Test: digiflex.sales.margin.wizard domain generation."""
        wizard = self.env['digiflex.sales.margin.wizard'].create({
            'date_from': date.today().replace(day=1),
            'date_to': date.today(),
            'sale_condition': 'cash',
            'movement_type': 'sales',
            'sale_type': 'products',
        })
        domain = wizard._get_report_domain()
        self.assertTrue(any(item == ('sale_condition', '=', 'cash') for item in domain))
        self.assertTrue(any(item == ('movement_type', '=', 'sales') for item in domain))
        self.assertTrue(any(item == ('product_type', '=', 'product') for item in domain))
