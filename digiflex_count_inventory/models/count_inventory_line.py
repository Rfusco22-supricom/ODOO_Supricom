# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class DigiflexCountInventoryLine(models.Model):
    _name = 'digiflex.count.inventory.line'
    _description = 'Línea de Conteo de Inventario Cuantitativo'
    _order = 'product_id, id'

    inventory_id = fields.Many2one(
        'digiflex.count.inventory',
        string='Sesión de Conteo',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        domain="[('type', '=', 'product')]",
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unidad de Medida',
        related='product_id.uom_id',
        store=True,
        readonly=True,
    )
    theoretical_qty = fields.Float(
        string='Cantidad Teórica',
        digits='Product Unit of Measure',
        default=0.0,
    )
    counted_qty = fields.Float(
        string='Cantidad Contada',
        digits='Product Unit of Measure',
        default=0.0,
    )
    is_counted = fields.Boolean(
        string='Contado',
        default=False,
    )
    difference_qty = fields.Float(
        string='Diferencia',
        digits='Product Unit of Measure',
        compute='_compute_difference',
        store=True,
    )
    difference_state = fields.Selection(
        selection=[
            ('match', 'Exacto'),
            ('missing', 'Faltante'),
            ('surplus', 'Sobrante'),
        ],
        string='Estado de Diferencia',
        compute='_compute_difference',
        store=True,
    )
    assigned_employee_id = fields.Many2one(
        'hr.employee',
        string='Operador Asignado',
        domain="[('count_inventory_available', '=', True)]",
    )
    notes = fields.Char(
        string='Observación',
    )

    @api.depends('theoretical_qty', 'counted_qty')
    def _compute_difference(self):
        for rec in self:
            diff = rec.counted_qty - rec.theoretical_qty
            rec.difference_qty = diff
            if abs(diff) < 0.0001:
                rec.difference_state = 'match'
            elif diff < 0:
                rec.difference_state = 'missing'
            else:
                rec.difference_state = 'surplus'

    def unlink(self):
        for rec in self:
            if not self.env.user.has_group('stock.group_stock_manager') and not self.env.user.has_group('base.group_system'):
                raise UserError(_("No tiene permisos para eliminar líneas de conteo de inventario. Solo un Administrador de Almacén puede realizar esta acción."))
            if rec.inventory_id.state in ('in_progress', 'closed') and not self.env.is_superuser():
                raise UserError(_("No se pueden eliminar líneas de conteo en una sesión en proceso o cerrada."))
        return super(DigiflexCountInventoryLine, self).unlink()
