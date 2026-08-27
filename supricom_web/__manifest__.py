# -*- coding: utf-8 -*-
{
    'name': 'Supricom Web - Cotizaciones en Sitio Web',
    'version': '17.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Reemplaza el flujo de compra/facturación nativo por solicitud de cotizaciones por Sitio Web.',
    'description': """
Este módulo permite anular el flujo nativo de checkout y pago de Odoo eCommerce
por un flujo exclusivo de solicitud de cotización (Quotation), configurable de forma individual por Sitio Web.
    """,
    'author': 'DIGIFLEX by Andres Castillo',
    'website': 'https://www.digiflex.com',
    'license': 'LGPL-3',
    'depends': [
        'website_sale',
        'whatsapp_connector',
    ],
    'data': [
        'views/website_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_sale_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
