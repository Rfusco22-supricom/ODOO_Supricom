# -*- coding: utf-8 -*-
{
    'name': 'Supricom Restrictions Sales',
    'summary': 'Restricciones de cancelación en Despachos y Facturas Emitidas',
    'description': """
        Módulo de restricciones para Supricom S.A.:
        - Impide cancelar despachos (stock.picking) que ya hayan sido validados (state == 'done').
        - Impide cancelar facturas (account.move) emitidas que tengan despachos validados asociados.
    """,
    'author': 'DIGIFLEX',
    'website': 'https://digiflextec.com',
    'category': 'Sales/Inventory/Accounting',
    'version': '17.0.1.0.0',
    'depends': ['stock', 'account', 'sale', 'sale_stock'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
