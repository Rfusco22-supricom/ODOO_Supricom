{
    'name': 'Digiflex - Integración Banco Mercantil',
    'version': '17.0.1.0.3',
    'category': 'Accounting/Localizations',
    'summary': 'Integración API Banco Mercantil (Transferencias y Pago Móvil C2P) con conciliación diaria y captura de pagos',
    'author': 'Digiflex Corp',
    'license': 'LGPL-3',
    'depends': ['account'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/bank_integration_account_views.xml',
        'views/bank_transaction_line_views.xml',
        'views/account_payment_views.xml',
        'wizard/bank_transaction_select_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
}
