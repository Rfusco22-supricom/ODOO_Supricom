from odoo import models, fields, api

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _selection_server(self):
        return [('bcv', 'BCV')]

    # Requerimiento 4: Solo permitir tasa oficial BCV
    # Quitar Dolar Today de la selección utilizando un método de selección
    server = fields.Selection(selection='_selection_server', string='Servidor', default='bcv')
