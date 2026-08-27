from datetime import timedelta

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestAccountDualCurrencyManualRate(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id
        cls.foreign_currency = cls.env.ref('base.USD')
        if cls.foreign_currency == cls.company_currency:
            cls.foreign_currency = cls.env.ref('base.EUR')
        cls.company.currency_id_dif = cls.foreign_currency
        cls.bank_journal = cls.company_data['default_bank_journal']
        cls.sales_journal = cls.company_data['default_sales_journal']
        cls.partner = cls.partner_a
        cls.product = cls.product_a
        method_line = cls.bank_journal.inbound_payment_method_line_ids[:1]
        if not method_line:
            method_line = cls.bank_journal.payment_method_line_ids[:1]
        cls.payment_method_line = method_line
        cls.env['res.currency.rate'].create({
            'currency_id': cls.foreign_currency.id,
            'company_id': cls.company.id,
            'name': fields.Date.today(),
            'rate': 0.5,
        })

    def test_invoice_payment_with_manual_rate(self):
        manual_invoice_rate = 36.5
        manual_payment_rate = 38.2
        invoice_date = fields.Date.today() - timedelta(days=5)
        payment_date = fields.Date.today() - timedelta(days=3)

        invoice = self.env['account.move'].with_context(default_move_type='out_invoice').create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': self.foreign_currency.id,
            'journal_id': self.sales_journal.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': 100.0,
                    'account_id': self.company_data['default_account_revenue'].id,
                })
            ],
        })

        rate_model = self.env['res.currency.rate']
        company_root = self.company.root_id or self.company
        invoice_rate_domain = [
            ('currency_id', '=', self.foreign_currency.id),
            ('company_id', '=', company_root.id),
            ('name', '=', invoice_date),
        ]
        self.assertFalse(rate_model.search(invoice_rate_domain, limit=1))

        invoice.write({
            'edit_trm': True,
            'tax_today': manual_invoice_rate,
        })

        created_invoice_rate = rate_model.search(invoice_rate_domain, limit=1)
        self.assertTrue(created_invoice_rate, "No se creó la tasa manual para la factura.")
        self.assertAlmostEqual(created_invoice_rate.inverse_company_rate, manual_invoice_rate, places=6)
        invoice.action_post()

        wizard_context = {
            'active_model': 'account.move',
            'active_ids': invoice.ids,
        }
        wizard = self.env['account.payment.register'].with_context(**wizard_context).create({
            'payment_date': payment_date,
            'journal_id': self.bank_journal.id,
            'custom_rate': True,
            'tax_today': manual_payment_rate,
            'payment_method_line_id': self.payment_method_line.id,
            'amount': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
        })

        payment_rate_domain = [
            ('currency_id', '=', self.foreign_currency.id),
            ('company_id', '=', company_root.id),
            ('name', '=', payment_date),
        ]
        self.assertFalse(rate_model.search(payment_rate_domain, limit=1))

        payments = wizard._create_payments()
        self.assertTrue(payments, "No se generó el pago.")

        for payment in payments:
            self.assertTrue(payment.custom_rate)
            self.assertAlmostEqual(payment.tax_today, manual_payment_rate, places=6)
            self.assertTrue(payment.move_id.edit_trm)
            self.assertAlmostEqual(payment.move_id.tax_today, manual_payment_rate, places=6)

        created_payment_rate = rate_model.search(payment_rate_domain, limit=1)
        self.assertTrue(created_payment_rate, "No se creó la tasa manual para el pago.")
        self.assertAlmostEqual(created_payment_rate.inverse_company_rate, manual_payment_rate, places=6)

    def _create_invoice(self, amount_usd, invoice_date, manual_rate=None):
        if manual_rate:
            self.env['res.currency.rate'].create({
                'currency_id': self.foreign_currency.id,
                'company_id': self.company.id,
                'name': invoice_date,
                'inverse_company_rate': manual_rate,
                'rate': 1 / manual_rate,
            })
        else:
            self.env['res.currency.rate'].create({
                'currency_id': self.foreign_currency.id,
                'company_id': self.company.id,
                'name': invoice_date,
                'rate': 1 / 50,
                'inverse_company_rate': 50,
            })

        invoice = self.env['account.move'].with_context(default_move_type='out_invoice').create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': self.foreign_currency.id,
            'journal_id': self.sales_journal.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': amount_usd,
                    'account_id': self.company_data['default_account_revenue'].id,
                })
            ],
        })

        if manual_rate:
            invoice.write({'edit_trm': True, 'tax_today': manual_rate})

        invoice.action_post()
        return invoice

    def _create_payment(self, amount_company_currency, payment_date, manual_rate=None):
        payment_vals = {
            'payment_type': 'inbound',
            'payment_method_line_id': self.payment_method_line.id,
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': amount_company_currency,
            'currency_id': self.company_currency.id,
            'journal_id': self.bank_journal.id,
            'date': payment_date,
        }
        if manual_rate:
            payment_vals.update({'custom_rate': True, 'tax_today': manual_rate})

        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        return payment

    def _reconcile_receivable(self, invoice, payment):
        receivable_account = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable').account_id
        lines = (invoice.line_ids + payment.move_id.line_ids).filtered(lambda l: l.account_id == receivable_account and not l.reconciled)
        lines.reconcile()
        return lines

    def test_manual_payment_system_invoice_reconciliation(self):
        invoice_date = fields.Date.today() - timedelta(days=20)
        payment_date = fields.Date.today() - timedelta(days=18)
        invoice_amount_usd = 600.71
        payment_amount_usd = 600.54
        manual_payment_rate = 55.0

        invoice = self._create_invoice(invoice_amount_usd, invoice_date)
        payment = self._create_payment(payment_amount_usd * manual_payment_rate, payment_date, manual_rate=manual_payment_rate)

        self._reconcile_receivable(invoice, payment)
        invoice.refresh()
        payment.move_id.refresh()

        receivable_account = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable').account_id
        payment_line = payment.move_id.line_ids.filtered(lambda l: l.account_id == receivable_account)[:1]
        invoice_line = invoice.line_ids.filtered(lambda l: l.account_id == receivable_account)[:1]

        self.assertAlmostEqual(payment_line.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(payment_line.amount_residual_usd, 0.0, places=2)
        expected_invoice_residual_usd = invoice_amount_usd - payment_amount_usd
        self.assertAlmostEqual(invoice.amount_residual_currency, expected_invoice_residual_usd, places=2)
        self.assertAlmostEqual(invoice_line.amount_residual_usd, expected_invoice_residual_usd, places=2)

        partial = payment_line.matched_credit_ids[:1]
        self.assertTrue(partial)
        self.assertAlmostEqual(partial.amount_usd, payment_amount_usd, places=2)

    def test_system_payment_manual_invoice_reconciliation(self):
        invoice_date = fields.Date.today() - timedelta(days=15)
        payment_date = fields.Date.today() - timedelta(days=14)
        invoice_amount_usd = 400.0
        manual_invoice_rate = 52.0
        system_rate = 50.0

        invoice = self._create_invoice(invoice_amount_usd, invoice_date, manual_rate=manual_invoice_rate)
        payment = self._create_payment(invoice_amount_usd * system_rate, payment_date)

        self._reconcile_receivable(invoice, payment)
        invoice.refresh()
        payment.move_id.refresh()

        receivable_account = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable').account_id
        payment_line = payment.move_id.line_ids.filtered(lambda l: l.account_id == receivable_account)[:1]
        invoice_line = invoice.line_ids.filtered(lambda l: l.account_id == receivable_account)[:1]

        self.assertAlmostEqual(payment_line.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(payment_line.amount_residual_usd, 0.0, places=2)
        self.assertAlmostEqual(invoice.amount_residual_currency, 0.0, places=2)
        self.assertAlmostEqual(invoice_line.amount_residual_usd, 0.0, places=2)

    def test_manual_payment_manual_invoice_reconciliation(self):
        invoice_date = fields.Date.today() - timedelta(days=12)
        payment_date = fields.Date.today() - timedelta(days=10)
        invoice_amount_usd = 250.0
        manual_invoice_rate = 51.5
        manual_payment_rate = 54.0

        invoice = self._create_invoice(invoice_amount_usd, invoice_date, manual_rate=manual_invoice_rate)
        payment = self._create_payment(invoice_amount_usd * manual_payment_rate, payment_date, manual_rate=manual_payment_rate)

        self._reconcile_receivable(invoice, payment)
        invoice.refresh()
        payment.move_id.refresh()

        receivable_account = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable').account_id
        payment_line = payment.move_id.line_ids.filtered(lambda l: l.account_id == receivable_account)[:1]
        invoice_line = invoice.line_ids.filtered(lambda l: l.account_id == receivable_account)[:1]

        self.assertAlmostEqual(payment_line.amount_residual, 0.0, places=2)
        self.assertAlmostEqual(payment_line.amount_residual_usd, 0.0, places=2)
        self.assertAlmostEqual(invoice.amount_residual_currency, 0.0, places=2)
        self.assertAlmostEqual(invoice_line.amount_residual_usd, 0.0, places=2)

        partial = payment_line.matched_credit_ids[:1]
        self.assertTrue(partial)
        self.assertAlmostEqual(partial.amount_usd, invoice_amount_usd, places=2)
