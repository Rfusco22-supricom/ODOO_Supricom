{
    "name": "Supricom - Forma Libre e IGTF",
    "version": "17.0.1.0.3",
    "summary": "Consolidación de las funcionalidades de impresión en Forma Libre y aplicación automática de IGTF",
    "description": """
        Este módulo consolida la funcionalidad de:
        - logicacero_igtf: Aplicación de IGTF y reporte legal.
        - forma_libre: Formato de impresión personalizado.
        - g3c_ve_homologacion: Automatización de IGTF en facturas y pagos (Notas de débito automáticas).
    """,
    "category": "Accounting",
    "author": "Andrés Castillo by Lógica Cero",
    "license": "LGPL-3",
    "depends": [
        "account",
        "account_dual_currency",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/paperformat_data.xml",
        "views/account_tax_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_move_views.xml",
        "views/account_payment_views.xml",
        "views/account_journal_views.xml",
        "wizard/igtf_report_wizard_view.xml",
        "report/invoice_report_action.xml",
        "report/invoice_template_dual.xml",
        "report/invoice_report.xml",
        "report/invoice_template.xml",
        "report/igtf_report.xml",
        "report/igtf_report_template.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
