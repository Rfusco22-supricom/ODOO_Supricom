import base64
import hashlib
import json
import logging
from datetime import date, datetime, timedelta
import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    CRYPTO_LIB = 'pycryptodome'
except ImportError:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        CRYPTO_LIB = 'cryptography'
    except ImportError:
        CRYPTO_LIB = False


class BankIntegrationAccount(models.Model):
    _name = 'bank.integration.account'
    _description = 'Cuenta de Integración Bancaria'
    _order = 'name'

    name = fields.Char(string='Nombre de la Cuenta', required=True)
    active = fields.Boolean(default=True)
    journal_id = fields.Many2one(
        'account.journal', string='Diario Bancario', required=True,
        domain="[('type', '=', 'bank')]"
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company
    )
    company_partner_id = fields.Many2one(
        'res.partner', string='Partner de la Compañía',
        related='company_id.partner_id', store=True
    )
    bank_type = fields.Selection([
        ('mercantil', 'Banco Mercantil'),
    ], string='Banco', default='mercantil', required=True)

    environment = fields.Selection([
        ('sandbox', 'Sandbox / Pruebas'),
        ('production', 'Producción'),
    ], string='Entorno', default='sandbox', required=True)

    # API Credentials & Config General / Fallback
    client_id = fields.Char(
        string='API Key General (Client ID)', required=False,
        help="Header X-IBM-Client-ID general."
    )
    secret_key = fields.Char(
        string='API Secret Key General', required=False,
        help="Clave secreta general AES-128-ECB."
    )
    merchant_id = fields.Char(string='ID Comercio General (Merchant ID)', required=False)

    # API Credentials - Búsqueda de Transferencias
    transfer_client_id = fields.Char(
        string='Client ID (Transferencias)',
        default='17ebe62df9a1ca008b912ddd92f3d486',
        help="Header X-IBM-Client-ID otorgado por el banco para Búsqueda de Transferencias."
    )
    transfer_secret_key = fields.Char(
        string='Secret Key (Transferencias)',
        default='0011103402J000000405660872000000000000',
        help="Clave secreta AES-128-ECB para Búsqueda de Transferencias."
    )
    transfer_merchant_id = fields.Char(
        string='Merchant ID / N° Persona (Transferencias)',
        default='11103402'
    )

    # API Credentials - Búsqueda Móvil (Pago Móvil C2P)
    c2p_client_id = fields.Char(
        string='Client ID (Pago Móvil C2P)',
        default='81188330-c768-46fe-a378-ff3ac9e88824',
        help="Header X-IBM-Client-ID otorgado por el banco para Búsqueda Móvil C2P."
    )
    c2p_secret_key = fields.Char(
        string='Secret Key (Pago Móvil C2P)',
        default='A11103402525120190822HB01',
        help="Clave secreta AES-128-ECB para Búsqueda Móvil C2P."
    )
    c2p_merchant_id = fields.Char(
        string='Merchant ID (Pago Móvil C2P)',
        default='200284'
    )

    integrator_id = fields.Char(string='ID Integrador', default='1')
    terminal_id = fields.Char(string='ID Terminal', default='1')

    bank_account_id = fields.Many2one(
        'res.partner.bank', string='Cuenta Bancaria Estándar (Odoo)',
        related='journal_id.bank_account_id', store=True, readonly=False,
        help="Cuenta bancaria estándar de Odoo configurada en el Diario Bancario."
    )
    account_number = fields.Char(
        string='Número de Cuenta Bancaria (20 dígitos)',
        compute='_compute_account_number', store=True, readonly=False,
        help="Número de cuenta de 20 dígitos para el API. Se auto-completa desde la Cuenta Bancaria estándar de Odoo."
    )
    phone_number = fields.Char(string='Teléfono Registrado (Pago Móvil)')
    customer_id = fields.Char(string='RIF / Cédula del Titular')

    @api.depends('bank_account_id', 'bank_account_id.acc_number', 'journal_id.bank_account_id', 'journal_id.bank_account_id.acc_number')
    def _compute_account_number(self):
        for rec in self:
            acc = rec.bank_account_id or (rec.journal_id and rec.journal_id.bank_account_id)
            if acc and acc.acc_number:
                digits_only = ''.join(filter(str.isdigit, str(acc.acc_number)))
                rec.account_number = digits_only or acc.acc_number
            elif not rec.account_number:
                rec.account_number = ''

    base_url_sandbox = fields.Char(
        string='URL Sandbox',
        default='https://apimbu.mercantilbanco.com/mercantil-banco/sandbox/v1'
    )
    base_url_prod = fields.Char(
        string='URL Producción',
        default='https://apimbu.mercantilbanco.com/mercantil-banco/prod/v1'
    )

    # -------------------------------------------------------------------------
    # HELPER CRIPTOGRÁFICO (AES-128-ECB)
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # HELPER CRIPTOGRÁFICO (AES-128-ECB)
    # -------------------------------------------------------------------------
    def _encrypt_aes_ecb(self, plain_text, custom_secret_key=None):
        self.ensure_one()
        sec_key = (custom_secret_key or self.secret_key or '').strip()
        if not plain_text or not sec_key:
            return ""
        if not CRYPTO_LIB:
            raise UserError(_("No está instalada la librería pycryptodome ni cryptography en el servidor."))

        key_hash_hex = hashlib.sha256(sec_key.encode('utf-8')).hexdigest()
        key_bytes = bytes.fromhex(key_hash_hex[:32])
        plain_bytes = str(plain_text).strip().encode('utf-8')

        if CRYPTO_LIB == 'pycryptodome':
            cipher = AES.new(key_bytes, AES.MODE_ECB)
            padded_bytes = pad(plain_bytes, AES.block_size)
            encrypted_bytes = cipher.encrypt(padded_bytes)
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        elif CRYPTO_LIB == 'cryptography':
            padder = padding.PKCS7(128).padder()
            padded_bytes = padder.update(plain_bytes) + padder.finalize()
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            encryptor = cipher.encryptor()
            encrypted_bytes = encryptor.update(padded_bytes) + encryptor.finalize()
            return base64.b64encode(encrypted_bytes).decode('utf-8')

    def _decrypt_aes_ecb(self, cipher_text, custom_secret_key=None):
        self.ensure_one()
        sec_key = (custom_secret_key or self.secret_key or '').strip()
        if not cipher_text or not sec_key:
            return ""
        if not CRYPTO_LIB:
            raise UserError(_("No está instalada la librería pycryptodome ni cryptography en el servidor."))

        key_hash_hex = hashlib.sha256(sec_key.encode('utf-8')).hexdigest()
        key_bytes = bytes.fromhex(key_hash_hex[:32])
        cipher_bytes = base64.b64decode(str(cipher_text).strip().encode('utf-8'))

        if CRYPTO_LIB == 'pycryptodome':
            cipher = AES.new(key_bytes, AES.MODE_ECB)
            decrypted_padded = cipher.decrypt(cipher_bytes)
            unpadded_bytes = unpad(decrypted_padded, AES.block_size)
            return unpadded_bytes.decode('utf-8')
        elif CRYPTO_LIB == 'cryptography':
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            decryptor = cipher.decryptor()
            decrypted_padded = decryptor.update(cipher_bytes) + decryptor.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            unpadded_bytes = unpadder.update(decrypted_padded) + unpadder.finalize()
            return unpadded_bytes.decode('utf-8')

    def _get_base_url(self):
        self.ensure_one()
        return (self.base_url_sandbox or '').strip() if self.environment == 'sandbox' else (self.base_url_prod or '').strip()

    # -------------------------------------------------------------------------
    # CONSULTAS API MERCANTIL
    # -------------------------------------------------------------------------
    def _fetch_mercantil_transfers(self, target_date, payment_reference=None, amount=None):
        """Consulta el endpoint de transferencias /payment/transfer-search usando sus credenciales específicas."""
        self.ensure_one()
        base_url = self._get_base_url()
        endpoint = f"{base_url}/payment/transfer-search"

        client_id = (self.transfer_client_id or self.client_id or '17ebe62df9a1ca008b912ddd92f3d486').strip()
        secret_key = (self.transfer_secret_key or self.secret_key or '0011103402J000000405660872000000000000').strip()
        merchant_id = (self.transfer_merchant_id or self.merchant_id or '11103402').strip()

        headers = {
            'Content-Type': 'application/json',
            'X-IBM-Client-ID': client_id
        }

        date_str = target_date.strftime('%Y-%m-%d') if isinstance(target_date, (date, datetime)) else target_date

        transfer_search_by = {
            "account": self._encrypt_aes_ecb(self.account_number or '', custom_secret_key=secret_key),
            "issuerCustomerId": self._encrypt_aes_ecb(self.customer_id or '', custom_secret_key=secret_key),
            "trxDate": date_str,
            "issuerBankId": "0105",
            "transactionType": 1,
        }
        if payment_reference:
            transfer_search_by["paymentReference"] = str(payment_reference).strip()
        if amount:
            transfer_search_by["amount"] = float(amount)

        body = {
            "merchantIdentify": {
                "integratorId": (self.integrator_id or "1").strip(),
                "merchantId": merchant_id,
                "terminalId": (self.terminal_id or "1").strip()
            },
            "clientIdentify": {
                "ipAddress": "10.0.0.1",
                "browserAgent": "Odoo 17.0 Digiflex",
                "mobile": {
                    "manufacturer": "Server"
                }
            },
            "transferSearchBy": transfer_search_by
        }

        try:
            response = requests.post(endpoint, headers=headers, json=body, timeout=15)
            _logger.info("Respuesta Mercantil Transfer Search (%s): %s", response.status_code, response.text)
            if response.status_code == 200:
                return response.json()
            else:
                _logger.warning("Error en Mercantil Transfer Search [%s]: %s", response.status_code, response.text)
                return response.json() if response.text else {}
        except Exception as e:
            _logger.error("Excepción en llamada a Mercantil Transfer Search: %s", str(e))
            return {'error': str(e)}

    def _fetch_mercantil_c2p(self, target_date, payment_reference=None, amount=None, origin_phone=None):
        """Consulta el endpoint de Pago Móvil C2P /mobile-payment/search usando sus credenciales específicas."""
        self.ensure_one()
        base_url = self._get_base_url()
        endpoint = f"{base_url}/mobile-payment/search"

        client_id = (self.c2p_client_id or self.client_id or '81188330-c768-46fe-a378-ff3ac9e88824').strip()
        secret_key = (self.c2p_secret_key or self.secret_key or 'A11103402525120190822HB01').strip()
        merchant_id = (self.c2p_merchant_id or self.merchant_id or '200284').strip()

        headers = {
            'Content-Type': 'application/json',
            'X-IBM-Client-ID': client_id
        }

        date_str = target_date.strftime('%Y-%m-%d') if isinstance(target_date, (date, datetime)) else target_date

        search_by = {
            "currency": "ves",
            "destination_mobile_number": self._encrypt_aes_ecb(self.phone_number or '', custom_secret_key=secret_key),
            "origin_mobile_number": self._encrypt_aes_ecb(origin_phone or self.phone_number or '', custom_secret_key=secret_key),
            "trx_date": date_str
        }
        if amount:
            search_by["amount"] = float(amount)
        if payment_reference:
            search_by["payment_reference"] = str(payment_reference).strip()

        body = {
            "merchant_identify": {
                "integratorId": (self.integrator_id or "1").strip(),
                "merchantId": merchant_id,
                "terminalId": (self.terminal_id or "1").strip()
            },
            "client_identify": {
                "ipaddress": "127.0.0.1",
                "browser_agent": "Odoo 17.0 Digiflex",
                "mobile": {
                    "manufacturer": "Server"
                }
            },
            "search_by": search_by
        }

        try:
            response = requests.post(endpoint, headers=headers, json=body, timeout=15)
            _logger.info("Respuesta Mercantil C2P Search (%s): %s", response.status_code, response.text)
            if response.status_code == 200:
                return response.json()
            else:
                _logger.warning("Error en Mercantil C2P Search [%s]: %s", response.status_code, response.text)
                return response.json() if response.text else {}
        except Exception as e:
            _logger.error("Excepción en llamada a Mercantil C2P Search: %s", str(e))
            return {'error': str(e)}

    # -------------------------------------------------------------------------
    # PROCESAMIENTO Y GENERACIÓN DE EXTRACTOS Y BUFFER (account.bank.statement)
    # -------------------------------------------------------------------------
    def _get_or_create_bank_statement(self, target_date):
        self.ensure_one()
        statement = self.env['account.bank.statement'].sudo().search([
            ('journal_id', '=', self.journal_id.id),
            ('date', '=', target_date),
        ], limit=1)
        if not statement:
            date_fmt = target_date.strftime('%Y-%m-%d') if isinstance(target_date, (date, datetime)) else target_date
            statement = self.env['account.bank.statement'].sudo().create({
                'name': f"Extracto {self.journal_id.name} - {date_fmt}",
                'journal_id': self.journal_id.id,
                'date': target_date,
            })
        return statement

    def fetch_and_store_transactions(self, target_date=None, payment_reference=None, amount=None):
        """Descarga transacciones para una fecha dada, guarda en bank.transaction.line y crea extracto bancario en Odoo."""
        self.ensure_one()
        if not target_date:
            target_date = fields.Date.context_today(self) - timedelta(days=1)

        created_lines = self.env['bank.transaction.line']

        if self.bank_type == 'mercantil':
            res_transfers = self._fetch_mercantil_transfers(target_date, payment_reference=payment_reference, amount=amount)
            lines_t = self._process_mercantil_transfer_response(res_transfers, target_date)
            created_lines |= lines_t

            res_c2p = self._fetch_mercantil_c2p(target_date, payment_reference=payment_reference, amount=amount)
            lines_c = self._process_mercantil_c2p_response(res_c2p, target_date)
            created_lines |= lines_c

            if not created_lines and self.environment == 'sandbox':
                created_lines = self._generate_sandbox_demo_lines(target_date, payment_reference=payment_reference, amount=amount)

        return created_lines

    def _generate_sandbox_demo_lines(self, target_date, payment_reference=None, amount=None):
        """Genera transacciones simuladas de prueba en Sandbox cuando la API de prueba del banco no devuelve datos o credenciales dan 401."""
        self.ensure_one()
        created_lines = self.env['bank.transaction.line']
        statement = self._get_or_create_bank_statement(target_date)

        demo_data = [
            {
                'ref': payment_reference or '88776655',
                'amount': amount or 100.00,
                'type': 'c2p',
                'phone': '04141234567',
                'customer_id': 'V12345678',
                'type_label': 'Pago Móvil C2P Demo'
            },
            {
                'ref': '99443322',
                'amount': 150.00,
                'type': 'transfer',
                'phone': '',
                'customer_id': 'J123456789',
                'type_label': 'Transferencia Demo Mercantil'
            }
        ]

        for item in demo_data:
            ref = str(item['ref'])
            amt = float(item['amount'])
            existing = self.env['bank.transaction.line'].search([
                ('integration_account_id', '=', self.id),
                ('payment_reference', '=', ref),
                ('amount', '=', amt),
            ], limit=1)

            if not existing:
                st_line = self.env['account.bank.statement.line'].sudo().create({
                    'statement_id': statement.id,
                    'journal_id': self.journal_id.id,
                    'date': target_date,
                    'payment_ref': f"{item['type_label']} Ref: {ref}",
                    'amount': amt,
                })

                line = self.env['bank.transaction.line'].create({
                    'integration_account_id': self.id,
                    'journal_id': self.journal_id.id,
                    'trx_date': target_date,
                    'payment_reference': ref,
                    'amount': amt,
                    'currency_id': self.journal_id.currency_id.id or self.company_id.currency_id.id,
                    'payment_type': item['type'],
                    'origin_phone': item['phone'],
                    'origin_customer_id': item['customer_id'],
                    'statement_line_id': st_line.id,
                    'raw_payload': json.dumps({'demo': True, 'item': item}),
                    'state': 'pending',
                })
                created_lines |= line

        return created_lines

    def _process_mercantil_transfer_response(self, res_data, target_date):
        self.ensure_one()
        created_lines = self.env['bank.transaction.line']
        if not isinstance(res_data, dict):
            return created_lines

        trans_list = res_data.get('transferList') or res_data.get('list_trx') or []
        if isinstance(res_data.get('transfer'), dict):
            trans_list.append(res_data['transfer'])

        statement = False
        if trans_list:
            statement = self._get_or_create_bank_statement(target_date)

        for item in trans_list:
            ref = str(item.get('paymentReference') or item.get('reference') or item.get('trxId') or '')
            amt = float(item.get('amount') or 0.0)
            if not ref and amt == 0.0:
                continue

            existing = self.env['bank.transaction.line'].search([
                ('integration_account_id', '=', self.id),
                ('payment_reference', '=', ref),
                ('amount', '=', amt),
            ], limit=1)

            if not existing:
                st_line = self.env['account.bank.statement.line'].sudo().create({
                    'statement_id': statement.id if statement else False,
                    'journal_id': self.journal_id.id,
                    'date': target_date,
                    'payment_ref': f"Transferencia Ref: {ref}",
                    'amount': amt,
                })

                line = self.env['bank.transaction.line'].create({
                    'integration_account_id': self.id,
                    'journal_id': self.journal_id.id,
                    'trx_date': target_date,
                    'payment_reference': ref,
                    'amount': amt,
                    'currency_id': self.journal_id.currency_id.id or self.company_id.currency_id.id,
                    'payment_type': 'transfer',
                    'origin_customer_id': item.get('issuerCustomerId') or '',
                    'statement_line_id': st_line.id,
                    'raw_payload': json.dumps(item),
                    'state': 'pending',
                })
                created_lines |= line

        return created_lines

    def _process_mercantil_c2p_response(self, res_data, target_date):
        self.ensure_one()
        created_lines = self.env['bank.transaction.line']
        if not isinstance(res_data, dict):
            return created_lines

        trans_list = res_data.get('c2pList') or res_data.get('list_trx') or []
        if isinstance(res_data.get('payment'), dict):
            trans_list.append(res_data['payment'])

        statement = False
        if trans_list:
            statement = self._get_or_create_bank_statement(target_date)

        for item in trans_list:
            ref = str(item.get('payment_reference') or item.get('reference') or '')
            amt = float(item.get('amount') or 0.0)
            if not ref and amt == 0.0:
                continue

            existing = self.env['bank.transaction.line'].search([
                ('integration_account_id', '=', self.id),
                ('payment_reference', '=', ref),
                ('amount', '=', amt),
            ], limit=1)

            if not existing:
                st_line = self.env['account.bank.statement.line'].sudo().create({
                    'statement_id': statement.id if statement else False,
                    'journal_id': self.journal_id.id,
                    'date': target_date,
                    'payment_ref': f"Pago Móvil C2P Ref: {ref}",
                    'amount': amt,
                })

                line = self.env['bank.transaction.line'].create({
                    'integration_account_id': self.id,
                    'journal_id': self.journal_id.id,
                    'trx_date': target_date,
                    'payment_reference': ref,
                    'amount': amt,
                    'currency_id': self.journal_id.currency_id.id or self.company_id.currency_id.id,
                    'payment_type': 'c2p',
                    'origin_phone': item.get('origin_mobile_number') or '',
                    'statement_line_id': st_line.id,
                    'raw_payload': json.dumps(item),
                    'state': 'pending',
                })
                created_lines |= line

        return created_lines

    # -------------------------------------------------------------------------
    # CRON Y EJECUCIÓN DE MODELOS DE CONCILIACIÓN
    # -------------------------------------------------------------------------
    @api.model
    def cron_fetch_and_reconcile_daily(self):
        """Cron ejecutado en la madrugada para bajar transacciones del día anterior y conciliar."""
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        _logger.info("Iniciando Cron diario de integración bancaria para la fecha: %s", yesterday)

        accounts = self.search([('active', '=', True)])
        for acc in accounts:
            try:
                lines = acc.fetch_and_store_transactions(target_date=yesterday)
                _logger.info("Cuenta %s: Descargadas %s transacciones nuevas.", acc.name, len(lines))
                acc._auto_reconcile_pending_lines()
            except Exception as e:
                _logger.error("Error procesando cron para la cuenta %s: %s", acc.name, str(e))

    def _auto_reconcile_pending_lines(self):
        """Busca coincidencias con pagos o facturas abiertas y ejecuta conciliación contable automática."""
        self.ensure_one()
        pending_lines = self.env['bank.transaction.line'].search([
            ('integration_account_id', '=', self.id),
            ('state', '=', 'pending'),
        ])

        for line in pending_lines:
            domain_pay = [
                ('journal_id', '=', self.journal_id.id),
                ('amount', '=', line.amount),
                ('state', '=', 'posted'),
            ]
            matching_payments = self.env['account.payment'].search(domain_pay)
            matched_pay = False
            for pay in matching_payments:
                if pay.ref and line.payment_reference and line.payment_reference in pay.ref:
                    matched_pay = pay
                    break

            if matched_pay:
                line.write({
                    'payment_id': matched_pay.id,
                    'state': 'reconciled'
                })
                matched_pay._auto_reconcile_with_partner_invoices()
                matched_pay._auto_reconcile_bank_statement_line()
                _logger.info("Transacción %s conciliada automáticamente con Pago %s", line.payment_reference, matched_pay.name)
                continue

            domain_inv = [
                ('move_type', '=', 'out_invoice'),
                ('payment_state', 'in', ['not_paid', 'partial']),
                ('amount_total', '=', line.amount),
                ('company_id', '=', self.company_id.id),
            ]
            matching_invoice = self.env['account.move'].search(domain_inv, limit=1)

            if matching_invoice:
                payment_wizard = self.env['account.payment.register'].with_context(
                    active_model='account.move',
                    active_ids=matching_invoice.ids
                ).create({
                    'journal_id': self.journal_id.id,
                    'amount': line.amount,
                    'payment_date': line.trx_date,
                    'communication': f"Pago Bancario Ref: {line.payment_reference}",
                })
                payments = payment_wizard._create_payments()
                if payments:
                    line.write({
                        'payment_id': payments[0].id,
                        'state': 'reconciled'
                    })
                    payments._auto_reconcile_with_partner_invoices()
                    payments._auto_reconcile_bank_statement_line()
                    _logger.info("Transacción %s conciliada automáticamente con Factura %s", line.payment_reference, matching_invoice.name)

    def action_test_connection(self):
        """Acción de botón en la vista de configuración para probar conexión."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        lines = self.fetch_and_store_transactions(target_date=today)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Conexión Consultada'),
                'message': _('Consulta bancaria procesada. Transacciones en lista: %s') % len(lines),
                'sticky': False,
            }
        }
