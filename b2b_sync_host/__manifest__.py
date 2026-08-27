# -*- coding: utf-8 -*-
{
    "name": "B2B Sync Host",
    "summary": "Módulo Host B2B para atender peticiones de API REST, tarifas, inventario y creación/réplica de pedidos desde clientes Odoo (Compatible Odoo 17-19)",
    "version": "1.0.0",
    "category": "Sales/Sales",
    "author": "Digiflex by Andres Castillo",
    "website": "https://www.digiflex.com",
    "license": "LGPL-3",
    "depends": [
        "base",
        "product",
        "sale_management",
        "stock",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/b2b_client_config_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": True,
}
