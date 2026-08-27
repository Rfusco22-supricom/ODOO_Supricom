# -*- coding: utf-8 -*-
"""
Tests para pagos parciales con doble moneda.
Verifica que amount_residual y amount_residual_usd se calculen correctamente.
"""

from datetime import timedelta
from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'dual_currency')
class TestPartialPaymentDualCurrency(AccountTestInvoicingCommon):
    """Test de pagos parciales con doble moneda VEF/USD"""

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id  # VEF (moneda de la compañía)
        
        # Configurar USD como moneda dual
        cls.usd_currency = cls.env.ref('base.USD')
        if cls.usd_currency == cls.company_currency:
            cls.usd_currency = cls.env.ref('base.EUR')
        cls.company.currency_id_dif = cls.usd_currency
        
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.sales_journal = cls.company_data['default_journal_sale']
        cls.purchase_journal = cls.company_data['default_journal_purchase']
        cls.partner = cls.partner_a
        cls.product = cls.product_a
        
        # Método de pago
        method_line = cls.bank_journal.inbound_payment_method_line_ids[:1]
        if not method_line:
            method_line = cls.bank_journal.payment_method_line_ids[:1]
        cls.payment_method_line = method_line
        
        # Crear tasa de cambio base (1 USD = 50 moneda local)
        cls.base_rate = 50.0
        cls.env['res.currency.rate'].search([
            ('currency_id', '=', cls.usd_currency.id),
            ('company_id', 'in', [cls.company.id, False]),
        ]).unlink()
        cls.env['res.currency.rate'].create({
            'currency_id': cls.usd_currency.id,
            'company_id': cls.company.id,
            'name': fields.Date.today(),
            'inverse_company_rate': cls.base_rate,
        })

    def _create_invoice(self, amount, rate=None, currency=None, move_type='out_invoice'):
        """Helper para crear facturas"""
        journal = self.sales_journal if move_type in ('out_invoice', 'out_refund') else self.purchase_journal
        
        invoice = self.env['account.move'].with_context(default_move_type=move_type).create({
            'move_type': move_type,
            'partner_id': self.partner.id,
            'currency_id': (currency or self.company_currency).id,
            'journal_id': journal.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': amount,
                    'account_id': self.company_data['default_account_revenue'].id if move_type in ('out_invoice', 'out_refund') else self.company_data['default_account_expense'].id,
                })
            ],
        })
        
        if rate:
            invoice.write({
                'edit_trm': True,
                'tax_today': rate,
            })
        
        invoice.action_post()
        return invoice

    def _register_payment(self, invoice, amount, rate=None):
        """Helper para registrar un pago parcial"""
        wizard_context = {
            'active_model': 'account.move',
            'active_ids': invoice.ids,
        }
        
        wizard_vals = {
            'payment_date': fields.Date.today(),
            'journal_id': self.bank_journal.id,
            'payment_method_line_id': self.payment_method_line.id,
            'amount': amount,
            'currency_id': invoice.currency_id.id,
        }
        
        if rate:
            wizard_vals.update({
                'custom_rate': True,
                'tax_today': rate,
            })
        
        wizard = self.env['account.payment.register'].with_context(**wizard_context).create(wizard_vals)
        return wizard._create_payments()

    def test_01_partial_payment_local_currency_invoice(self):
        """
        Test: Factura en moneda local con pago parcial
        - Factura: 15,000 (tasa 50 = 300 USD)
        - Pago 1: 5,000 (1/3)
        - Verificar: amount_residual = 10,000, estado = partial
        """
        rate = 50.0
        invoice_amount = 15000.0
        payment_amount = 5000.0
        
        # Crear factura
        invoice = self._create_invoice(invoice_amount, rate=rate)
        
        # Verificar valores iniciales
        self.assertEqual(invoice.amount_total, invoice_amount)
        self.assertEqual(invoice.amount_residual, invoice_amount)
        
        receivable_line = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        self.assertTrue(receivable_line)
        
        # Verificar debit_usd calculado correctamente
        expected_debit_usd = invoice_amount / rate
        self.assertAlmostEqual(
            receivable_line.debit_usd, 
            expected_debit_usd, 
            places=2,
            msg=f"debit_usd debería ser {expected_debit_usd}, pero es {receivable_line.debit_usd}"
        )
        
        # Registrar pago parcial (1/3 del total)
        payment = self._register_payment(invoice, payment_amount, rate=rate)
        self.assertTrue(payment)
        
        # Invalidar caché y recargar
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        # Verificar amount_residual
        expected_residual = invoice_amount - payment_amount  # 10,000
        self.assertAlmostEqual(
            invoice.amount_residual, 
            expected_residual, 
            places=2,
            msg=f"amount_residual debería ser {expected_residual}, pero es {invoice.amount_residual}"
        )
        
        # Verificar payment_state
        self.assertEqual(
            invoice.payment_state, 
            'partial',
            msg=f"payment_state debería ser 'partial', pero es '{invoice.payment_state}'"
        )

    def test_02_multiple_partial_payments(self):
        """
        Test: Factura con múltiples pagos parciales
        - Factura: 30,000 (tasa 50 = 600 USD)
        - Pago 1: 10,000
        - Pago 2: 10,000
        - Pago 3: 10,000 (completa)
        """
        rate = 50.0
        invoice_amount = 30000.0
        payment_amount = 10000.0
        
        invoice = self._create_invoice(invoice_amount, rate=rate)
        
        # Pago 1: 1/3
        self._register_payment(invoice, payment_amount, rate=rate)
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        self.assertAlmostEqual(invoice.amount_residual, 20000.0, places=2)
        self.assertEqual(invoice.payment_state, 'partial')
        
        # Pago 2: 2/3
        self._register_payment(invoice, payment_amount, rate=rate)
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        self.assertAlmostEqual(invoice.amount_residual, 10000.0, places=2)
        self.assertEqual(invoice.payment_state, 'partial')
        
        # Pago 3: completo
        self._register_payment(invoice, payment_amount, rate=rate)
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        self.assertAlmostEqual(invoice.amount_residual, 0.0, places=2)
        self.assertIn(invoice.payment_state, ['paid', 'in_payment'])

    def test_03_partial_payment_usd_invoice(self):
        """
        Test: Factura en USD con pago parcial
        - Factura: 300 USD
        - Pago 1: 100 USD
        - Verificar: amount_residual = 200 USD
        """
        invoice_amount = 300.0
        payment_amount = 100.0
        
        # Crear factura en USD
        invoice = self._create_invoice(invoice_amount, currency=self.usd_currency)
        
        self.assertEqual(invoice.amount_total, invoice_amount)
        self.assertEqual(invoice.currency_id, self.usd_currency)
        
        # Registrar pago parcial
        self._register_payment(invoice, payment_amount)
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        # Verificar
        expected_residual = invoice_amount - payment_amount  # 200 USD
        self.assertAlmostEqual(
            invoice.amount_residual, 
            expected_residual, 
            places=2,
            msg=f"amount_residual debería ser {expected_residual} USD"
        )
        self.assertEqual(invoice.payment_state, 'partial')

    def test_04_partial_payment_different_rates(self):
        """
        Test: Factura y pagos con tasas diferentes
        - Factura: 15,000 @ tasa 50 (= 300 USD)
        - Pago 1: 5,000 @ tasa 55 (= 90.91 USD)
        - Verificar consistencia de amount_residual
        """
        invoice_rate = 50.0
        payment_rate = 55.0
        invoice_amount = 15000.0
        payment_amount = 5000.0
        
        invoice = self._create_invoice(invoice_amount, rate=invoice_rate)
        
        # Pago con tasa diferente
        self._register_payment(invoice, payment_amount, rate=payment_rate)
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        # El residual en moneda local debe ser exacto
        expected_residual = invoice_amount - payment_amount
        self.assertAlmostEqual(
            invoice.amount_residual, 
            expected_residual, 
            places=2,
            msg=f"amount_residual debería ser {expected_residual}"
        )
        
        # El estado debe ser partial
        self.assertEqual(invoice.payment_state, 'partial')

    def test_05_amount_usd_in_partial_reconcile(self):
        """
        Test: Verificar que amount_usd se calcula correctamente en account.partial.reconcile
        """
        rate = 50.0
        invoice_amount = 15000.0
        payment_amount = 5000.0
        
        invoice = self._create_invoice(invoice_amount, rate=rate)
        self._register_payment(invoice, payment_amount, rate=rate)
        
        # Buscar la reconciliación parcial
        receivable_line = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        
        partials = self.env['account.partial.reconcile'].search([
            '|',
            ('debit_move_id', '=', receivable_line.id),
            ('credit_move_id', '=', receivable_line.id),
        ])
        
        self.assertTrue(partials, "Debería existir al menos una reconciliación parcial")
        
        for partial in partials:
            # amount_usd NO debe ser igual a amount (eso indicaría tasa 1.0)
            if rate != 1.0:
                self.assertNotAlmostEqual(
                    partial.amount_usd,
                    partial.amount,
                    places=2,
                    msg="amount_usd no debería ser igual a amount cuando rate != 1.0"
                )
            
            # Verificar que amount_usd es razonable
            self.assertGreater(partial.amount_usd, 0, "amount_usd debe ser mayor que 0")

    def test_06_vendor_invoice_partial_payment(self):
        """
        Test: Factura de proveedor con pago parcial
        - Factura proveedor: 10,000 @ tasa 50
        - Pago 1: 3,000
        - Verificar: amount_residual = 7,000
        """
        rate = 50.0
        invoice_amount = 10000.0
        payment_amount = 3000.0
        
        invoice = self._create_invoice(invoice_amount, rate=rate, move_type='in_invoice')
        
        # Verificar línea de payable
        payable_line = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'liability_payable'
        )
        self.assertTrue(payable_line)
        
        # Verificar credit_usd
        expected_credit_usd = invoice_amount / rate
        self.assertAlmostEqual(
            payable_line.credit_usd,
            expected_credit_usd,
            places=2,
            msg=f"credit_usd debería ser {expected_credit_usd}"
        )
        
        # Registrar pago parcial
        self._register_payment(invoice, payment_amount, rate=rate)
        invoice.invalidate_recordset()
        invoice = invoice.browse(invoice.id)
        
        expected_residual = invoice_amount - payment_amount
        self.assertAlmostEqual(invoice.amount_residual, expected_residual, places=2)
        self.assertEqual(invoice.payment_state, 'partial')

    def test_07_debit_credit_usd_consistency(self):
        """
        Test: Verificar que debit_usd y credit_usd son consistentes con balance
        """
        rate = 50.0
        amount = 10000.0
        
        invoice = self._create_invoice(amount, rate=rate)
        
        for line in invoice.line_ids:
            if line.display_type in ('line_section', 'line_note'):
                continue
            
            # Si balance > 0, debe tener debit_usd > 0 y credit_usd = 0
            if line.balance > 0:
                self.assertGreater(line.debit_usd, 0, f"Línea con balance positivo debe tener debit_usd > 0")
                self.assertEqual(line.credit_usd, 0, f"Línea con balance positivo debe tener credit_usd = 0")
            # Si balance < 0, debe tener credit_usd > 0 y debit_usd = 0
            elif line.balance < 0:
                self.assertEqual(line.debit_usd, 0, f"Línea con balance negativo debe tener debit_usd = 0")
                self.assertGreater(line.credit_usd, 0, f"Línea con balance negativo debe tener credit_usd > 0")
