{
    'name': 'Reportes de Nómina RRHH',
    'version': '17.0.1.0.0',
    'summary': 'Reportes de reglas salariales por período con vista detallada y consolidada',
    'description': """
        Módulo de reportes para el módulo de Nómina de Odoo 17.
        Permite generar reportes de reglas salariales por período,
        con opciones de vista detallada o consolidada.
        Incluye funcionalidad de guardar configuraciones como favoritos.
    """,
    'author': 'Ing. Leonardo Semprún',
    'category': 'Human Resources/Payroll',
    'depends': ['hr_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/hr_payroll_report_wizard_view.xml',
        'report/hr_payroll_report_action.xml',
        'report/hr_payroll_report_template.xml',
        'views/hr_payroll_report_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
