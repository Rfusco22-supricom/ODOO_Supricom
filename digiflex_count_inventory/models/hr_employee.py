# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    count_pin = fields.Char(
        string='PIN Conteo Inventario',
        size=4,
        help='PIN de 4 dígitos para ingresar al módulo de conteo de inventario.',
    )
    count_inventory_available = fields.Boolean(
        string='Disponible para Conteos',
        default=True,
        help='Permite seleccionar a este empleado como responsable en sesiones de conteo de inventario.',
    )
