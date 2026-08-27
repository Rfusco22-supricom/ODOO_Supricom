{
    'name': 'Compra/Transferencia de Divisas',
    'version': '17.0.1.3.0',
    'category': 'Accounting',
    'summary': 'Gestión de compra y transferencia de divisas con cálculo de diferencial cambiario.',
    'description': """
        Este módulo permite gestionar transferencias de dinero entre diarios (ej. Caja Bs a Zelle)
        donde la tasa de cambio puede diferir de la del sistema, generando ajustes automáticos
        por diferencial cambiario.
        
        Características:
        - Flujo de dos pasos: Enviar (Origen) y Recibir (Destino).
        - Especificación manual de montos.
        - Cálculo automático de Ganancia/Pérdida Cambiaria.
        - Generación de asientos contables.
        - Configuración de cuentas y diarios predeterminados.
    """,
    'author': 'Aecas by Lógica Cero',
    'depends': ['account'],
    'data': [
        'security/currency_exchange_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/currency_exchange_views.xml',
        'views/config_views.xml',
        'reports/exchange_report.xml',
    ],
    'installable': True,
    'application': True,
}
