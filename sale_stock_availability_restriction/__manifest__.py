{
    'name': 'Sale Stock Availability Restriction',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Restrict sale confirmation if no stock in warehouse location',
    'description': """
        This module adds a validation when confirming a sale order:
        - It checks that there is enough quantity available in the stock location of the assigned warehouse.
        - If the product has on-hand quantity in other locations but not in the stock location of the assigned warehouse, it will not allow the confirmation.
    """,
    'author': 'Antigravity',
    'depends': ['sale_management', 'sale_stock', 'stock', 'account'],
    'data': [
        'security/stock_picking_rule.xml',
        'security/ir.model.access.csv',
        'wizard/recreate_picking_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
