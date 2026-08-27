{
    'name': 'France - Accounting Reports Extension',
    'countries': ['fr'],
    'version': '1.0',
    'description': """
Accounting reports for France Extension
========================================
    """,
    'category': 'Accounting/Localizations/Reporting',
    'depends': ['l10n_fr_reports'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/l10n_fr_send_vat_report_wizard.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'OEEL-1',
}
