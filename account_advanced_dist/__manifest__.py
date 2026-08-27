{
    'name': 'Distribución Avanzada de Pagos (Multi-Compañía)',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'author': 'Lógica Cero',
    'description': """
Módulo avanzado para la distribución de pagos en entornos multi-compañía.
Permite aplicar pagos parciales, gestionar pagos de terceros y realizar transferencias inter-compañía automáticamente.
    """,
    'depends': ['account', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/payment_split_wizard_view.xml',
        'views/account_move_view_inherit.xml',
        'views/res_company_view.xml',
        'views/apply_exchange_diff_wizard_view.xml',
    ],
    'application': False,
    'license': 'OPL-1',
}