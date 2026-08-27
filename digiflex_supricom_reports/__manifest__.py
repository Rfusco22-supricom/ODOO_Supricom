# -*- coding: utf-8 -*-
{
    'name': 'Digiflex - Supricom Reports',
    'version': '17.0.1.0.0',
    'category': 'Sales/Accounting',
    'summary': 'Reporte de ventas con margen sobre costo, cierre de caja diario y estado operativo de pedidos',
    'description': """
    Módulo de reportes y control operativo para Supricom:
    =====================================================
    1. Reporte de Ventas con Utilidad y Margen sobre Costo % (Ventas y Devoluciones).
    2. Cierre de Caja Diario (Cuadre de pagos agrupado por mes y diario).
    3. Identificación y marcado de pedidos facturados con devolución como 'Operados Parcialmente'.
    """,
    'author': 'DIGIFLEX',
    'website': 'https://digiflex.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'account',
        'stock',
        'sale_stock',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/sales_margin_wizard_views.xml',
        'views/sales_margin_report_views.xml',
        'views/daily_cash_closing_views.xml',
        'views/sale_order_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
