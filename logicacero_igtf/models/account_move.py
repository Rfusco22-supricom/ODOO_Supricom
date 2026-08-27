from odoo import models, fields, _, api
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang

class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_ve_igtf_applied = fields.Boolean(string='IGTF Aplicado', readonly=True, copy=False)

    igtf_base_suggested = fields.Monetary(string='Base IGTF Sugerido', compute='_compute_igtf_suggested', currency_field='currency_id_dif')
    igtf_amount_suggested = fields.Monetary(string='Monto IGTF Sugerido', compute='_compute_igtf_suggested', currency_field='currency_id_dif')

    igtf_base_suggested_bs = fields.Monetary(string='Base IGTF Sugerido (Bs)', compute='_compute_igtf_suggested', currency_field='company_currency_id')
    igtf_amount_suggested_bs = fields.Monetary(string='Monto IGTF Sugerido (Bs)', compute='_compute_igtf_suggested', currency_field='company_currency_id')

    @api.depends('invoice_line_ids', 'amount_untaxed', 'amount_tax', 'amount_total', 'amount_untaxed_usd', 'amount_untaxed_bs', 'partner_id')
    def _compute_igtf_suggested(self):
        for move in self:
            # Si la homologación está desactivada, no sugerir IGTF
            if hasattr(move.company_id, 'homologacion_activa') and not move.company_id.homologacion_activa:
                move.igtf_base_suggested = 0.0
                move.igtf_amount_suggested = 0.0
                move.igtf_base_suggested_bs = 0.0
                move.igtf_amount_suggested_bs = 0.0
                continue

            # Solo aplicar IGTF para partners venezolanos
            is_venezuela = move.partner_id.country_id and move.partner_id.country_id.code == 'VE'
            if not is_venezuela:
                move.igtf_base_suggested = 0.0
                move.igtf_amount_suggested = 0.0
                move.igtf_base_suggested_bs = 0.0
                move.igtf_amount_suggested_bs = 0.0
                continue

            # 1. Invoice Currency is USD
            if move.currency_id.name == 'USD':
                base = move.amount_total
                
                # Para BS: tomamos el monto convertido que guarda account_dual_currency
                exchange_rate = getattr(move, 'tax_today', 1.0) or 1.0
                if hasattr(move, 'amount_total_bs') and move.amount_total_bs:
                    base_bs = move.amount_total_bs
                else:
                    base_bs = move.amount_total * exchange_rate
                    
            # 2. Invoice Currency is Bolivares (VES/VEF/VED)
            else:
                base_bs = move.amount_total
                
                # Para USD: tomamos el equivalente en dólares
                exchange_rate = getattr(move, 'tax_today', 1.0) or 1.0
                if hasattr(move, 'amount_total_usd') and move.amount_total_usd:
                    base = move.amount_total_usd
                else:
                    base = (move.amount_total / exchange_rate) if exchange_rate else 0.0

            move.igtf_base_suggested = base
            move.igtf_amount_suggested = base * 0.03

            move.igtf_base_suggested_bs = base_bs
            move.igtf_amount_suggested_bs = base_bs * 0.03

    @api.depends('line_ids', 'partner_id')
    def _compute_tax_totals(self):
        """Inject Monto IGTF Sugerido between Subtotal and IVA in tax_totals."""
        super()._compute_tax_totals()
        for move in self:
            # Si la homologación está desactivada, no inyectar IGTF
            if hasattr(move.company_id, 'homologacion_activa') and not move.company_id.homologacion_activa:
                continue

            # Solo para partners venezolanos
            is_venezuela = move.partner_id.country_id and move.partner_id.country_id.code == 'VE'
            if not is_venezuela:
                continue

            if not move.tax_totals:
                continue
            totals = move.tax_totals

            # Determine the correct IGTF values based on currency
            if move.currency_id.name == 'USD':
                igtf_amount = move.igtf_amount_suggested
                igtf_base = move.igtf_base_suggested
                currency = move.currency_id
            else:
                igtf_amount = move.igtf_amount_suggested_bs
                igtf_base = move.igtf_base_suggested_bs
                currency = move.currency_id

            if not igtf_amount:
                continue

            # If the IGTF product is already present in invoice lines, show 0
            igtf_product = move.company_id.igtf_product_id if hasattr(move.company_id, 'igtf_product_id') else False
            if igtf_product and move.invoice_line_ids.filtered(lambda l: l.product_id == igtf_product):
                igtf_amount = 0.0
                igtf_base = 0.0

            # Format amounts for display
            fmt_amount = formatLang(self.env, igtf_amount, currency_obj=currency)
            fmt_base = formatLang(self.env, igtf_base, currency_obj=currency)

            # Create the IGTF entry as a tax group item
            igtf_entry = {
                'tax_group_name': 'IGTF 3% Sugerido',
                'tax_group_amount': igtf_amount,
                'tax_group_base_amount': igtf_base,
                'formatted_tax_group_amount': fmt_amount,
                'formatted_tax_group_base_amount': fmt_base,
                'tax_group_id': False,
                'group_key': 'igtf_suggested',
            }

            # Insert the IGTF entry at the beginning of groups_by_subtotal
            # so it appears right after Subtotal and before IVA
            if 'groups_by_subtotal' in totals:
                for subtotal_key in totals['groups_by_subtotal']:
                    totals['groups_by_subtotal'][subtotal_key].insert(0, igtf_entry)
                    break  # Only insert in the first subtotal group

            move.tax_totals = totals
