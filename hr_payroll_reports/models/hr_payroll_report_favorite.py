from odoo import models, fields, api


class HrPayrollReportFavorite(models.Model):
    _name = 'hr.payroll.report.favorite'
    _description = 'Favoritos de Reportes de Nómina'
    _order = 'name'

    name = fields.Char(
        string='Nombre del Favorito',
        required=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.user,
        required=True,
    )
    struct_ids = fields.Many2many(
        'hr.payroll.structure',
        'hr_payroll_fav_structure_rel',
        'favorite_id',
        'struct_id',
        string='Estructuras Salariales',
    )
    salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_payroll_fav_rule_rel',
        'favorite_id',
        'rule_id',
        string='Reglas Salariales',
    )
    report_type = fields.Selection([
        ('detailed', 'Detallado'),
        ('consolidated', 'Consolidado'),
    ], string='Tipo de Reporte', default='detailed')
    department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
    )
    deductible_as_positive = fields.Boolean(
        string='¿Mostrar deducibles en positivo?',
        default=False,
    )

    _sql_constraints = [
        ('name_user_uniq', 'unique(name, user_id)',
         'Ya existe un favorito con este nombre para este usuario.'),
    ]
