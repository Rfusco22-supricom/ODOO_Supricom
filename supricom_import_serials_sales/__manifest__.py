# -*- coding: utf-8 -*-
{
    'name': 'Supricom - Importación Masiva de Seriales en Ventas y Despachos',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Sales',
    'summary': 'Permite la carga masiva de números de serie desde archivos Excel/CSV para Despachos y Facturas de Venta',
    'author': 'DIGIFLEX / Supricom',
    'website': 'https://supricom.com',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'sale_management',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/import_serials_sales_wizard_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
