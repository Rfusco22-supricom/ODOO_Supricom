from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BankTransactionSelectWizard(models.TransientModel):
    _name = 'bank.transaction.select.wizard'
    _description = 'Wizard de Selección e Ingreso Bancario'

    payment_id = fields.Many2one('account.payment', string='Pago')
    partner_id = fields.Many2one('res.partner', string='Cliente / Proveedor')
    journal_id = fields.Many2one(
        'account.journal', string='Diario Bancario', required=True,
        domain="[('type', '=', 'bank')]"
    )
    date_from = fields.Date(string='Fecha Desde', default=fields.Date.context_today, required=True)
    date_to = fields.Date(string='Fecha Hasta', default=fields.Date.context_today, required=True)
    payment_reference = fields.Char(string='Referencia / N° Operación')
    amount = fields.Monetary(string='Monto Búsqueda', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='journal_id.currency_id')

    line_ids = fields.Many2many(
        'bank.transaction.line', string='Ingresos Pendientes Encontrados',
        compute='_compute_line_ids', store=True, readonly=False
    )
    selected_line_id = fields.Many2one('bank.transaction.line', string='Transacción Seleccionada')

    @api.depends('journal_id', 'date_from', 'date_to', 'payment_reference', 'amount')
    def _compute_line_ids(self):
        for wizard in self:
            if wizard.journal_id:
                domain = [
                    ('journal_id', '=', wizard.journal_id.id),
                    ('state', '=', 'pending'),
                ]
                if wizard.date_from:
                    domain.append(('trx_date', '>=', wizard.date_from))
                if wizard.date_to:
                    domain.append(('trx_date', '<=', wizard.date_to))
                if wizard.payment_reference:
                    domain.append(('payment_reference', 'ilike', wizard.payment_reference.strip()))
                if wizard.amount:
                    domain.append(('amount', '=', wizard.amount))

                lines = self.env['bank.transaction.line'].search(domain)
                wizard.line_ids = [(6, 0, lines.ids)]
            else:
                wizard.line_ids = [(6, 0, [])]

    def action_fetch_live_bank(self):
        """Consulta en vivo al banco para las fechas, referencia y monto seleccionados."""
        self.ensure_one()
        accounts = self.env['bank.integration.account'].search([
            ('journal_id', '=', self.journal_id.id),
            ('active', '=', True)
        ])
        if not accounts:
            raise UserError(_("No existe una cuenta de integración bancaria activa configurada para el diario %s.") % self.journal_id.name)

        new_lines = self.env['bank.transaction.line']
        curr_date = self.date_from
        while curr_date <= self.date_to:
            for acc in accounts:
                fetched = acc.fetch_and_store_transactions(
                    target_date=curr_date,
                    payment_reference=self.payment_reference,
                    amount=self.amount
                )
                new_lines |= fetched
            curr_date += timedelta(days=1)

        # Volver a cargar las líneas pendientes aplicando los filtros
        domain = [
            ('journal_id', '=', self.journal_id.id),
            ('state', '=', 'pending'),
            ('trx_date', '>=', self.date_from),
            ('trx_date', '<=', self.date_to),
        ]
        if self.payment_reference:
            domain.append(('payment_reference', 'ilike', self.payment_reference.strip()))
        if self.amount:
            domain.append(('amount', '=', self.amount))

        all_lines = self.env['bank.transaction.line'].search(domain)
        self.line_ids = [(6, 0, all_lines.ids)]

        ctx = dict(self.env.context)
        if self.partner_id:
            ctx['default_partner_id'] = self.partner_id.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bank.transaction.select.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_confirm_selection(self):
        """Aplica la transacción seleccionada al pago o al registro de pago de factura."""
        self.ensure_one()
        line = self.selected_line_id
        if not line and self.line_ids:
            if len(self.line_ids) == 1:
                line = self.line_ids[0]

        if not line:
            raise UserError(_("Por favor seleccione una transacción bancaria de la lista."))

        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')

        # 1. Determinar partner infaliblemente
        target_partner = self.partner_id
        if not target_partner and self.env.context.get('default_partner_id'):
            target_partner = self.env['res.partner'].browse(self.env.context.get('default_partner_id'))

        if not target_partner and active_model == 'account.payment.register' and active_id:
            pay_reg = self.env['account.payment.register'].browse(active_id)
            if pay_reg.exists() and pay_reg.partner_id:
                target_partner = pay_reg.partner_id

        if not target_partner and active_model == 'account.move' and active_id:
            move = self.env['account.move'].browse(active_id)
            if move.exists() and move.partner_id:
                target_partner = move.partner_id

        if not target_partner:
            target_partner = line._find_matching_partner()

        # Si viene desde el wizard de Registro de Pago de Factura (account.payment.register)
        if active_model == 'account.payment.register' and active_id:
            pay_reg = self.env['account.payment.register'].browse(active_id)
            if pay_reg.exists():
                memo = pay_reg.communication or ''
                if line.payment_reference and line.payment_reference not in memo:
                    memo = f"{memo} Ref: {line.payment_reference}" if memo else f"Ref: {line.payment_reference}"
                vals = {
                    'journal_id': self.journal_id.id,
                    'amount': line.amount,
                    'payment_date': line.trx_date,
                    'communication': memo,
                    'bank_transaction_line_id': line.id,
                }
                partner_to_set = target_partner or pay_reg.partner_id
                if partner_to_set:
                    vals['partner_id'] = partner_to_set.id
                pay_reg.write(vals)
                return {
                    'name': _('Registrar Pago'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.payment.register',
                    'res_id': pay_reg.id,
                    'view_mode': 'form',
                    'target': 'new',
                }

        # Si viene desde un pago existente (account.payment)
        if self.payment_id:
            vals = {
                'journal_id': self.journal_id.id,
                'amount': line.amount,
                'date': line.trx_date,
                'ref': f"Ref Bancaria: {line.payment_reference}",
                'bank_transaction_line_id': line.id,
            }
            partner_to_set = target_partner or self.payment_id.partner_id
            if partner_to_set:
                vals['partner_id'] = partner_to_set.id
            self.payment_id.write(vals)
            return {'type': 'ir.actions.act_window_close'}
        else:
            # Si se abre de forma independiente y crea un pago nuevo, copiar el cliente de la factura
            partner_to_set = target_partner or line._find_matching_partner()
            return {
                'name': _('Registrar Pago'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.payment',
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'default_payment_type': 'inbound',
                    'default_partner_type': 'customer',
                    'default_partner_id': partner_to_set.id if partner_to_set else False,
                    'default_journal_id': self.journal_id.id,
                    'default_amount': line.amount,
                    'default_date': line.trx_date,
                    'default_ref': f"Mercantil Ref: {line.payment_reference}",
                    'default_bank_transaction_line_id': line.id,
                }
            }
