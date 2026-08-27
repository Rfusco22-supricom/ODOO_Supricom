from odoo.tests.common import TransactionCase


class TestMercantilCrypto(TransactionCase):

    def setUp(self):
        super(TestMercantilCrypto, self).setUp()
        self.journal = self.env['account.journal'].create({
            'name': 'Banco Mercantil Test',
            'code': 'BMTEST',
            'type': 'bank',
        })
        self.account = self.env['bank.integration.account'].create({
            'name': 'Cuenta Mercantil Sandbox Test',
            'journal_id': self.journal.id,
            'bank_type': 'mercantil',
            'environment': 'sandbox',
            'client_id': '335c75bf562497ca4a5877c304e00792',
            'secret_key': 'c1f041b4d9f2b09a5e27ce4e6f51260a',
            'merchant_id': '201999999',
            'account_number': '01050000000000000000',
            'phone_number': '04141234567',
            'customer_id': 'V12345678',
        })

    def test_encrypt_decrypt_aes_ecb(self):
        """Prueba que el cifrado AES-128-ECB y posterior descifrado retorne el texto original."""
        original_text = "01050123456789012345"
        encrypted = self.account._encrypt_aes_ecb(original_text)
        self.assertTrue(encrypted, "El cifrado debe retornar una cadena Base64 no vacía.")
        self.assertNotEqual(original_text, encrypted)

        decrypted = self.account._decrypt_aes_ecb(encrypted)
        self.assertEqual(original_text, decrypted, "El texto descifrado debe coincidir exactamente con el original.")

    def test_empty_string_crypto(self):
        """Prueba comportamiento con cadenas vacías."""
        self.assertEqual(self.account._encrypt_aes_ecb(""), "")
        self.assertEqual(self.account._decrypt_aes_ecb(""), "")
