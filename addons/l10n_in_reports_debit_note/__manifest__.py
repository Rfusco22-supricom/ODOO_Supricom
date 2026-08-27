{
    'name': "Indian - GSTR eFiling for Debit Note",
    'countries': ['in'],
    "description": """
GST return filing for Debit Notes
=================================
This module provides functionality for filing GST returns specifically for Debit Notes in India.
    """,
    'category': "Accounting/Localizations/Reporting",
    'depends': ['l10n_in_reports_gstr', 'account_debit_note'],
    'data': [
        'data/account_financial_html_report_gstr1.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'OEEL-1',
}
