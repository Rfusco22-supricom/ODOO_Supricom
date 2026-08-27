{
    'name': 'Restricciones de Usuario Supricom',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Restringe la modificación de cierres pasados, movimientos de caja pasados y creación de cuentas bancarias.',
    'author': 'DIGIFLEX',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'stock',
        'sale',
        'sale_stock',
    ],
    'data': [
        'security/security.xml',
    ],
    'installable': True,
    'application': False,
}
