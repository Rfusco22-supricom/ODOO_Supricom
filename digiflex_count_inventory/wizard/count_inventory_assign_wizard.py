# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DigiflexCountInventoryAssignWizard(models.TransientModel):
    _name = 'digiflex.count.inventory.assign.wizard'
    _description = 'Asignación Masiva de Operadores por Filtro'

    inventory_id = fields.Many2one(
        'digiflex.count.inventory',
        string='Sesión de Conteo',
        required=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Operador a Asignar',
        required=True,
        domain="[('count_inventory_available', '=', True)]",
    )
    search_text = fields.Char(
        string='Filtrar por Texto / Marca / Código',
        help='Ejemplo: "HP", "IMPRESORA", "CANON", "LAPTOP". Deja vacío para aplicar a todos los productos.',
    )
    categ_id = fields.Many2one(
        'product.category',
        string='Categoría de Producto',
    )
    only_unassigned = fields.Boolean(
        string='Solo productos sin operador asignado',
        default=False,
    )

    def action_apply_assignment(self):
        self.ensure_one()
        session = self.inventory_id
        if not session or session.state == 'closed':
            raise UserError(_('No se puede modificar una sesión de conteo cerrada.'))

        lines = session.line_ids

        if self.only_unassigned:
            lines = lines.filtered(lambda l: not l.assigned_employee_id)

        if self.categ_id:
            lines = lines.filtered(lambda l: l.product_id.categ_id.id == self.categ_id.id or l.product_id.categ_id.parent_path and str(self.categ_id.id) in l.product_id.categ_id.parent_path.split('/'))

        if self.search_text:
            query = self.search_text.strip().lower()
            lines = lines.filtered(lambda l: query in (l.product_id.display_name or '').lower() or query in (l.product_id.default_code or '').lower() or query in (l.product_id.barcode or '').lower())

        if not lines:
            raise UserError(_('No se encontraron líneas que coincidan con los criterios de búsqueda especificados.'))

        lines.write({'assigned_employee_id': self.employee_id.id})
        if self.employee_id.id not in session.employee_ids.ids:
            session.write({'employee_ids': [(4, self.employee_id.id)]})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Asignación Completada'),
                'message': _('Se asignaron %s productos a %s exitosamente.') % (len(lines), self.employee_id.name),
                'type': 'success',
                'sticky': False,
            }
        }
