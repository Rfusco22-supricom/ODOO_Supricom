{
    'name': 'Supricom Sales Reports',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Reportes personalizados de ventas para Supricom',
    'description': """
    Módulo para generar:
    - Reporte de clientes nuevos (monto de su primera compra y mes).
    - Reporte de ventas por marca (SPIFF) por estado.
    """,
    'author': 'Supricom',
    'website': 'https://supricom.com',
    'depends': [
        'sale',
        'sale_management',
        'spiff_management',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/new_customer_sales_report_views.xml',
        'views/brand_state_sales_report_views.xml',
        'views/sale_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
