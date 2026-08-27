# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.payment_sepa_direct_debit.tests.common import SepaDirectDebitCommon


@tagged('post_install', '-at_install')
class TestSepaDirectDebit(SepaDirectDebitCommon):

    # TODO: Should only test that processing the tx confirms it.
    def test_transactions_are_confirmed_as_soon_as_mandate_is_valid(self):
        token = self._create_token(provider_ref=self.mandate.name, sdd_mandate_id=self.mandate.id)
        tx = self._create_transaction(flow='token', token_id=token.id)

        tx._send_payment_request()
        self.assertEqual(tx.state, 'done', "SEPA transactions should be immediately confirmed.")

    def test_send_payment_request_succeeds_for_active_mandates(self):
        """Test that token payment requests are accepted for txs with an active mandate."""
        token = self._create_token(provider_ref=self.mandate.name, sdd_mandate_id=self.mandate.id)
        tx = self._create_transaction(flow='token', token_id=token.id)

        self._assert_does_not_raise(UserError, tx._send_payment_request)

    def test_send_payment_request_succeeds_for_mandates_ending_in_the_future(self):
        """Test that token payment requests are accepted for txs with a mandate ending in the
        future."""
        self.mandate.start_date = fields.Date.today() - timedelta(days=10)
        self.mandate.end_date = fields.Date.today() + timedelta(days=10)
        token = self._create_token(provider_ref=self.mandate.name, sdd_mandate_id=self.mandate.id)
        tx = self._create_transaction(flow='token', token_id=token.id)

        self._assert_does_not_raise(UserError, tx._send_payment_request)

    @freeze_time('2020-1-1 10:00:00')
    def test_send_payment_request_succeeds_for_mandates_ending_today(self):
        """Test that token payment requests are accepted for txs with a mandate ending today."""
        self.mandate.start_date = fields.Date.today() - timedelta(days=10)
        self.mandate.end_date = fields.Date.today()
        token = self._create_token(provider_ref=self.mandate.name, sdd_mandate_id=self.mandate.id)
        tx = self._create_transaction(flow='token', token_id=token.id)

        self._assert_does_not_raise(UserError, tx._send_payment_request)

    def test_send_payment_request_fails_for_inactive_mandates(self):
        """Test that token payment requests are rejected for txs with an inactive mandate."""
        self.mandate.state = 'revoked'
        token = self._create_token(provider_ref=self.mandate.name, sdd_mandate_id=self.mandate.id)
        tx = self._create_transaction('token', token_id=token.id)

        with self.assertRaises(UserError):
            tx._send_payment_request()

    def test_send_payment_request_fails_for_expired_mandates(self):
        """Test that token payment requests are rejected for txs with an expired mandate."""
        self.mandate.start_date = fields.Date.today() - timedelta(days=10)
        self.mandate.end_date = fields.Date.today() - timedelta(days=10)
        token = self._create_token(provider_ref=self.mandate.name, sdd_mandate_id=self.mandate.id)
        tx = self._create_transaction('token', token_id=token.id)

        with self.assertRaises(UserError):
            tx._send_payment_request()

    def test_bank_statement_confirms_transaction_and_mandate(self):
        tx = self._create_transaction(flow='direct', state='pending', mandate_id=self.mandate.id)
        AccountBankStatementLine = self.env['account.bank.statement.line']
        AccountBankStatementLine.create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'partner_id': self.mandate.partner_id.id,
            'amount_currency': tx.amount,
            'foreign_currency_id': tx.currency_id.id,
            'payment_ref': tx.reference,
            'account_number': self.partner_bank_number
        })
        AccountBankStatementLine._cron_confirm_sepa_transactions()
        self.assertEqual(tx.state, 'done')

    def test_bank_statement_confirms_transaction_and_mandate_based_on_partner_name(self):
        tx = self._create_transaction(flow='direct', state='pending', mandate_id=self.mandate.id)
        AccountBankStatementLine = self.env['account.bank.statement.line']
        AccountBankStatementLine.create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'partner_name': self.mandate.partner_id.name,
            'amount_currency': tx.amount,
            'foreign_currency_id': tx.currency_id.id,
            'payment_ref': tx.reference,
            'account_number': self.partner_bank_number
        })
        AccountBankStatementLine._cron_confirm_sepa_transactions()
        self.assertEqual(tx.state, 'done')

    def test_confirming_transaction_creates_token(self):
        tx = self._create_transaction(flow='direct', state='pending', mandate_id=self.mandate.id)
        tx._set_done()
        token = self.env['payment.token'].search([('sdd_mandate_id', '=', self.mandate.id)])
        self.assertTrue(token)
        self.assertTrue(token.active)
        self.assertEqual(tx.token_id, token)
        self.assertEqual(self.mandate.state, 'active')

    def test_revoking_mandate_archives_token(self):
        tx = self._create_transaction(flow='direct', state='pending', mandate_id=self.mandate.id)
        tx._set_done()
        token = self.env['payment.token'].search([('sdd_mandate_id', '=', self.mandate.id)])
        self.mandate.with_user(self.invoicing_user).action_revoke_mandate()
        self.assertFalse(token.active)

    def test_creating_batch_payment_generates_export_file(self):
        """ Test the XML generation when validating a batch payment. """
        sdd_provider_method_line = self.company_data['default_journal_bank'] \
            .inbound_payment_method_line_ids.filtered(lambda l: l.code == 'sepa_direct_debit')
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_id': self.partner.id,
            'amount': 100.0,
            'journal_id': self.company_data['default_journal_bank'].id,
            'payment_method_line_id': sdd_provider_method_line.id,
        })
        payment.action_post()

        batch_payment = self.env['account.batch.payment'].create(
            {
                'journal_id': payment.journal_id.id,
                'payment_method_id': payment.payment_method_id.id,
                'payment_ids': [
                    (Command.set(payment.ids))
                ],
            }
        )
        batch_payment.validate_batch_button()

        self.assertTrue(batch_payment.export_file)
