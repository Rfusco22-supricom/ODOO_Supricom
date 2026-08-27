# -*- coding: utf-8 -*-
{
    'name': 'Digiflex Conteo de Inventario',
    'version': '17.0.1.1.4',
    'category': 'Inventory/Inventory',
    'summary': 'Conteo cuantitativo de inventario cíclico y mensual con interfaz OWL y PIN',
    'description': """
Módulo de Conteo de Inventario Cuantitativo (Digiflex)
======================================================
- Interfaz OWL en pantalla completa con selector de usuario y teclado PIN.
- Conteo cuantitativo (sin trazabilidad de lotes/series durante el conteo).
- Inventario cíclico diario (productos vendidos en fecha configurable) e inventario de todos los productos.
- Asignación masiva y reparto automático de productos por operador.
- Opción de conteo a ciegas (oculta cantidades teóricas).
- Asignación de empleados responsables por ubicación.
- Indicador visual de diferencias (verde: match, rojo: faltante, azul/amarillo: sobrante).
- Integración con Ajustes nativos de Odoo (stock.quant).
- Cierre del conteo del día y generación de reportes en PDF.
    """,
    'author': 'DIGIFLEX / Supricom',
    'website': 'https://www.digiflex.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'stock',
        'hr',
        'web',
        'mail',
    ],

    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'wizard/count_inventory_assign_wizard_views.xml',
        'views/count_inventory_views.xml',
        'views/hr_employee_views.xml',
        'views/action_menu.xml',
        'report/count_inventory_report.xml',
        'report/count_inventory_report_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'digiflex_count_inventory/static/src/css/count_inventory_app.css',
            'digiflex_count_inventory/static/src/js/count_inventory_app.js',
            'digiflex_count_inventory/static/src/xml/count_inventory_app.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
