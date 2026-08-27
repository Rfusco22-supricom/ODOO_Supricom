{
    'name': 'Logica Cero IGTF',
    'version': '17.0.0.4',
    'summary': 'Agrega un botón para aplicar el impuesto IGTF en facturas',
    'description': """
        Este módulo agrega un campo booleano '¿Es IGTF?' a los impuestos y un botón
        'Aplicar IGTF' en el formulario de factura para aplicar fácilmente este impuesto a todas las líneas.
    """,
    'category': 'Accounting',
    'author': 'Aecas by Logica Cero',
    'depends': ['account', 'account_dual_currency', 'l10n_ve_full'],
    'data': [
        'security/ir.model.access.csv',
        # 'views/account_tax_views.xml',
        # 'views/account_move_views.xml',
        'wizard/igtf_report_wizard_view.xml',
        'report/igtf_report.xml',
        'report/igtf_report_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
