# -*- coding: utf-8 -*-
{
    'name': "Venezuela: Account Dual Currency",
        "version": "17.0.3.3.2",
    'category' : 'Account',
    'license': 'Other proprietary',
    'summary': """Esta aplicación permite manejar dualidad de moneda en Contabilidad.""",
    'description': """
    
        - Mantener como moneda principal Bs y $ como secundaria.
        - Facturas en Bs pero manteniendo deuda en $.
        - Tasa individual para cada Factura de Cliente y Proveedor.
        - Tasa individual para Asientos contables.
        - Visualización de Débito y Crédito en ambas monedas en los apuntes contables.
        - Conciliación total o parcial de $ y Bs en facturas.
        - Registro de pagos en facturas con tasa diferente a la factura.
        - Registro de anticipos en el módulo de Pagos de Odoo, manteniendo saldo a favor en $ y Bs.
        - Informe de seguimiento en $ y Bs a la tasa actual.
        - Reportes contables en $ (Vencidas por Pagar, Vencidas por Cobrar y Libro mayor de empresas)
        - Valoración de inventario en $ y Bs a la tasa actual

    """,
    'depends': [
                'base','account','account_reports','account_followup','web','l10n_ve_full',
                'stock_account','account_accountant','analytic','account_debit_note','mail',
                'account_reports_cash_basis', 'product','purchase_stock', 'stock_landed_costs'
                ],
    'data':[
        'security/ir.model.access.csv',
        'security/res_groups.xml',
        'views/res_currency.xml',
        'views/res_config_settings.xml',
        'views/account_move_view.xml',
        'views/account_move_line.xml',
        # 'views/search_template_view.xml',
        'wizard/account_payment_register.xml',
        'views/account_payment.xml',
        'views/product_template.xml',
        'views/stock_landed_cost.xml',
        'views/stock_valuation_layer.xml',
        # 'views/account_journal_dashboard.xml',
        'views/product_pricelist_item_views.xml',
        'views/product_pricelist_views.xml',
        'data/decimal_precision.xml',
        'data/cron.xml',
        'data/account_partial_reconcile_migration.xml',
        # 'data/channel.xml',
        'views/effective_date_change.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_dual_currency/static/src/js/systray_theme_menu.js',
            'account_dual_currency/static/src/xml/systray.xml',
            'account_dual_currency/static/src/components/**/*',
        ],
    },
    'images': [
        'static/description/thumbnail.png',
    ],
    'installable' : True,
    'application' : False,
}

