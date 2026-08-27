# -*- coding: utf-8 -*-
{
    'name': "BCV Exchange Rate Connect",
    'summary': """
        Scrape and inject BCV exchange rates into Odoo currencies.""",
    'description': """
        This module allows to connect with the Central Bank of Venezuela (BCV)
        website to retrieve the official exchange rates (USD, EUR) and
        automatically update the currency rates in Odoo.
        
        Features:
        - Standalone module (No dependencies on other custom localization modules).
        - "Inverse Rate" field in Currency Rates for easier reading/writing (e.g. 54.00 Bs/USD).
        - Scheduled action to update rates daily.
        - Detailed logging of scraping process.
        - Support for USD and EUR.

======================================================================
AVISO DE PROPIEDAD: Supricom
======================================================================
Este módulo es propiedad privada y exclusiva de CruiserParts.
Su uso está restringido únicamente a la infraestructura y operaciones
de CruiserParts. Prohibida su distribución a terceros.

Para más detalles, consulte el archivo LICENSE en la raíz del módulo.
======================================================================
    """,
    'author': "Aecas",
    'website': "https://www.google.com",
    'category': 'Accounting/Localizations',
    'version': '17.0.1.0.0',
    'depends': ['base', 'account'],
    'data': [
        'data/ir_cron.xml',
        'views/res_currency_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'license': 'LGPL-3',
}

