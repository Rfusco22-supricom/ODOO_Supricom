from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HrPayrollReportWizard(models.TransientModel):
    _name = 'hr.payroll.report.wizard'
    _description = 'Asistente de Reportes de Nómina'

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
    )
    struct_ids = fields.Many2many(
        'hr.payroll.structure',
        'hr_payroll_wizard_struct_rel',
        'wizard_id',
        'struct_id',
        string='Estructuras Salariales',
        required=True,
    )
    report_type = fields.Selection([
        ('detailed', 'Detallado'),
        ('consolidated', 'Consolidado'),
    ], string='Tipo de Reporte', default='detailed', required=True)
    employee_ids = fields.Many2many(
        'hr.employee',
        'hr_payroll_wizard_employee_rel',
        'wizard_id',
        'employee_id',
        string='Empleados',
        help='Dejar vacío para incluir todos los empleados',
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        help='Filtrar por departamento específico',
    )
    favorite_id = fields.Many2one(
        'hr.payroll.report.favorite',
        string='Cargar Favorito',
        domain="[('user_id', '=', uid)]",
    )
    favorite_name = fields.Char(
        string='Nombre del Favorito',
    )
    deductible_as_positive = fields.Boolean(
        string='¿Mostrar deducibles en positivo?',
        default=False,
        help='Si se activa, los montos de reglas deducibles (negativos) '
             'se mostrarán como valores positivos en el reporte.',
    )
    salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_payroll_wizard_rule_rel',
        'wizard_id',
        'rule_id',
        string='Reglas Salariales',
        help='Seleccione una o más reglas salariales específicas. '
             'Si se seleccionan, se usarán estas reglas en vez de '
             'todas las reglas de las estructuras seleccionadas. '
             'Los montos de las reglas seleccionadas se sumarán para el informe.',
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Hecho'),
    ], default='draft')
    excel_file = fields.Binary('Reporte Excel')
    excel_filename = fields.Char('Nombre Archivo Excel')

    @api.onchange('favorite_id')
    def _onchange_favorite_id(self):
        """Load favorite configuration into wizard fields."""
        if self.favorite_id:
            self.struct_ids = self.favorite_id.struct_ids
            self.report_type = self.favorite_id.report_type
            self.department_id = self.favorite_id.department_id
            self.salary_rule_ids = self.favorite_id.salary_rule_ids
            self.deductible_as_positive = self.favorite_id.deductible_as_positive

    @api.onchange('struct_ids')
    def _onchange_struct_ids(self):
        """Limpiar reglas seleccionadas si ya no pertenecen a las estructuras."""
        if self.salary_rule_ids and self.struct_ids:
            valid_rules = self.struct_ids.mapped('rule_ids')
            self.salary_rule_ids = self.salary_rule_ids.filtered(
                lambda r: r in valid_rules
            )
        elif not self.struct_ids:
            self.salary_rule_ids = False

    @api.onchange('department_id')
    def _onchange_department_id(self):
        """Filter employees by department if set."""
        if self.department_id:
            return {
                'domain': {
                    'employee_ids': [
                        ('department_id', '=', self.department_id.id)
                    ]
                }
            }
        return {
            'domain': {
                'employee_ids': []
            }
        }

    def action_save_favorite(self):
        """Save the current configuration as a favorite."""
        self.ensure_one()
        if not self.favorite_name:
            raise UserError(_('Debe ingresar un nombre para el favorito.'))
        if not self.struct_ids:
            raise UserError(_(
                'Debe seleccionar al menos una estructura salarial '
                'para guardar como favorito.'
            ))

        name_stripped = self.favorite_name.strip()
        existing = self.env['hr.payroll.report.favorite'].search([
            ('name', '=ilike', name_stripped),
            ('user_id', '=', self.env.user.id),
        ], limit=1)

        if existing:
            raise UserError(_(
                'Ya existe un favorito guardado con el nombre "%s". '
                'Por favor utilice un nombre diferente.'
            ) % name_stripped)

        vals = {
            'name': name_stripped,
            'user_id': self.env.user.id,
            'struct_ids': [(6, 0, self.struct_ids.ids)],
            'salary_rule_ids': [(6, 0, self.salary_rule_ids.ids)],
            'report_type': self.report_type,
            'deductible_as_positive': self.deductible_as_positive,
            'department_id': self.department_id.id or False,
        }

        self.env['hr.payroll.report.favorite'].create(vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Favorito Guardado'),
                'message': _(
                    'La configuración "%s" se ha guardado correctamente.',
                    self.favorite_name,
                ),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'hr.payroll.report.wizard',
                    'views': [(False, 'form')],
                    'view_mode': 'form',
                    'target': 'new',
                    'res_id': self.id,
                },
            },
        }

    def action_generate_report(self):
        """Generate the payroll report based on wizard parameters."""
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_(
                'La fecha de inicio no puede ser mayor que la fecha de fin.'
            ))
        if not self.struct_ids:
            raise UserError(_(
                'Debe seleccionar al menos una estructura salarial.'
            ))

        # Get salary rules: use selected rules if any, otherwise all from structures
        if self.salary_rule_ids:
            salary_rules = self.salary_rule_ids
        else:
            salary_rules = self.struct_ids.mapped('rule_ids')
        
        # Build the domain to fetch payslip lines
        domain = [
            ('slip_id.date_from', '>=', self.date_from),
            ('slip_id.date_to', '<=', self.date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('salary_rule_id', 'in', salary_rules.ids),
        ]

        if self.employee_ids:
            domain.append(
                ('slip_id.employee_id', 'in', self.employee_ids.ids)
            )
        if self.department_id:
            domain.append(
                ('slip_id.employee_id.department_id', '=',
                 self.department_id.id)
            )

        payslip_lines = self.env['hr.payslip.line'].search(
            domain, order='slip_id, sequence'
        )

        if not payslip_lines:
            raise UserError(_(
                'No se encontraron datos para los parámetros seleccionados.\n'
                'Verifique que existan nóminas confirmadas en el período '
                'indicado con las reglas salariales seleccionadas.'
            ))

        # Prepare data for the report
        data = self._prepare_report_data(payslip_lines)
        data['docids'] = self.ids

        return self.env.ref(
            'hr_payroll_reports.action_report_payroll_rules'
        ).report_action(self, data=data)

    def action_generate_excel(self):
        """Generate the payroll report in Excel format."""
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_("La librería xlsxwriter no está instalada."))
            
        if self.date_from > self.date_to:
            raise UserError(_(
                'La fecha de inicio no puede ser mayor que la fecha de fin.'
            ))
        if not self.struct_ids:
            raise UserError(_(
                'Debe seleccionar al menos una estructura salarial.'
            ))

        if self.salary_rule_ids:
            salary_rules = self.salary_rule_ids
        else:
            salary_rules = self.struct_ids.mapped('rule_ids')
        domain = [
            ('slip_id.date_from', '>=', self.date_from),
            ('slip_id.date_to', '<=', self.date_to),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('salary_rule_id', 'in', salary_rules.ids),
        ]

        if self.employee_ids:
            domain.append(('slip_id.employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(('slip_id.employee_id.department_id', '=', self.department_id.id))

        payslip_lines = self.env['hr.payslip.line'].search(domain, order='slip_id, sequence')

        if not payslip_lines:
            raise UserError(_(
                'No se encontraron datos para los parámetros seleccionados.\n'
                'Verifique que existan nóminas confirmadas en el período '
                'indicado con las reglas salariales seleccionadas.'
            ))

        data = self._prepare_report_data(payslip_lines)
        
        # Create Excel file in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Reporte de Nómina')
        
        # Formats
        title_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_format = workbook.add_format({'bold': True, 'bg_color': '#d9edf7', 'border': 1})
        bold_format = workbook.add_format({'bold': True})
        money_format = workbook.add_format({'num_format': '#,##0.00'})
        money_bold_format = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#f0f0f0'})
        money_grand_total = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#d9edf7'})
        
        # Write Title
        sheet.merge_range(0, 0, 0, 5, 'Reporte de Estructuras Salariales', title_format)
        sheet.write(1, 0, f"Tipo: {data['report_type_label']}", bold_format)
        sheet.write(2, 0, f"Desde: {data['date_from']} Hasta: {data['date_to']}", bold_format)
        sheet.write(3, 0, f"Departamento: {data['department']}", bold_format)
        
        row = 5
        
        if self.report_type == 'detailed':
            headers = ['Empleado', 'Cédula/ID', 'Departamento', 'Regla Salarial', 'Código', 'Cantidad', 'Monto']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)
                sheet.set_column(col, col, 15)
            sheet.set_column(0, 0, 30)
            sheet.set_column(3, 3, 25)
            
            row += 1
            for emp in data['detail_lines']:
                start_row = row
                for rule in emp['rules']:
                    sheet.write(row, 0, emp['employee_name'])
                    sheet.write(row, 1, emp['employee_id'])
                    sheet.write(row, 2, emp['department'])
                    sheet.write(row, 3, rule['rule_name'])
                    sheet.write(row, 4, rule['rule_code'])
                    sheet.write(row, 5, rule['quantity'])
                    sheet.write(row, 6, rule['amount'], money_format)
                    row += 1
                
                sheet.write(row, 0, f"Subtotal {emp['employee_name']}:", bold_format)
                sheet.write(row, 6, emp['employee_total'], money_bold_format)
                row += 1
                
            sheet.write(row, 0, "TOTAL GENERAL:", bold_format)
            sheet.write(row, 6, data['grand_total'], money_grand_total)
            
        else: # consolidated
            headers = ['Regla Salarial', 'Código', 'Total Empleados', 'Monto Total']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)
                sheet.set_column(col, col, 20)
            sheet.set_column(0, 0, 30)
            
            row += 1
            for rule in data['consolidated_lines']:
                sheet.write(row, 0, rule['rule_name'])
                sheet.write(row, 1, rule['rule_code'])
                sheet.write(row, 2, rule['employee_count'])
                sheet.write(row, 3, rule['total_amount'], money_format)
                row += 1
                
            sheet.write(row, 0, "TOTAL GENERAL:", bold_format)
            sheet.write(row, 3, data['grand_total'], money_grand_total)
            
        workbook.close()
        output.seek(0)
        
        excel_data = base64.b64encode(output.read())
        
        self.write({
            'excel_file': excel_data,
            'excel_filename': f"Reporte_Nomina_{self.date_from}_{self.date_to}.xlsx",
            'state': 'done'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payroll.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.id,
        }

    def _prepare_report_data(self, payslip_lines):
        """Prepare data dictionary for the QWeb report template."""
        self.ensure_one()

        report_data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'report_type': self.report_type,
            'report_type_label': dict(
                self._fields['report_type'].selection
            ).get(self.report_type, ''),
            'salary_rules': [],
            'department': self.department_id.name or 'Todos',
            'print_date': fields.Datetime.now().strftime('%d/%m/%Y %H:%M'),
            'deductible_as_positive': self.deductible_as_positive,
        }

        if self.report_type == 'detailed':
            report_data.update(
                self._prepare_detailed_data(payslip_lines)
            )
        else:
            report_data.update(
                self._prepare_consolidated_data(payslip_lines)
            )

        return report_data

    def _prepare_detailed_data(self, payslip_lines):
        """Prepare detailed report data — one line per employee per rule."""
        lines = []
        grand_total = 0.0

        # Group by employee
        employees = payslip_lines.mapped('slip_id.employee_id')
        for employee in employees.sorted(key=lambda e: e.name):
            emp_lines = payslip_lines.filtered(
                lambda l: l.slip_id.employee_id == employee
            )
            employee_data = {
                'employee_name': employee.name,
                'employee_id': employee.identification_id or '',
                'department': employee.department_id.name or '',
                'rules': [],
                'employee_total': 0.0,
            }
            if self.salary_rule_ids:
                salary_rules = self.salary_rule_ids.sorted(
                    key=lambda r: r.sequence
                )
            else:
                salary_rules = self.struct_ids.mapped('rule_ids').sorted(
                    key=lambda r: r.sequence
                )
            for rule in salary_rules:
                rule_lines = emp_lines.filtered(
                    lambda l: l.salary_rule_id == rule
                )
                total = sum(rule_lines.mapped('total'))
                if self.deductible_as_positive:
                    total = abs(total)
                quantity = sum(rule_lines.mapped('quantity'))
                employee_data['rules'].append({
                    'rule_name': rule.name,
                    'rule_code': rule.code,
                    'quantity': quantity,
                    'amount': total,
                })
                employee_data['employee_total'] += total

            grand_total += employee_data['employee_total']
            lines.append(employee_data)

        return {
            'detail_lines': lines,
            'grand_total': grand_total,
            'salary_rules': [
                {'name': r.name, 'code': r.code}
                for r in (self.salary_rule_ids or self.struct_ids.mapped('rule_ids')).sorted(
                    key=lambda r: r.sequence
                )
            ],
        }

    def _prepare_consolidated_data(self, payslip_lines):
        """Prepare consolidated report data — grouped by salary rule."""
        rules_data = []
        grand_total = 0.0

        if self.salary_rule_ids:
            salary_rules = self.salary_rule_ids.sorted(
                key=lambda r: r.sequence
            )
        else:
            salary_rules = self.struct_ids.mapped('rule_ids').sorted(
                key=lambda r: r.sequence
            )
        for rule in salary_rules:
            rule_lines = payslip_lines.filtered(
                lambda l: l.salary_rule_id == rule
            )
            employees = rule_lines.mapped('slip_id.employee_id')
            total = sum(rule_lines.mapped('total'))
            if self.deductible_as_positive:
                total = abs(total)
            rules_data.append({
                'rule_name': rule.name,
                'rule_code': rule.code,
                'employee_count': len(employees),
                'total_amount': total,
            })
            grand_total += total

        return {
            'consolidated_lines': rules_data,
            'grand_total': grand_total,
        }
