# -*- coding: utf-8 -*-
{
    'name': 'Digiflex - Reporte Cuentas por Cobrar',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Reporte en vista lista de Cuentas por Cobrar con Vendedor y Número de Control',
    'author': 'DIGIFLEX',
    'website': 'https://digiflex.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'sale',
        'l10n_ve_full',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/digiflex_cxc_report_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'digiflex_cxc_odoo/static/src/js/export_banner.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
