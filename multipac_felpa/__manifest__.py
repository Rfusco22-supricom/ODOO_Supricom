# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

{
    'name': "E-Invoice - Panamá FEL",

    'summary': """
        Odoo module for Panamá E-Invoice System (FEL).
        """,

    'description': """
        Odoo module for Panamá E-Invoice System (FEL).
        """,

    'author': "Molbitek - MRDC",
    'website': "https://mrdc.tech",
    'category': 'Invoicing & Payments',
    'version': '1.0.4',

    'countries': ['pa'],

    'depends': ['base', 'web', 'base_setup', 'account', 'sale', 'base_address_extended', 'l10n_pa', 'l10n_latam_base', 'contacts', 'sale_stock', 'mail'],

    'data': [

        'security/fel_pa_security.xml',
        'security/ir.model.access.csv',

        'data/l10n_latam.identification.type.csv',
        'data/fel_pa_tools_report_fonts_data.xml',
        'data/fel_pa_res_country_state_data.xml',
        'data/fel_pa_res_city_data.xml',
        'data/fel_pa_tools_county_data.xml',
        'data/fel_pa_tools_product_unspsc_category_data.xml',
        'data/fel_pa_ir_cron_data.xml',
        'data/fel_pa_withholding_data.xml',

        'wizard/fel_pa_tools_msg_wizard_views.xml',
        'wizard/fel_pa_tools_cancel_wizard_views.xml',
        'wizard/fel_pa_tools_create_contingency_wizard_views.xml',
        'wizard/fel_pa_tools_ruc_validator_wizard_views.xml',

        'views/fel_pa_tools_api_request_views.xml',
        'views/fel_pa_tools_report_extra_content_views.xml',
        'views/fel_pa_tools_contingency_views.xml',

        'views/res_partner_views.xml',
        'views/res_company_views.xml',
        'views/product_views.xml',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_withholding_views.xml',
        'views/fel_pa_withholding_views.xml',

        'views/invoice_templates/templates.xml',
        'views/invoice_templates/invoice_templates.xml',
        'views/invoice_templates/template_report.xml',
        'views/invoice_templates/morden_invoice.xml',
        'views/invoice_templates/bold_invoice.xml',
        'views/invoice_templates/corporate_invoice.xml',
        'views/invoice_templates/polished_invoice.xml',
        'views/invoice_templates/classic_invoice.xml',
        'views/invoice_templates/infile_classic_invoice.xml',
        'views/invoice_templates/odoo_invoice.xml',
        'views/invoice_templates/vintage_invoice.xml',
        'views/invoice_templates/report_invoice.xml',

        'views/multipac_felpa_views.xml',

        'report/report_withholding_certificate.xml',

        'data/country.xml',

    ],

    'assets':{
        'web.report_assets_common': [
            'multipac_felpa/static/src/css/template.css',
        ],
    },

    'external_dependencies': {
        'python': ['img2pdf', 'fpdf']
    },

    'demo': [],
    'license': 'OPL-1',
}
