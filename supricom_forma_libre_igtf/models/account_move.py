from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    # ==========================================
    # FORMA LIBRE (De forma_libre)
    # ==========================================
    # Campos en moneda base
    tax_16 = fields.Monetary(string="IVA 16%", compute="_compute_tax_amounts", store=True)
    tax_8 = fields.Monetary(string="IVA 8%", compute="_compute_tax_amounts", store=True)
    tax_31 = fields.Monetary(string="IVA 31%", compute="_compute_tax_amounts", store=True)
    tax_exento = fields.Monetary(string="Monto Exento", compute="_compute_tax_amounts", store=True)
    base_16 = fields.Monetary(string="Base Imponible 16%", compute="_compute_tax_amounts", store=True)
    base_8 = fields.Monetary(string="Base Imponible 8%", compute="_compute_tax_amounts", store=True)
    base_31 = fields.Monetary(string="Base Imponible 31%", compute="_compute_tax_amounts", store=True)
    total_imponible = fields.Monetary(string="Total Imponible", compute="_compute_tax_amounts", store=True)
    subtotal = fields.Monetary(string="SubTotal", compute="_compute_tax_amounts", store=True)

    # Campos en dólares
    tax_16_usd = fields.Monetary(string="IVA 16% (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    tax_8_usd = fields.Monetary(string="IVA 8% (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    tax_31_usd = fields.Monetary(string="IVA 31% (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    tax_exento_usd = fields.Monetary(string="Monto Exento (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    base_16_usd = fields.Monetary(string="Base Imponible 16% (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    base_8_usd = fields.Monetary(string="Base Imponible 8% (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    base_31_usd = fields.Monetary(string="Base Imponible 31% (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    total_imponible_usd = fields.Monetary(string="Total Imponible (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')
    subtotal_usd = fields.Monetary(string="SubTotal (USD)", compute="_compute_tax_amounts", store=True, currency_field='usd_currency_id')

    # Moneda USD
    usd_currency_id = fields.Many2one('res.currency', string="Moneda USD", default=lambda self: self.env.ref('base.USD'))

    # Control de impresión
    invoice_template_dual_printed = fields.Boolean(string="Factura Original Impresa", default=False, readonly=True)
    print_count = fields.Integer(string="Cantidad de impresiones", copy=False, default=0)

    # Control para visibilidad del botón
    show_print_dual_button = fields.Boolean(
        string="Mostrar botón de factura dual",
        compute="_compute_show_print_dual_button",
        store=False
    )

    @api.depends('move_type')
    def _compute_show_print_dual_button(self):
        for rec in self:
            rec.show_print_dual_button = rec.move_type == 'out_invoice' and rec.company_id.supricom_fl_igtf_enabled

    @api.depends('line_ids.price_subtotal', 'line_ids.tax_ids', 'tax_today', 'currency_id')
    def _compute_tax_amounts(self):
        for move in self:
            tax_16 = tax_8 = tax_31 = tax_exento = 0.0
            base_16 = base_8 = base_31 = 0.0
    
            exchange_rate = getattr(move, 'tax_today', 1.0) or 1.0
            is_usd = move.currency_id and move.currency_id.name == 'USD'
    
            for line in move.line_ids.filtered(lambda l: l.display_type == 'product'):
                subtotal = line.price_subtotal or 0.0
                tax_list = line.tax_ids.filtered(lambda t: t.amount_type == 'percent')
    
                if not tax_list or all(t.amount == 0 for t in tax_list):
                    tax_exento += subtotal
                else:
                    for tax in tax_list:
                        rate = tax.amount
                        if rate == 16:
                            base_16 += subtotal
                            tax_16 += subtotal * (rate / 100)
                        elif rate == 8:
                            base_8 += subtotal
                            tax_8 += subtotal * (rate / 100)
                        elif rate == 31:
                            base_31 += subtotal
                            tax_31 += subtotal * (rate / 100)
    
            if is_usd:
                move.tax_16_usd = tax_16
                move.tax_8_usd = tax_8
                move.tax_31_usd = tax_31
                move.tax_exento_usd = tax_exento
                move.base_16_usd = base_16
                move.base_8_usd = base_8
                move.base_31_usd = base_31
                move.total_imponible_usd = base_16 + base_8 + base_31
                move.subtotal_usd = tax_exento + move.total_imponible_usd + tax_16 + tax_8 + tax_31
                
                move.tax_16 = tax_16 * exchange_rate
                move.tax_8 = tax_8 * exchange_rate
                move.tax_31 = tax_31 * exchange_rate
                move.tax_exento = tax_exento * exchange_rate
                move.base_16 = base_16 * exchange_rate
                move.base_8 = base_8 * exchange_rate
                move.base_31 = base_31 * exchange_rate
                move.total_imponible = move.total_imponible_usd * exchange_rate
                move.subtotal = move.subtotal_usd * exchange_rate
            else:
                move.tax_16 = tax_16
                move.tax_8 = tax_8
                move.tax_31 = tax_31
                move.tax_exento = tax_exento
                move.base_16 = base_16
                move.base_8 = base_8
                move.base_31 = base_31
                move.total_imponible = base_16 + base_8 + base_31
                move.subtotal = tax_exento + move.total_imponible + tax_16 + tax_8 + tax_31
                
                move.tax_16_usd = tax_16 / exchange_rate
                move.tax_8_usd = tax_8 / exchange_rate
                move.tax_31_usd = tax_31 / exchange_rate
                move.tax_exento_usd = tax_exento / exchange_rate
                move.base_16_usd = base_16 / exchange_rate
                move.base_8_usd = base_8 / exchange_rate
                move.base_31_usd = base_31 / exchange_rate
                move.total_imponible_usd = move.total_imponible / exchange_rate
                move.subtotal_usd = move.subtotal / exchange_rate

    def get_report_name(self):
        return f"Factura Fiscal - {self.name}"

    def action_print_invoice_custom_dual(self):
        if self.state == 'posted':
            if self.move_type == 'out_refund':
                return self.env.ref('supricom_forma_libre_igtf.action_report_invoice_custom_dual').report_action(self)
            elif self.debit_origin_id:
                return self.env.ref('supricom_forma_libre_igtf.action_report_invoice_custom_dual').report_action(self)
            else:
                return self.env.ref('supricom_forma_libre_igtf.action_report_invoice_custom_dual').report_action(self)
        else:
            if self.move_type == 'out_refund':
                message = 'La Nota de Crédito debe estar publicada para ser impresa.'
            elif self.debit_origin_id:
                message = 'La Nota de Débito debe estar publicada para ser impresa.'
            else:
                message = 'La factura debe estar publicada para ser impresa.'
            raise UserError(message)
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['invoice_template_dual_printed'] = False
        return super(AccountMove, self).create(vals_list)

    def copy(self, default=None):
        default = dict(default or {}, invoice_template_dual_printed=False)
        return super().copy(default)

    # ==========================================
    # IGTF (De logicacero_igtf y g3c_ve_homologacion)
    # ==========================================
    l10n_ve_igtf_applied = fields.Boolean(string='IGTF Aplicado', readonly=True, copy=False)
    igtf_base_suggested = fields.Monetary(string='Base IGTF Sugerido', compute='_compute_igtf_suggested', currency_field='currency_id_dif')
    igtf_amount_suggested = fields.Monetary(string='Monto IGTF Sugerido', compute='_compute_igtf_suggested', currency_field='currency_id_dif')
    igtf_base_suggested_bs = fields.Monetary(string='Base IGTF Sugerido (Bs)', compute='_compute_igtf_suggested', currency_field='company_currency_id')
    igtf_amount_suggested_bs = fields.Monetary(string='Monto IGTF Sugerido (Bs)', compute='_compute_igtf_suggested', currency_field='company_currency_id')

    def action_apply_igtf_tax(self):
        self.ensure_one()
        is_venezuela = self.partner_id.country_id and self.partner_id.country_id.code == 'VE'
        if not self.company_id.supricom_fl_igtf_enabled or not is_venezuela:
            return

        igtf_tax = self.env['account.tax'].search([
            ('l10n_ve_is_igtf', '=', True),
            ('company_id', '=', self.company_id.id),
            ('type_tax_use', '=', 'sale')
        ], limit=1)

        if not igtf_tax:
            raise UserError(_('No se encontró ningún impuesto configurado como IGTF para esta compañía. Por favor configure uno en Contabilidad > Impuestos.'))

        was_posted = self.state == 'posted'
        if was_posted:
            self.button_draft()

        for line in self.invoice_line_ids:
            if igtf_tax not in line.tax_ids:
                line.tax_ids = [(4, igtf_tax.id)]

        self.l10n_ve_igtf_applied = True

        if was_posted:
            self.action_post()

    @api.depends('invoice_line_ids', 'amount_total', 'amount_untaxed_usd', 'amount_untaxed_bs', 'partner_id')
    def _compute_igtf_suggested(self):
        for move in self:
            is_venezuela = move.partner_id.country_id and move.partner_id.country_id.code == 'VE'
            if not move.company_id.supricom_fl_igtf_enabled or not is_venezuela:
                move.igtf_base_suggested = 0.0
                move.igtf_amount_suggested = 0.0
                move.igtf_base_suggested_bs = 0.0
                move.igtf_amount_suggested_bs = 0.0
                continue

            base = 0.0
            is_company_usd = move.company_id.currency_id.name == 'USD'
            if is_company_usd:
                # Company in USD: IGTF base is always amount_untaxed (already USD)
                base = move.amount_untaxed
            elif move.currency_id != move.company_id.currency_id:
                base = move.amount_untaxed
            elif hasattr(move, 'amount_untaxed_usd'):
                base = move.amount_untaxed_usd

            move.igtf_base_suggested = base
            move.igtf_amount_suggested = base * 0.03

            base_bs = 0.0
            if is_company_usd:
                # Company in USD: Bs reference = amount_untaxed * exchange rate
                exchange_rate = getattr(move, 'tax_today', 1.0) or 1.0
                base_bs = move.amount_untaxed * exchange_rate
            elif hasattr(move, 'amount_untaxed_bs'):
                base_bs = move.amount_untaxed_bs
            elif hasattr(move, 'amount_untaxed_signed'):
                base_bs = abs(move.amount_untaxed_signed)

            move.igtf_base_suggested_bs = base_bs
            move.igtf_amount_suggested_bs = base_bs * 0.03

    @api.depends('line_ids', 'partner_id')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for move in self:
            is_venezuela = move.partner_id.country_id and move.partner_id.country_id.code == 'VE'
            if not move.company_id.supricom_fl_igtf_enabled or not move.tax_totals or not is_venezuela:
                continue
            
            totals = move.tax_totals
            is_company_usd = move.company_id.currency_id.name == 'USD'
            same_curr = hasattr(move, 'same_currency') and move.same_currency
            
            if is_company_usd or not same_curr:
                # USD company or different currencies: use USD-based values
                igtf_amount = move.igtf_amount_suggested
                igtf_base = move.igtf_base_suggested
                currency = getattr(move, 'currency_id_dif', move.currency_id)
            else:
                igtf_amount = move.igtf_amount_suggested_bs
                igtf_base = move.igtf_base_suggested_bs
                currency = move.company_currency_id

            if not igtf_amount:
                continue

            igtf_product = move.company_id.igtf_product_id if hasattr(move.company_id, 'igtf_product_id') else False
            if igtf_product and move.invoice_line_ids.filtered(lambda l: l.product_id == igtf_product):
                igtf_amount = 0.0
                igtf_base = 0.0

            fmt_amount = formatLang(self.env, igtf_amount, currency_obj=currency)
            fmt_base = formatLang(self.env, igtf_base, currency_obj=currency)

            igtf_entry = {
                'tax_group_name': 'IGTF 3% Sugerido',
                'tax_group_amount': igtf_amount,
                'tax_group_base_amount': igtf_base,
                'formatted_tax_group_amount': fmt_amount,
                'formatted_tax_group_base_amount': fmt_base,
                'tax_group_id': False,
                'group_key': 'igtf_suggested',
            }

            if 'groups_by_subtotal' in totals:
                for subtotal_key in totals['groups_by_subtotal']:
                    totals['groups_by_subtotal'][subtotal_key].insert(0, igtf_entry)
                    break 

            move.tax_totals = totals

    def action_post(self):
        # Automatización de IGTF (Extraída de homologación)
        for rec in self:
            is_venezuela = rec.partner_id.country_id and rec.partner_id.country_id.code == 'VE'
            if rec.move_type in ['out_invoice', 'out_refund'] and rec.company_id.supricom_fl_igtf_enabled and is_venezuela:
                igtf_tax = self.env['account.tax'].search([
                    ('l10n_ve_is_igtf', '=', True),
                    ('company_id', '=', rec.company_id.id),
                    ('type_tax_use', '=', 'sale')
                ], limit=1)
                
                if igtf_tax:
                    is_dual = hasattr(rec, 'currency_id_dif') and rec.currency_id_dif
                    if rec.currency_id != rec.company_id.currency_id or is_dual:
                        # Optimization: Assign tax in batch to avoid O(N^2) dynamic lines recomputation
                        lines_to_update = rec.invoice_line_ids.filtered(
                            lambda l: l.display_type == 'product' and igtf_tax not in l.tax_ids
                        )
                        if lines_to_update:
                            lines_to_update.write({'tax_ids': [(4, igtf_tax.id)]})
                        
                        rec.l10n_ve_igtf_applied = True
        
        return super(AccountMove, self).action_post()

    def get_vet_timestamp(self):
        """Devuelve la fecha de creación convertida a la zona horaria de Venezuela."""
        self.ensure_one()
        if not self.create_date:
            return ''
        import pytz
        # Odoo almacena en UTC (naive)
        utc_dt = self.create_date.replace(tzinfo=pytz.UTC)
        vet_tz = pytz.timezone('America/Caracas')
        vet_dt = utc_dt.astimezone(vet_tz)
        return vet_dt.strftime('%d/%m/%Y %I:%M %p')

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    alicuota = fields.Char(string='Alícuota', compute='_compute_alicuota', store=True)

    @api.depends('tax_ids')
    def _compute_alicuota(self):
        for line in self:
            if not line.tax_ids:
                line.alicuota = '( E )'
            else:
                all_zero = all(tax.amount == 0 for tax in line.tax_ids)
                line.alicuota = '( E )' if all_zero else ''
