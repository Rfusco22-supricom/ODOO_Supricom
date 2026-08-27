from odoo import fields
from odoo.tests.common import TransactionCase


class TestBankIntegration(TransactionCase):

    def setUp(self):
        super(TestBankIntegration, self).setUp()
        self.journal = self.env['account.journal'].create({
            'name': 'Banco Mercantil VE',
            'code': 'BMVE',
            'type': 'bank',
        })
        self.account = self.env['bank.integration.account'].create({
            'name': 'Cuenta Mercantil Test Integración',
            'journal_id': self.journal.id,
            'bank_type': 'mercantil',
            'environment': 'sandbox',
            'client_id': '335c75bf562497ca4a5877c304e00792',
            'secret_key': 'c1f041b4d9f2b09a5e27ce4e6f51260a',
            'merchant_id': '201999999',
            'account_number': '01050000000000000000',
            'phone_number': '04141234567',
            'customer_id': 'J123456789',
        })

    def test_transaction_buffer_creation_and_reconciliation(self):
        """Prueba la creación de líneas de transacción y su conciliación al confirmar un pago."""
        trx_line = self.env['bank.transaction.line'].create({
            'integration_account_id': self.account.id,
            'journal_id': self.journal.id,
            'trx_date': fields.Date.context_today(self),
            'payment_reference': 'TRX123456',
            'amount': 150.00,
            'currency_id': self.env.company.currency_id.id,
            'payment_type': 'transfer',
            'state': 'pending',
        })
        self.assertEqual(trx_line.state, 'pending')

        # Registrar un pago y vincular la línea
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'journal_id': self.journal.id,
            'amount': 150.00,
            'date': fields.Date.context_today(self),
            'ref': 'TRX123456',
            'bank_transaction_line_id': trx_line.id,
        })
        self.assertEqual(payment.bank_transaction_line_id, trx_line)

        # Confirmar el pago y verificar que la línea cambie a conciliada
        payment.action_post()
        self.assertEqual(payment.state, 'posted')
        self.assertEqual(trx_line.state, 'reconciled')
        self.assertEqual(trx_line.payment_id, payment)

    def test_cron_execution_smoke(self):
        """Smoke test de la ejecución del cron diario sin lanzar errores."""
        try:
            self.env['bank.integration.account'].cron_fetch_and_reconcile_daily()
        except Exception as e:
            self.fail(f"El cron de integración bancaria falló con la excepción: {e}")
