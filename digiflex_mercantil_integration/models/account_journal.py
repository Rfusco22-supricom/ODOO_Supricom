import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # Configuración API Directa en el Diario Bancario
    bank_integration_enabled = fields.Boolean(
        string='Habilitar Integración API Bancaria', default=False
    )
    bank_type = fields.Selection([
        ('mercantil', 'Banco Mercantil'),
    ], string='Banco API', default='mercantil')

    bank_environment = fields.Selection([
        ('sandbox', 'Sandbox / Pruebas'),
        ('production', 'Producción'),
    ], string='Entorno API', default='sandbox')

    bank_client_id = fields.Char(
        string='API Key General (Client ID)',
        help="Header X-IBM-Client-ID general."
    )
    bank_secret_key = fields.Char(
        string='API Secret Key General',
        help="Clave secreta general para cifrado AES-128-ECB."
    )
    bank_merchant_id = fields.Char(string='ID Comercio General (Merchant ID)')

    # Búsqueda de Transferencias
    bank_transfer_client_id = fields.Char(
        string='Client ID (Transferencias)',
        default='17ebe62df9a1ca008b912ddd92f3d486',
        help="Header X-IBM-Client-ID para Búsqueda de Transferencias."
    )
    bank_transfer_secret_key = fields.Char(
        string='Secret Key (Transferencias)',
        default='0011103402J000000405660872000000000000',
        help="Clave secreta para Búsqueda de Transferencias."
    )
    bank_transfer_merchant_id = fields.Char(
        string='Merchant ID / N° Persona (Transferencias)',
        default='11103402'
    )

    # Búsqueda Móvil (Pago Móvil C2P)
    bank_c2p_client_id = fields.Char(
        string='Client ID (Pago Móvil C2P)',
        default='81188330-c768-46fe-a378-ff3ac9e88824',
        help="Header X-IBM-Client-ID para Búsqueda Móvil C2P."
    )
    bank_c2p_secret_key = fields.Char(
        string='Secret Key (Pago Móvil C2P)',
        default='A11103402525120190822HB01',
        help="Clave secreta para Búsqueda Móvil C2P."
    )
    bank_c2p_merchant_id = fields.Char(
        string='Merchant ID (Pago Móvil C2P)',
        default='200284'
    )

    bank_integrator_id = fields.Char(string='ID Integrador', default='1')
    bank_terminal_id = fields.Char(string='ID Terminal', default='1')

    bank_account_number = fields.Char(
        string='Número de Cuenta Bancaria (20 dígitos)',
        compute='_compute_bank_account_number', store=True, readonly=False,
        help="Se auto-completa desde la Cuenta Bancaria estándar de Odoo (bank_account_id)."
    )
    bank_phone_number = fields.Char(string='Teléfono Afiliado (Pago Móvil)')
    bank_customer_id = fields.Char(string='RIF / Cédula del Titular')

    @api.depends('bank_account_id', 'bank_account_id.acc_number')
    def _compute_bank_account_number(self):
        for journal in self:
            if journal.bank_account_id and journal.bank_account_id.acc_number:
                digits_only = ''.join(filter(str.isdigit, str(journal.bank_account_id.acc_number)))
                journal.bank_account_number = digits_only or journal.bank_account_id.acc_number
            elif not journal.bank_account_number:
                journal.bank_account_number = ''

    bank_integration_account_ids = fields.One2many(
        'bank.integration.account', 'journal_id', string='Cuentas de Integración API'
    )
    bank_integration_account_id = fields.Many2one(
        'bank.integration.account', string='Cuenta de Integración Activa',
        compute='_compute_bank_integration_account_id', store=True
    )

    @api.depends('bank_integration_account_ids', 'bank_integration_enabled',
                 'bank_client_id', 'bank_secret_key', 'bank_merchant_id',
                 'bank_transfer_client_id', 'bank_transfer_secret_key', 'bank_transfer_merchant_id',
                 'bank_c2p_client_id', 'bank_c2p_secret_key', 'bank_c2p_merchant_id',
                 'bank_environment', 'bank_account_number', 'bank_phone_number', 'bank_customer_id')
    def _compute_bank_integration_account_id(self):
        for journal in self:
            if journal.type == 'bank' and journal.bank_integration_enabled:
                integration = self.env['bank.integration.account'].sudo().search([
                    ('journal_id', '=', journal.id)
                ], limit=1)
                vals = {
                    'name': f"API {journal.name}",
                    'journal_id': journal.id,
                    'bank_type': journal.bank_type or 'mercantil',
                    'environment': journal.bank_environment or 'sandbox',
                    'client_id': journal.bank_client_id or '',
                    'secret_key': journal.bank_secret_key or '',
                    'merchant_id': journal.bank_merchant_id or '',
                    'transfer_client_id': journal.bank_transfer_client_id or '17ebe62df9a1ca008b912ddd92f3d486',
                    'transfer_secret_key': journal.bank_transfer_secret_key or '0011103402J000000405660872000000000000',
                    'transfer_merchant_id': journal.bank_transfer_merchant_id or '11103402',
                    'c2p_client_id': journal.bank_c2p_client_id or '81188330-c768-46fe-a378-ff3ac9e88824',
                    'c2p_secret_key': journal.bank_c2p_secret_key or 'A11103402525120190822HB01',
                    'c2p_merchant_id': journal.bank_c2p_merchant_id or '200284',
                    'integrator_id': journal.bank_integrator_id or '1',
                    'terminal_id': journal.bank_terminal_id or '1',
                    'account_number': journal.bank_account_number or '',
                    'phone_number': journal.bank_phone_number or '',
                    'customer_id': journal.bank_customer_id or '',
                    'active': journal.bank_integration_enabled,
                }
                if not integration:
                    integration = self.env['bank.integration.account'].sudo().create(vals)
                else:
                    integration.sudo().write(vals)
                journal.bank_integration_account_id = integration
            else:
                journal.bank_integration_account_id = False

    def action_test_bank_connection(self):
        """Prueba la conexión bancaria directamente desde la ficha del Diario."""
        self.ensure_one()
        if not self.bank_integration_enabled:
            raise UserError(_("Debe habilitar la integración API bancaria para probar la conexión."))

        self._compute_bank_integration_account_id()
        if self.bank_integration_account_id:
            return self.bank_integration_account_id.sudo().action_test_connection()
        else:
            raise UserError(_("No se pudo obtener la cuenta de integración bancaria."))

        self._compute_bank_integration_account_id()
        if self.bank_integration_account_id:
            return self.bank_integration_account_id.sudo().action_test_connection()
        else:
            raise UserError(_("No se pudo obtener la cuenta de integración bancaria."))
