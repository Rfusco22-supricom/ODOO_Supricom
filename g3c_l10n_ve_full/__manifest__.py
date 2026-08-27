# -*- coding: utf-8 -*-
{
    "name": "G3C C.A localizacion custom",
    "version": "1.0.0",
    "category": "Localization",
    "author": "G3C C.A",
    "summary": "localizacion custom",
    "description": """
        localizacion custom",
    """,
    "depends": [
        "l10n_ve_full","account_dual_currency"
    ],
    "data": [
        "views/res_users_security.xml",
        "data/sequence_invoices.xml",
        "wizard/advertencia_wizard.xml",
        "views/account_move.xml",
        "views/account_payment.xml",
        "views/sale_order.xml",
        "views/product_template.xml",        
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
