# -*- coding: utf-8 -*-
{
    'name': "Product Company Price",
    'version': "17.0.1.0.0",
    'category': 'Sales',
    'license': 'Other proprietary',
    'summary': "Precio de venta por empresa usando la lista de precios predeterminada.",
    'description': """
        Permite que cada empresa tenga su propio precio de venta para productos
        compartidos (sin empresa asignada), usando la lista de precios
        predeterminada de cada empresa.
    """,
    'depends': ['product', 'sale', 'account_dual_currency'],
    'data': [
        'data/cron.xml',
        'views/product_pricelist_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
}
