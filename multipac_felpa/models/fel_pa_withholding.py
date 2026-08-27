# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.exceptions import UserError


class FelPaWithholding(models.Model):
    _name = 'fel_pa.withholding'
    _description = 'Certificado de Retención ITBMS'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nro. de Retención',
        readonly=True,
        default='Nuevo',
        copy=False,
        tracking=True,
    )
    date = fields.Date(
        string='Fecha',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contribuyente',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True, copy=False)

    resolution_text = fields.Char(
        string='Resolución',
        default='Resolución Nro. 201-5894 Agosto de 2022 (literal D)',
    )
    line_ids = fields.One2many(
        'fel_pa.withholding.line',
        'withholding_id',
        string='Líneas de Retención',
    )

    # --- Computed Totals ---
    total_base = fields.Monetary(
        string='Total Base Imponible',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_itbms_causado = fields.Monetary(
        string='Total ITBMS Causado',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_itbms_retenido = fields.Monetary(
        string='Total ITBMS Retenido',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    total_a_pagar = fields.Monetary(
        string='Total a Pagar',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
        store=True,
    )

    @api.depends('line_ids.base_imponible', 'line_ids.itbms_causado',
                 'line_ids.itbms_retenido', 'line_ids.total_a_pagar')
    def _compute_totals(self):
        for rec in self:
            rec.total_base = sum(rec.line_ids.mapped('base_imponible'))
            rec.total_itbms_causado = sum(rec.line_ids.mapped('itbms_causado'))
            rec.total_itbms_retenido = sum(rec.line_ids.mapped('itbms_retenido'))
            rec.total_a_pagar = sum(rec.line_ids.mapped('total_a_pagar'))

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('Debe agregar al menos una línea de retención.'))
            if rec.name == 'Nuevo':
                rec.name = self.env['ir.sequence'].next_by_code('fel_pa.withholding') or 'Nuevo'
            rec.state = 'confirmed'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_print(self):
        return self.env.ref('multipac_felpa.action_report_withholding_certificate').report_action(self)


class FelPaWithholdingLine(models.Model):
    _name = 'fel_pa.withholding.line'
    _description = 'Línea de Certificado de Retención'

    withholding_id = fields.Many2one(
        'fel_pa.withholding',
        string='Certificado',
        required=True,
        ondelete='cascade',
    )
    move_id = fields.Many2one(
        'account.move',
        string='Nº de Factura',
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('partner_id', '=', parent.partner_id)]",
        required=True,
    )
    invoice_date = fields.Date(
        string='Fecha de Emisión',
        related='move_id.invoice_date',
        store=True,
    )
    base_imponible = fields.Monetary(
        string='Base Imponible',
        currency_field='currency_id',
    )
    itbms_causado = fields.Monetary(
        string='ITBMS Causado',
        currency_field='currency_id',
    )
    itbms_retenido = fields.Monetary(
        string='ITBMS Retenido',
        currency_field='currency_id',
    )
    total_a_pagar = fields.Monetary(
        string='Total a Pagar',
        compute='_compute_total',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='withholding_id.currency_id',
        store=True,
    )

    @api.depends('base_imponible', 'itbms_causado', 'itbms_retenido')
    def _compute_total(self):
        for line in self:
            line.total_a_pagar = line.base_imponible + line.itbms_causado - line.itbms_retenido

    @api.onchange('move_id')
    def _onchange_move_id(self):
        """Auto-fill amounts from the selected invoice."""
        if self.move_id:
            self.base_imponible = self.move_id.amount_untaxed
            
            # Calculate positive taxes (Causado) and negative taxes (Retenido)
            itbms_causado = 0.0
            itbms_retenido = 0.0
            for line in self.move_id.invoice_line_ids:
                for tax in line.tax_ids:
                    if tax.amount > 0:
                        itbms_causado += (line.price_subtotal * tax.amount / 100)
                    elif tax.amount < 0:
                        itbms_retenido += abs(line.price_subtotal * tax.amount / 100)
            
            self.itbms_causado = itbms_causado if itbms_retenido else (abs(self.move_id.amount_tax) if self.move_id.amount_tax > 0 else 0.0)
            self.itbms_retenido = itbms_retenido
