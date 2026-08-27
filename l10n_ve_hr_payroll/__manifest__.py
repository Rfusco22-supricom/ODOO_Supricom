# -*- coding: utf-8 -*-
{
    'name': 'Localización Venezuela - Nómina RRHH',
    'version': '17.0.1.0.0',
    'summary': 'Adaptaciones de nómina para la localización de Venezuela',
    'description': """
        Módulo para la localización de Venezuela que añade campos específicos a los empleados y contratos:
        - Salario y Adicional en USD en el contrato.
        - Saldo de prestaciones en la ficha del empleado.
        - Tasa de interés del BCV en la configuración.
    """,
    'author': 'Supricom / Antigravity',
    'category': 'Human Resources/Payroll',
    'depends': ['hr', 'hr_contract', 'hr_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/hr_contract_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_bcv_interest_rate_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
