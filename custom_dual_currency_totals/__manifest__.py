# -*- coding: utf-8 -*-
{
    'name': 'Custom Dual Currency Totals',
    'version': '1.0',
    'summary': 'Bloque de totales profesional para dualidad en facturas',
    'description': """
        Crea un nuevo bloque de subtotales y totales para las facturas que muestra los valores 
        en moneda local y divisas de forma profesional, basado en el módulo account_dual_currency.
    """,
    'author': 'Antigravity',
    'website': 'https://github.com/andresecas15/bdd17v10',
    'category': 'Accounting',
    'depends': ['account', 'account_dual_currency'],
    'data': [
        'views/account_move_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom_dual_currency_totals/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
