{
    'name': 'Notificacion al Seniat',
    'version': '17.0',  # Actualizado a la versión 17
    'summary': 'Manage Fiscal Year Lock Date with Warnings',
    'sequence': 10,
    'description': """ """,
    'category': 'Accounting',
    'website': 'https://www.contablesag.com',
    'depends': ['base', 'mail', 'stock', 'account', 'account_accountant'],  # Verificar si alguna dependencia requiere actualización para Odoo 17
    'data': [
        'data/mail_template2.xml',
        'views/warning.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '/delivery_warning_seniat/static/src/js/form_controller.js',
        ],
    },
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
