from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountApplyExchangeDiffWizard(models.TransientModel):
    _name = 'account.apply.exchange.diff.wizard'
    _description = 'Aplicar Diferencial Cambiario a Factura'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    
    invoice_id = fields.Many2one('account.move', string="Factura", required=True)
    partner_id = fields.Many2one('res.partner', related='invoice_id.partner_id')
    
    date = fields.Date(string="Fecha", default=fields.Date.context_today, required=True)
    
    journal_id = fields.Many2one(
        'account.journal', 
        string="Diario", 
        domain=[('type', '=', 'general')],
        default=lambda self: self.env.company.currency_exchange_journal_id
    )
    
    transit_account_id = fields.Many2one(
        'account.account',
        string="Cuenta de Tránsito",
        default=lambda self: self.env.company.exchange_diff_transit_account_id,
        required=True
    )
    
    diff_type = fields.Selection([
        ('gain', 'Ganancia (Aumentar CXC/CXP)'),
        ('loss', 'Pérdida (Disminuir CXC/CXP)')
    ], string="Tipo de Diferencia", required=True, default='gain')
    
    amount = fields.Monetary(string="Monto Diferencial", currency_field='currency_id', required=True)
    
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get('active_model') == 'account.move' and self._context.get('active_id'):
            invoice_id = self._context.get('active_id')
            res['invoice_id'] = invoice_id
            
            # Try to pre-calculate amount from Transit Account
            # Logic: Check balance directly on Transit Account for this Partner
            invoice = self.env['account.move'].browse(invoice_id)
            company = self.env.company
            transit_account = company.exchange_diff_transit_account_id
            
            if transit_account and invoice.partner_id:
                # Search for unreconciled lines in Transit Account for this partner
                # We could sum them up.
                domain = [
                    ('account_id', '=', transit_account.id),
                    ('partner_id', '=', invoice.partner_id.id),
                    ('parent_state', '=', 'posted'),
                    ('reconciled', '=', False)
                ]
                lines = self.env['account.move.line'].search(domain)
                
                balance = sum(lines.mapped('balance'))
                # Balance > 0 (Debit) means Loss stored there (waiting to Credit Invoice?) OR Gain stored (waiting to Debit Invoice?)
                
                # RECALL OUR LOGIC:
                # Auto-Move (Gain): Debit CXP / Credit Transit.
                # So Transit has CREDIT balance (-2500).
                
                # Wizard (Gain): Debit Transit / Credit CXP.
                # So we need a positive amount to Debit Transit.
                
                # If Balance is Negative (Credit), it means we have a surplus/gain in Transit.
                # We need to DEBIT Transit to close it.
                # So Amount = abs(balance). Type = Gain (Debit Transit).
                
                if balance < 0:
                     res['amount'] = abs(balance)
                     res['diff_type'] = 'gain' # Debit Transit / Credit CXP (Reduces Factura)
                elif balance > 0:
                     res['amount'] = abs(balance)
                     res['diff_type'] = 'loss' # Credit Transit / Debit CXP (Increases Factura)
                else:
                     res['amount'] = 0.0

        return res

    def action_apply_diff(self):
        self.ensure_one()
        _logger.info(f"[APPLY-DIFF] Starting Wizard for Invoice: {self.invoice_id.name}")
        _logger.info(f"[APPLY-DIFF] Amount: {self.amount}, Type: {self.diff_type}")
        
        if self.amount <= 0:
            raise UserError("El monto debe ser positivo.")

        # Logic:
        # Gain: Debit CXC / Credit Transit
        # Loss: Debit Transit / Credit CXC
        # For Payables (Suppliers):
        # Gain (We owe less? No, Gain usually means we pay less local currency for same USD?)
        # Let's stick to pure Account logic.
        
        # IMPORTANTE: El asiento de TRÁNSITO ya afectó la cuenta CXP/CXC.
        # Este wizard de APLICACIÓN debe:
        # 1. CERRAR el saldo del Tránsito
        # 2. Registrar la Ganancia o Pérdida en las cuentas correspondientes
        # SIN afectar CXP/CXC nuevamente.
        
        # SITUACIÓN EN TRÁNSITO (Payable/Supplier):
        # - Si pagamos MÁS Bs: El tránsito recibió Debit Transit / Credit CXP
        #   Tránsito tiene saldo DÉBITO.
        #   Esto es una PÉRDIDA (pagamos más por lo mismo).
        #   Para cerrar: Debit Pérdida / Credit Transit
        
        # - Si pagamos MENOS Bs: El tránsito recibió Debit CXP / Credit Transit
        #   Tránsito tiene saldo CRÉDITO.
        #   Esto es una GANANCIA (pagamos menos por lo mismo).
        #   Para cerrar: Debit Transit / Credit Ganancia
        
        account_cxc_cxp = self.invoice_id.line_ids.filtered(lambda l: l.account_type in ('asset_receivable', 'liability_payable')).account_id
        if not account_cxc_cxp:
            raise UserError("No se encontró cuenta por cobrar/pagar en la factura.")

        _logger.info(f"[APPLY-DIFF] Invoice Account (CXC/CXP): {account_cxc_cxp.code} - {account_cxc_cxp.name}")

        # Get Gain/Loss accounts from company
        company = self.env.company
        account_gain = company.income_currency_exchange_account_id
        account_loss = company.expense_currency_exchange_account_id
        
        if not account_gain or not account_loss:
            raise UserError("Debe configurar las cuentas de Ganancia y Pérdida Cambiaria en los ajustes de la Compañía.")
        
        debit_acc = False
        credit_acc = False
        
        if self.diff_type == 'gain':
             # Ganancia: El tránsito tiene saldo Crédito.
             # Para cerrar: Debit Transit / Credit Ganancia
             debit_acc = self.transit_account_id.id
             credit_acc = account_gain.id
             
        else:
             # Pérdida: El tránsito tiene saldo Débito.
             # Para cerrar: Debit Pérdida / Credit Transit
             debit_acc = account_loss.id
             credit_acc = self.transit_account_id.id

        _logger.info(f"[APPLY-DIFF] Debit Account: {debit_acc}, Credit Account: {credit_acc}")

        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': f"Aplicación Diferencial: {self.invoice_id.name}",
            'move_type': 'entry',
            'tax_today': 0, # Force Dual Currency 0
        }
        
        lines = [
            (0, 0, {
                'name': self.diff_type == 'gain' and 'Ganancia Diferencial' or 'Pérdida Diferencial',
                'account_id': debit_acc,
                'debit': self.amount,
                'credit': 0,
                'partner_id': self.partner_id.id,
                'debit_usd': 0, 'credit_usd': 0, # Force Dual Currency 0
            }),
            (0, 0, {
                'name': 'Contrapartida Tránsito',
                'account_id': credit_acc,
                'debit': 0,
                'credit': self.amount,
                'partner_id': self.partner_id.id,
                'debit_usd': 0, 'credit_usd': 0, # Force Dual Currency 0
            })
        ]
        
        move_vals['line_ids'] = lines
        
        _logger.info(f"[APPLY-DIFF] Creating Move with vals: Journal={self.journal_id.name}, Date={self.date}, Amount={self.amount}")
        
        # Context to force our dual currency logic override
        move = self.env['account.move'].with_context(force_no_dual_currency_exchange=True).create(move_vals)
        move.action_post()
        
        _logger.info(f"[APPLY-DIFF] Created and Posted Move: {move.name}")
        
        # Ahora reconciliamos las líneas de Tránsito:
        # 1. La línea del nuevo asiento que afecta a Transit
        # 2. Las líneas pendientes en Transit para este partner
        
        transit_line_new = move.line_ids.filtered(lambda l: l.account_id == self.transit_account_id)
        
        _logger.info(f"[APPLY-DIFF] Transit Line from new Move: {transit_line_new.name} | Debit: {transit_line_new.debit} | Credit: {transit_line_new.credit}")
        
        # Buscar líneas pendientes en Tránsito para este partner
        transit_lines_pending = self.env['account.move.line'].search([
            ('account_id', '=', self.transit_account_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('id', '!=', transit_line_new.id if transit_line_new else 0),
        ])
        
        _logger.info(f"[APPLY-DIFF] Pending Transit Lines: {len(transit_lines_pending)}")
        
        if transit_line_new and transit_lines_pending:
            try:
                # Reconciliar la nueva línea con las pendientes
                # El monto debería cuadrar automáticamente
                (transit_line_new + transit_lines_pending).with_context(
                    no_exchange_difference=True
                ).reconcile()
                
                _logger.info("[APPLY-DIFF] Transit lines reconciled successfully.")
            except Exception as e:
                _logger.warning(f"[APPLY-DIFF] Transit reconciliation warning: {e}")
                # Not critical - the move is posted, just might not be fully reconciled
        
        _logger.info("[APPLY-DIFF] Application completed.")
        
        return {'type': 'ir.actions.act_window_close'}
