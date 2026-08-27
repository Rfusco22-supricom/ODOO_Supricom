# -*- coding: utf-8 -*-
{
    'name': 'Digiflex Widget Stock by Storage',
    'summary': 'Muestra el stock a la mano de una ubicación previamente configurada en ajustes y permite ocultar el stock global a usuarios restringidos.',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'DIGIFLEX',
    'license': 'LGPL-3',
    'depends': ['base', 'stock', 'account_dual_currency'],
    'data': [
        'security/groups.xml',
        'views/res_config_settings_views.xml',
        'views/product_views.xml',
    ],
    'installable': True,
    'application': False,
}
