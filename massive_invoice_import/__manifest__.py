{
    'name': 'Massive Invoice Import',
    'version': '17.0.1.2.0',
    'summary': 'Import invoices, credit notes, and delivery notes from Excel (Persistent with Progress)',
    'category': 'Accounting',
    'author': 'Marvin by Logica Cero',
    'depends': ['base', 'account', 'sale', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/import_documentos_views.xml',
    ],
    'external_dependencies': {
        'python': ['pandas', 'openpyxl'],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
