# -*- coding: utf-8 -*-

from datetime import timedelta
import pytz
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DigiflexCountInventory(models.Model):
    _name = 'digiflex.count.inventory'
    _description = 'Conteo de Inventario Cuantitativo'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Referencia',
        required=True,
        readonly=True,
        default=lambda self: _('Nuevo'),
        copy=False,
        tracking=True,
    )
    date = fields.Date(
        string='Fecha del Conteo',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    sales_target_date = fields.Date(
        string='Fecha de Entregas a Contar',
        default=lambda self: fields.Date.today() - timedelta(days=1),
        help='Fecha de referencia para auditar los productos físicamente entregados/despachados por Almacén ese día específico (ej. Sábado si se cuenta el Lunes).',
        tracking=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Ubicación',
        required=True,
        domain="[('usage', '=', 'internal')]",
        help='Ubicación física donde se realiza el conteo de inventario.',
        tracking=True,
    )
    count_type = fields.Selection(
        selection=[
            ('daily', 'Cíclico Diario (Entregados por Fecha)'),
            ('monthly', 'Todos los Productos'),
        ],
        string='Tipo de Conteo',
        required=True,
        default='daily',
        tracking=True,
    )
    employee_ids = fields.Many2many(
        'hr.employee',
        'digiflex_count_inventory_employee_rel',
        'count_id',
        'employee_id',
        string='Personal Responsable',
        domain="[('count_inventory_available', '=', True)]",
        tracking=True,
    )
    hide_theoretical_qty = fields.Boolean(
        string='Conteo a Ciegas',
        default=False,
        help='Si está activo, las cantidades teóricas esperadas estarán ocultas durante la carga del conteo.',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('in_progress', 'En Conteo'),
            ('closed', 'Cerrado'),
            ('cancelled', 'Cancelado'),
        ],
        string='Estado',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    adjustment_applied = fields.Boolean(
        string='Ajuste Aplicado',
        default=False,
        copy=False,
        tracking=True,
    )
    line_ids = fields.One2many(
        'digiflex.count.inventory.line',
        'inventory_id',
        string='Líneas de Conteo',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Administrador / Creador',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    total_items = fields.Integer(
        string='Total Productos',
        compute='_compute_summary_counters',
    )
    total_differences = fields.Integer(
        string='Total Diferencias',
        compute='_compute_summary_counters',
    )

    @api.depends('line_ids', 'line_ids.difference_qty')
    def _compute_summary_counters(self):
        for rec in self:
            rec.total_items = len(rec.line_ids)
            rec.total_differences = len(rec.line_ids.filtered(lambda l: abs(l.difference_qty) > 0.0001))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                seq = self.env['ir.sequence'].next_by_code('digiflex.count.inventory')
                vals['name'] = seq or self.env['ir.sequence'].next_by_code('stock.quant.package') or _('CNT/%s') % fields.Date.today().strftime('%Y%m%d')
        return super(DigiflexCountInventory, self).create(vals_list)

    def action_start(self):
        self.ensure_one()
        if not self.location_id:
            raise UserError(_('Debe seleccionar una ubicación de inventario.'))

        # Limpiar líneas previas en borrador
        self.line_ids.unlink()

        products_to_count = self.env['product.product']

        if self.count_type == 'daily':
            # Usar la fecha de ventas seleccionada por el supervisor (sales_target_date)
            target_date = self.sales_target_date or (self.date - timedelta(days=1))
            user_tz = self.env.user.tz or self.env.context.get('tz') or 'UTC'
            try:
                tz = pytz.timezone(user_tz)
            except Exception:
                tz = pytz.UTC

            dt_start_local = tz.localize(fields.Datetime.to_datetime(target_date).replace(hour=0, minute=0, second=0))
            dt_end_local = tz.localize(fields.Datetime.to_datetime(target_date).replace(hour=23, minute=59, second=59))
            date_start = dt_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
            date_end = dt_end_local.astimezone(pytz.UTC).replace(tzinfo=None)

            moves = self.env['stock.move'].search([
                ('state', '=', 'done'),
                ('date', '>=', date_start),
                ('date', '<=', date_end),
                ('location_id', '=', self.location_id.id),
                ('location_dest_id.usage', '=', 'customer'),
            ])
            products_to_count = moves.mapped('product_id').filtered(lambda p: p.type == 'product')

            # Fallback 1: Si no hay entregas registradas en esa fecha objetivo, buscar en la fecha actual de conteo
            if not products_to_count:
                dt_start_today = tz.localize(fields.Datetime.to_datetime(self.date).replace(hour=0, minute=0, second=0))
                dt_end_today = tz.localize(fields.Datetime.to_datetime(self.date).replace(hour=23, minute=59, second=59))
                date_start_today = dt_start_today.astimezone(pytz.UTC).replace(tzinfo=None)
                date_end_today = dt_end_today.astimezone(pytz.UTC).replace(tzinfo=None)
                moves_today = self.env['stock.move'].search([
                    ('state', '=', 'done'),
                    ('date', '>=', date_start_today),
                    ('date', '<=', date_end_today),
                    ('location_id', '=', self.location_id.id),
                    ('location_dest_id.usage', '=', 'customer'),
                ])
                products_to_count = moves_today.mapped('product_id').filtered(lambda p: p.type == 'product')

            # Fallback 2: Productos con stock físico en la ubicación
            if not products_to_count:
                quants = self.env['stock.quant'].search([
                    ('location_id', '=', self.location_id.id),
                    ('quantity', '>', 0),
                ])
                products_to_count = quants.mapped('product_id')

            if not products_to_count:
                products_to_count = self.env['product.product'].search([
                    ('type', '=', 'product'),
                    ('active', '=', True),
                ], limit=100)

        elif self.count_type == 'monthly':
            # Todos los productos almacenables (storable)
            quants = self.env['stock.quant'].search([
                ('location_id', '=', self.location_id.id),
                ('quantity', '>', 0),
            ])
            products_with_stock = quants.mapped('product_id')

            all_storable = self.env['product.product'].search([
                ('type', '=', 'product'),
                ('active', '=', True),
            ])
            products_to_count = products_with_stock | all_storable

        if not products_to_count:
            products_to_count = self.env['product.product'].search([
                ('type', '=', 'product'),
                ('active', '=', True),
            ], limit=50)

        line_vals = []
        for idx, product in enumerate(products_to_count):
            qty_available = product.with_context(location=self.location_id.id).qty_available

            line_vals.append({
                'inventory_id': self.id,
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'theoretical_qty': qty_available,
                'counted_qty': 0.0,
                'is_counted': False,
                'assigned_employee_id': False,
                'notes': '',
            })

        self.env['digiflex.count.inventory.line'].create(line_vals)
        self.state = 'in_progress'

        # Generar actividad en Odoo para los operadores/empleados asignados
        self.action_schedule_activities()
        return True

    def action_schedule_activities(self):
        for rec in self:
            users_to_assign = rec.employee_ids.mapped('user_id')
            if not users_to_assign:
                users_to_assign = rec.env.user

            activity_type = rec.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            activity_type_id = activity_type.id if activity_type else False

            for user in users_to_assign:
                existing = rec.env['mail.activity'].search([
                    ('res_model', '=', rec._name),
                    ('res_id', '=', rec.id),
                    ('user_id', '=', user.id),
                ])
                if not existing:
                    rec.activity_schedule(
                        activity_type_id=activity_type_id,
                        summary=_('Conteo de Inventario Asignado: %s') % rec.name,
                        note=_('Tiene asignado el conteo de inventario en la ubicación %s.') % rec.location_id.complete_name,
                        user_id=user.id,
                        date_deadline=rec.date,
                    )

    def action_finish_operator_count(self, employee_id=False):
        """
        Permite a un colaborador registrar la finalización de sus productos asignados.
        Si todos los productos de la sesión fueron contados, cierra la sesión de forma automática.
        De lo contrario, mantiene la sesión abierta para otros operadores o productos pendientes.
        """
        self.ensure_one()
        employee = self.env['hr.employee'].browse(employee_id) if employee_id else False
        emp_name = employee.name if employee else self.env.user.name

        if employee:
            emp_lines = self.line_ids.filtered(lambda l: l.assigned_employee_id == employee)
        else:
            emp_lines = self.line_ids

        total_emp = len(emp_lines)
        counted_emp = len(emp_lines.filtered(lambda l: l.is_counted))

        self.message_post(
            body=Markup("<p><strong style='color:#16a34a;'>Conteo Individual Finalizado:</strong> El colaborador <strong>%s</strong> ha finalizado el conteo de sus productos (%s de %s contados).</p>") % (emp_name, counted_emp, total_emp)
        )

        uncounted_lines = self.line_ids.filtered(lambda l: not l.is_counted)
        if not uncounted_lines:
            self.action_create_stock_quant_adjustment()
            self.state = 'closed'
            activities = self.env['mail.activity'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
            ])
            if activities:
                activities.action_done()
            self.message_post(
                body=Markup("<p><strong>¡Sesión Completada!</strong> Se ha completado el 100% de los conteos. La sesión ha sido cerrada automáticamente.</p>")
            )
            return {'all_counted': True, 'state': 'closed', 'remaining_uncounted': 0}

        return {'all_counted': False, 'state': 'in_progress', 'remaining_uncounted': len(uncounted_lines)}

    def action_close(self):
        self.ensure_one()
        uncounted = len(self.line_ids.filtered(lambda l: not l.is_counted))
        self.action_create_stock_quant_adjustment()
        self.state = 'closed'
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ])
        if activities:
            activities.action_done()

        if uncounted > 0:
            self.message_post(
                body=Markup("<p><strong style='color:#d97706;'>Cierre Administrativo de Sesión:</strong> Sesión cerrada administrativamente por %s con <strong>%s productos sin contar</strong>.</p>") % (self.env.user.name, uncounted)
            )
        else:
            self.message_post(
                body=Markup("<p><strong>Cierre de Sesión:</strong> La sesión fue cerrada exitosamente con el 100% de los productos contados.</p>")
            )
        return True

    def unlink(self):
        for rec in self:
            if not self.env.user.has_group('stock.group_stock_manager') and not self.env.user.has_group('base.group_system'):
                raise UserError(_("No tiene permisos para eliminar sesiones de conteo de inventario. Solo un Administrador de Almacén puede realizar esta acción."))
            if rec.state == 'closed' and not self.env.is_superuser():
                raise UserError(_("No se puede eliminar una sesión de conteo que ya se encuentra cerrada."))
        return super(DigiflexCountInventory, self).unlink()

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ])
        if activities:
            activities.unlink()
        return True

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('digiflex_count_inventory.action_report_count_inventory').report_action(self)

    def action_create_stock_quant_adjustment(self):
        """
        Registra un resumen detallado de diferencias en el Chatter de la sesión sin aplicar movimientos de stock.
        Indica explícitamente que los ajustes físicos y la asignación de seriales/lotes deben realizarse
        mediante el módulo nativo de Ajustes de Inventario de Odoo.
        """
        for rec in self:
            if rec.adjustment_applied:
                rec.message_post(body=Markup("<p><strong>Aviso:</strong> El resumen de diferencias para esta sesión ya fue registrado en el Chatter previamente.</p>"))
                continue

            diff_lines = rec.line_ids.filtered(lambda l: l.is_counted and abs(l.difference_qty) > 0.0001)
            if not diff_lines:
                rec.message_post(body=Markup("<p><strong>Información del Conteo:</strong> No se encontraron diferencias entre las cantidades contadas y las cantidades teóricas.</p>"))
                rec.adjustment_applied = True
                continue

            standard_summary = []
            serialized_summary = []

            for line in diff_lines:
                product = line.product_id
                summary_item = _(
                    "• <strong>%s</strong> [%s]: Teórica: %s | Contada: %s | Diferencia: <strong>%s %s</strong>"
                ) % (
                    product.display_name,
                    product.default_code or '-',
                    line.theoretical_qty,
                    line.counted_qty,
                    line.difference_qty,
                    line.product_uom_id.name
                )

                if product.tracking == 'none':
                    standard_summary.append(summary_item)
                else:
                    serialized_summary.append(summary_item + _(" (Requiere asignación de Lote/Serial en Odoo nativo)"))

            rec.adjustment_applied = True

            msg_parts = ["<p><strong>Resumen de Diferencias de Conteo Auditadas:</strong></p>"]
            if standard_summary:
                msg_parts.append("<p><strong>Productos Estándar con Diferencia:</strong></p><ul>")
                for item in standard_summary:
                    msg_parts.append("<li>%s</li>" % item)
                msg_parts.append("</ul>")

            if serialized_summary:
                msg_parts.append("<p><strong style='color: #0284c7;'>Productos Serializados / Con Lote con Diferencia:</strong></p><ul>")
                for item in serialized_summary:
                    msg_parts.append("<li>%s</li>" % item)
                msg_parts.append("</ul>")

            msg_parts.append(
                "<p><strong style='color: #d97706;'>Nota Operativa:</strong> Este módulo registra únicamente el resultado de la auditoría de conteo. "
                "Para actualizar las cantidades físicas e ingresar o desincorporar los números de serie/lote correspondientes, "
                "utilice el módulo nativo de <strong>Ajustes de Inventario de Odoo</strong> (Inventario -&gt; Operaciones -&gt; Ajustes de Inventario).</p>"
            )

            rec.message_post(body=Markup("".join(msg_parts)))

        return True

    def action_open_assign_wizard(self):
        self.ensure_one()
        return {
            'name': _('Asignación Masiva de Operadores'),
            'type': 'ir.actions.act_window',
            'res_model': 'digiflex.count.inventory.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_inventory_id': self.id,
            }
        }

    # -------------------------------------------------------------------------
    # API RPC Methods for OWL Interface
    # -------------------------------------------------------------------------
    @api.model
    def get_initial_data(self):
        company_ids = self.env.companies.ids

        locations = self.env['stock.location'].search_read(
            [
                ('usage', '=', 'internal'),
                '|', ('company_id', '=', False), ('company_id', 'in', company_ids)
            ],
            ['id', 'name', 'complete_name']
        )

        employee_records = self.env['hr.employee'].search([
            ('count_inventory_available', '=', True),
            '|', ('company_id', '=', False), ('company_id', 'in', company_ids)
        ])

        employees = []
        for emp in employee_records:
            employees.append({
                'id': emp.id,
                'name': emp.name,
            })

        is_manager = bool(self.env.user.has_group('digiflex_count_inventory.group_count_inventory_manager'))

        domain = [
            ('state', 'in', ['draft', 'in_progress']),
            '|', ('company_id', '=', False), ('company_id', 'in', company_ids)
        ]

        active_session_records = self.search(domain, order='id desc', limit=50)

        active_sessions = []
        for s in active_session_records:
            active_sessions.append({
                'id': s.id,
                'name': s.name,
                'date': fields.Date.to_string(s.date),
                'sales_target_date': fields.Date.to_string(s.sales_target_date or (s.date - timedelta(days=1))),
                'location_id': s.location_id.id,
                'location_name': s.location_id.complete_name,
                'count_type': s.count_type,
                'hide_theoretical_qty': s.hide_theoretical_qty,
                'state': s.state,
                'total_items': s.total_items,
                'total_differences': s.total_differences,
                'employees': [{'id': e.id, 'name': e.name} for e in s.employee_ids],
            })

        return {
            'locations': locations,
            'employees': employees,
            'active_sessions': active_sessions,
            'activeSessions': active_sessions,
            'is_manager': is_manager,
        }

    @api.model
    def verify_employee_pin(self, employee_id, pin):
        """
        Valida el PIN de 4 dígitos del empleado de forma segura en el servidor.
        evitando exponer los PINs en el cliente JavaScript.
        """
        if not employee_id:
            return False
        emp = self.env['hr.employee'].browse(int(employee_id))
        if not emp.exists():
            return False

        expected_pin = (emp.count_pin or getattr(emp, 'pin', False) or '').strip()
        entered_pin = str(pin or '').strip()

        if not expected_pin:
            return True
        return expected_pin == entered_pin

    @api.model
    def create_session_from_owl(self, location_id, count_type, hide_theoretical_qty, employee_ids, date=False, sales_target_date=False):
        emp_ids = [int(e) for e in employee_ids] if employee_ids else []
        location = self.env['stock.location'].browse(int(location_id))
        session = self.create({
            'location_id': location.id,
            'count_type': count_type,
            'hide_theoretical_qty': hide_theoretical_qty,
            'employee_ids': [(6, 0, emp_ids)] if emp_ids else [],
            'date': date or fields.Date.today(),
            'sales_target_date': sales_target_date or (fields.Date.today() - timedelta(days=1)),
            'company_id': location.company_id.id if location.company_id else self.env.company.id,
        })
        session.action_start()
        return session.get_session_details()

    def get_session_details(self):
        self.ensure_one()
        lines = []
        for line in self.line_ids:
            lines.append({
                'id': line.id,
                'product_id': line.product_id.id,
                'product_name': line.product_id.display_name,
                'default_code': line.product_id.default_code or '',
                'barcode': line.product_id.barcode or '',
                'uom_name': line.product_uom_id.name,
                'theoretical_qty': line.theoretical_qty,
                'counted_qty': line.counted_qty,
                'difference_qty': line.difference_qty,
                'difference_state': line.difference_state,
                'is_counted': line.is_counted,
                'assigned_employee_id': line.assigned_employee_id.id if line.assigned_employee_id else False,
                'assigned_employee_name': line.assigned_employee_id.name if line.assigned_employee_id else '',
                'notes': line.notes or '',
            })
        return {
            'id': self.id,
            'name': self.name,
            'date': fields.Date.to_string(self.date),
            'sales_target_date': fields.Date.to_string(self.sales_target_date or (self.date - timedelta(days=1))),
            'location_id': self.location_id.id,
            'location_name': self.location_id.complete_name,
            'count_type': self.count_type,
            'hide_theoretical_qty': self.hide_theoretical_qty,
            'state': self.state,
            'total_items': self.total_items,
            'total_differences': self.total_differences,
            'employees': [{'id': e.id, 'name': e.name} for e in self.employee_ids],
            'lines': lines,
        }

    @api.model
    def save_session_lines_owl(self, session_id, lines_data):
        session = self.browse(session_id)
        if not session.exists() or session.state in ['closed', 'cancelled']:
            raise UserError(_('La sesión de conteo no está activa o fue cerrada.'))

        line_obj = self.env['digiflex.count.inventory.line']
        for data in lines_data:
            line = line_obj.browse(data.get('id'))
            if line.exists() and line.inventory_id.id == session.id:
                vals = {
                    'counted_qty': float(data.get('counted_qty', 0.0)),
                    'notes': data.get('notes', ''),
                }
                if 'is_counted' in data:
                    vals['is_counted'] = bool(data['is_counted'])
                elif 'counted_qty' in data:
                    vals['is_counted'] = True
                if 'assigned_employee_id' in data:
                    emp_id = int(data['assigned_employee_id']) if data['assigned_employee_id'] else False
                    vals['assigned_employee_id'] = emp_id
                    if emp_id and emp_id not in session.employee_ids.ids:
                        session.write({'employee_ids': [(4, emp_id)]})
                line.write(vals)

        return session.get_session_details()

    @api.model
    def close_session_owl(self, session_id):
        session = self.browse(session_id)
        if session.exists():
            session.action_close()
            return session.get_session_details()
        return False
