# __manifest__.py
{
    "name": "Gestión de Incentivos de Ventas (SPIFF)",
    "version": "17.0.1.3.0",
    "category": "Sales",
    "summary": "Gestione incentivos SPIFF por Producto y Marca",
    "author": "Logica Cero",
    "depends": ["sale_management", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/spiff_security.xml",
        "views/spiff_views.xml",
        "wizard/credit_extension_wizard_views.xml",
        "wizard/multi_brand_warning_views.xml",
        "reports/spiff_report_templates.xml",
        "reports/spiff_report_actions.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
