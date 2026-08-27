# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestPrintCheck(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref='ph'):
        super().setUpClass(chart_template_ref=chart_template_ref)

        cls.company_data['company'].account_check_printing_layout = 'l10n_ph_check_printing.action_print_check'

        bank_journal = cls.company_data['default_journal_bank']

        cls.payment_method_line_check = bank_journal.outbound_payment_method_line_ids \
            .filtered(lambda l: l.code == 'check_printing')

        cls.partner_a.write({
            'vat': '123-456-789-001',
            'branch_code': '001',
            'name': 'JMC Company',
            'street': "250 Amorsolo Street",
            'city': "Manila",
            'country_id': cls.env.ref('base.ph').id,
            'zip': "+900–1-096",
            'is_company': True,
        })

    def test_check_printing_only(self):
        """ Test that if the amount does not contain decimals,
            The amount in words on the check contains the keyword 'ONLY'
        """
        vendor_bill = self.init_invoice(
            move_type='in_invoice',
            partner=self.partner_a,
            amounts=[91490],
            post=True,
        )

        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=vendor_bill.ids, lang='en_US'
        ).create({
            'payment_method_line_id': self.payment_method_line_check.id,
        })._create_payments()

        self.assertEqual(payment.check_amount_in_words, 'Ninety-One Thousand Four Hundred Ninety ONLY')

    def test_check_printing_rounding(self):
        """ Test that the amount in words on the check is rounded to 2 decimals,
            And does not contain the keyword 'ONLY'
         """
        vendor_bill = self.init_invoice(
            move_type='in_invoice',
            partner=self.partner_a,
            amounts=[91490.15],
            post=True,
        )

        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=vendor_bill.ids, lang='en_US'
        ).create({
            'payment_method_line_id': self.payment_method_line_check.id,
        })._create_payments()

        self.assertEqual(payment.check_amount_in_words, 'Ninety-One Thousand Four Hundred Ninety and 15/100')

    def test_check_printing_rounding_two_decimals(self):
        """ Test that even with a different rounding factor,
            The amount in words on the check is still rounded to 2 decimals
        """
        self.env.ref('product.decimal_price').digits = 4
        self.env.company.currency_id.rounding = 0.0001

        vendor_bill = self.init_invoice(
            move_type='in_invoice',
            partner=self.partner_a,
            amounts=[91490.1579],
            post=True,
        )

        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=vendor_bill.ids, lang='en_US'
        ).create({
            'payment_method_line_id': self.payment_method_line_check.id,
        })._create_payments()

        self.assertEqual(payment.check_amount_in_words, 'Ninety-One Thousand Four Hundred Ninety and 16/100')
