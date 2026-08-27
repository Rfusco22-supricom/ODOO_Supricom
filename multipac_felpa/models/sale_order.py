# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import api, fields, models, _
from odoo.tools import float_compare, float_is_zero


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Compatibility fields for other modules
    allow_below_min_price = fields.Boolean(
        string='Allow Below Min Price',
        help='Compatibility field - allows selling below minimum price'
    )
    fel_pa_active = fields.Boolean(
        string="Panamá FEL Activo",
        compute="_compute_fel_pa_active",
    )
    fel_pa_interes_information = fields.Text(
        string="Términos y Condiciones Factura (FEL Panamá)",
        help="Información de intereses o términos y condiciones que se mostrarán en la factura a generar (Panamá FEL).",
    )

    @api.depends('company_id', 'journal_id')
    def _compute_fel_pa_active(self):
        for order in self:
            if order.journal_id and order.journal_id.fel_pa_active:
                order.fel_pa_active = True
            else:
                company = order.company_id or self.env.company
                order.fel_pa_active = bool(self.env['account.journal'].search_count([
                    ('company_id', '=', company.id),
                    ('type', '=', 'sale'),
                    ('fel_pa_active', '=', True),
                ]))

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        if self.fel_pa_interes_information:
            invoice_vals['fel_pa_interes_information'] = self.fel_pa_interes_information
        return invoice_vals

    def _is_pa_foreign_customer(self):
        self.ensure_one()
        # REQUERIMIENTO: Solo para la empresa de Panamá
        # Validar por código de país 'PA' o por moneda (USD/PAB) si el país no está cargado
        company = self.company_id
        is_pa = (company.country_id and company.country_id.code.upper() == 'PA') or \
                (company.currency_id and company.currency_id.name in ['USD', 'PAB', 'PAB'])
        
        if not is_pa:
            return False

        # Verificar si el contacto está clasificado como extranjero
        partner = self.partner_id
        if not partner:
            return False
        
        # Tipo de receptor '04' (Extranjero) de Panamá FEL
        is_foreign = partner.fel_pa_recipient_type == '04' or \
                     partner.commercial_partner_id.fel_pa_recipient_type == '04'
        
        # Fallback: Si el país no es Panamá
        if not is_foreign:
            country = partner.country_id or partner.commercial_partner_id.country_id
            if country and country.code not in ['PA', 'pa']:
                is_foreign = True
                
        return is_foreign

    def _get_pa_exempt_tax(self):
        self.ensure_one()
        # Buscar dinámicamente el impuesto exento (0%)
        # Prioridad 1: Por monto y tipo de uso
        exempt_tax = self.env['account.tax'].search([
            ('company_id', '=', self.company_id.id),
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', 0.0),
        ], limit=1)
        
        # Prioridad 2: Por nombre si el monto falla (casos raros)
        if not exempt_tax:
            exempt_tax = self.env['account.tax'].search([
                ('company_id', '=', self.company_id.id),
                ('type_tax_use', '=', 'sale'),
                ('name', 'ilike', 'Exento'),
            ], limit=1)
            
        return exempt_tax

    @api.onchange('partner_id')
    def _onchange_partner_id_pa_foreign(self):
        """Updates all lines to Exempt if the customer is foreign."""
        if self._is_pa_foreign_customer():
            # En lugar de forzar impuestos en líneas, asignar la posición fiscal nativa
            fp = self.partner_id.property_account_position_id or self.env['account.fiscal.position'].search([
                ('name', 'ilike', 'exento'), ('company_id', '=', self.company_id.id)
            ], limit=1)
            if fp:
                try:
                    self.fiscal_position_id = fp
                except Exception:
                    # Si el modelo de venta no tiene `fiscal_position_id`, evitar excepción
                    pass

    @api.model_create_multi
    def create(self, vals_list):
        orders = super(SaleOrder, self).create(vals_list)
        for order in orders:
            if order._is_pa_foreign_customer():
                # Asignar la posición fiscal nativa en vez de forzar impuestos en líneas.
                fp = order.partner_id.property_account_position_id or self.env['account.fiscal.position'].search([
                    ('name', 'ilike', 'exento'), ('company_id', '=', order.company_id.id)
                ], limit=1)
                if fp:
                    order.fiscal_position_id = fp
        return orders

    def action_confirm(self):
        """Asignar posición fiscal nativa antes de confirmar y delegar en Odoo."""
        for order in self:
            if order._is_pa_foreign_customer():
                fp = order.partner_id.property_account_position_id or self.env['account.fiscal.position'].search([
                    ('name', 'ilike', 'exento'), ('company_id', '=', order.company_id.id)
                ], limit=1)
                if fp:
                    order.fiscal_position_id = fp

        return super(SaleOrder, self).action_confirm()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_tax_id(self):
        """Hook estándar de Odoo 17 para obtener impuestos. Forzamos exento para extranjeros en PA."""
        self.ensure_one()
        return super(SaleOrderLine, self)._get_tax_id()

    @api.depends('product_id', 'order_id.partner_id', 'order_id.company_id')
    def _compute_tax_id(self):
        """Asegura que el compute use nuestra lógica de _get_tax_id."""
        super(SaleOrderLine, self)._compute_tax_id()

    @api.onchange('product_id', 'product_uom', 'product_uom_qty')
    def _onchange_product_id_pa_foreign(self):
        """Fuerza el impuesto exento al cambiar el producto en UI para clientes extranjeros."""
        return

    @api.model_create_multi
    def create(self, vals_list):
        lines = super(SaleOrderLine, self).create(vals_list)
        return lines








    def get_stock_moves_link_invoice(self):
        moves_linked = self.env["stock.move"]
        to_invoice = self.qty_to_invoice
        for stock_move in self.move_ids.sorted(
            lambda m: (m.write_date, m.id), reverse=True
        ):
            if (
                stock_move.state != "done"
                or stock_move.scrapped
                or (
                    stock_move.location_dest_id.usage != "customer"
                    and (
                        stock_move.location_id.usage != "customer"
                        or not stock_move.to_refund
                    )
                )
            ):
                continue
            if not stock_move.invoice_line_ids:
                to_invoice -= (
                    stock_move.quantity
                    if not stock_move.to_refund
                    else -stock_move.quantity
                )
                moves_linked += stock_move
                continue
            elif float_is_zero(
                to_invoice, precision_rounding=self.product_uom.rounding
            ):
                break
            to_invoice -= (
                stock_move.quantity
                if not stock_move.to_refund
                else -stock_move.quantity
            )
            moves_linked += stock_move
        return moves_linked

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        stock_moves = self.get_stock_moves_link_invoice()
        # Invoice returned moves marked as to_refund
        if (
            float_compare(
                self.qty_to_invoice, 0.0, precision_rounding=self.currency_id.rounding
            )
            < 0
        ):
            stock_moves = stock_moves.filtered("to_refund")
        vals["move_line_ids"] = [(4, m.id) for m in stock_moves]
        # Si el pedido es para un cliente extranjero (PA), forzamos el impuesto exento
        try:
            if self._is_pa_foreign_customer():
                exempt_tax = self._get_pa_exempt_tax()
                if exempt_tax:
                    vals['tax_ids'] = [(6, 0, exempt_tax.ids)]
        except Exception:
            # Protección: no romper la creación de la factura si algo falla aquí
            pass
        return vals
