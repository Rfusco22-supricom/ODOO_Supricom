from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SpiffCalculation(models.Model):
    _name = 'spiff.calculation'
    _description = 'Cálculo de SPIFF'
    _order = 'calculation_date desc'

    name = fields.Char(string="Referencia", required=True, default=lambda self: _('Nuevo'))
    calculation_date = fields.Date(default=fields.Date.today, readonly=True)
    period_start = fields.Date(string="Inicio Periodo", required=True)
    period_end = fields.Date(string="Fin Periodo", required=True)

    line_ids = fields.One2many('spiff.calculation.line', 'calculation_id', string="Resultados")
    state = fields.Selection([('draft', 'Borrador'), ('done', 'Calculado')], default='draft')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    def action_calculate(self):
        self.ensure_one()
        # Limpiar cálculos previos si se recalcula
        self.line_ids.unlink()

        # 1. Buscar Líneas de Factura (Publicadas, Facturas y Rectificativas)
        domain = [
            ('move_id.state', '=', 'posted'),
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('move_id.invoice_date', '>=', self.period_start),
            ('move_id.invoice_date', '<=', self.period_end),
            ('display_type', '=', 'product')
        ]
        all_lines = self.env['account.move.line'].search(domain)

        # 2. Buscar Reglas Activas para el periodo
        rules = self.env['spiff.incentive'].search([
            ('start_date', '<=', self.period_end),
            ('end_date', '>=', self.period_start),
            ('active', '=', True)
        ])

        # Clave: (user_id, rule_id) → {'qty', 'amount', 'rule', 'detail_lines': []}
        results = {}

        # 3. Procesar Datos — guardar detalle por línea de factura
        for line in all_lines:
            salesperson = line.move_id.invoice_user_id
            if not salesperson:
                continue

            sign = -1 if line.move_id.move_type == 'out_refund' else 1
            qty = line.quantity * sign
            amount = line.price_subtotal * sign

            for rule in rules:
                is_match = False

                if rule.rule_type == 'product' and rule.product_id == line.product_id:
                    is_match = True
                elif rule.rule_type == 'brand' and rule.brand_id:
                    if line.product_id.spiff_brand_id and line.product_id.spiff_brand_id.id == rule.brand_id.id:
                        is_match = True

                if is_match:
                    key = (salesperson.id, rule.id)
                    if key not in results:
                        results[key] = {
                            'qty': 0.0,
                            'amount': 0.0,
                            'rule': rule,
                            'detail_lines': [],
                        }
                    results[key]['qty'] += qty
                    results[key]['amount'] += amount

                    # Guardar detalle por línea individual
                    results[key]['detail_lines'].append({
                        'invoice_id': line.move_id.id,
                        'invoice_date': line.move_id.invoice_date,
                        'partner_id': line.move_id.partner_id.id,
                        'product_id': line.product_id.id,
                        'quantity': qty,
                        'amount_sold': amount,
                        'rule_id': rule.id,
                    })

        # 4. Generar Líneas de Resultado con sus detalless
        for (user_id, rule_id), data in results.items():
            rule = data['rule']
            payout = 0.0

            if rule.rule_type == 'product':
                if data['qty'] > 0:
                    payout = data['qty'] * rule.incentive_per_unit
            elif rule.rule_type == 'brand':
                if data['amount'] > 0 and rule.target_amount > 0:
                    blocks = int(data['amount'] // rule.target_amount)
                    payout = blocks * rule.incentive_amount

            if payout > 0:
                detail_vals = [(0, 0, {
                    'invoice_id': d['invoice_id'],
                    'invoice_date': d['invoice_date'],
                    'partner_id': d['partner_id'],
                    'product_id': d['product_id'],
                    'quantity': d['quantity'],
                    'amount_sold': d['amount_sold'],
                    'rule_id': d['rule_id'],
                }) for d in data['detail_lines']]

                self.env['spiff.calculation.line'].create({
                    'calculation_id': self.id,
                    'user_id': user_id,
                    'rule_id': rule_id,
                    'total_quantity': data['qty'],
                    'total_amount_sold': data['amount'],
                    'spiff_amount': payout,
                    'detail_ids': detail_vals,
                })

        self.state = 'done'

    def action_view_detail(self):
        """Acción de botón para ver todas las líneas de detalle de este cálculo."""
        self.ensure_one()
        detail_ids = self.line_ids.mapped('detail_ids').ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'Detalle SPIFF — {self.name}',
            'res_model': 'spiff.calculation.line.detail',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', detail_ids)],
            'context': {'search_default_group_by_rule': 1},
        }


class SpiffCalculationLine(models.Model):
    _name = 'spiff.calculation.line'
    _description = 'Línea de Resultado SPIFF'

    calculation_id = fields.Many2one('spiff.calculation', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', string="Vendedor", required=True)
    rule_id = fields.Many2one('spiff.incentive', string="Regla Aplicada")

    total_quantity = fields.Float(string="Cant. Neta")
    total_amount_sold = fields.Monetary(string="Monto Neto Vendido")
    spiff_amount = fields.Monetary(string="Pago SPIFF")

    currency_id = fields.Many2one('res.currency', related='calculation_id.company_id.currency_id')

    detail_ids = fields.One2many(
        'spiff.calculation.line.detail', 'line_id',
        string="Detalle por Factura"
    )


class SpiffCalculationLineDetail(models.Model):
    _name = 'spiff.calculation.line.detail'
    _description = 'Detalle SPIFF por Línea de Factura'
    _order = 'invoice_date desc'

    line_id = fields.Many2one(
        'spiff.calculation.line', string="Línea SPIFF",
        required=True, ondelete='cascade'
    )
    calculation_id = fields.Many2one(
        'spiff.calculation', string="Cálculo",
        related='line_id.calculation_id', store=True
    )
    user_id = fields.Many2one(
        'res.users', string="Vendedor",
        related='line_id.user_id', store=True
    )
    rule_id = fields.Many2one('spiff.incentive', string="Regla", required=True)

    # Trazabilidad a la factura individual
    invoice_id = fields.Many2one('account.move', string="Factura")
    invoice_date = fields.Date(string="Fecha")
    partner_id = fields.Many2one('res.partner', string="Cliente")
    product_id = fields.Many2one('product.product', string="Producto")
    quantity = fields.Float(string="Cantidad")
    amount_sold = fields.Monetary(string="Monto Vendido")

    currency_id = fields.Many2one(
        'res.currency',
        related='line_id.calculation_id.company_id.currency_id'
    )
