# -*- coding: utf-8 -*-
{
    'name': "Panamá: Localización Completa",
    'summary': """Localización Panameña""",
    'description': """
        Localización completa para Panamá
        - Campo RUC con validación
        - Visibilidad condicional por país
        - Sincronización con campo VAT estándar
    """,
    'category': 'Localization',
    'version': '17.0.1.0.4',
    'depends': [
        'base',
        'base_vat',
        'contacts',
        'account',
        'sale',
        'purchase',
        'l10n_pa',
    ],
    'data': [
        'data/res_country_vat_label.xml',
        'views/res_partner.xml',
        'views/sale_order.xml',
        'views/purchase_order.xml',
        'views/account_move.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
