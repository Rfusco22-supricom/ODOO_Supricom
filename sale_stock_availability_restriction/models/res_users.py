from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    puede_aprobar_excepcion = fields.Boolean(string="Puede Aprobar Excepción de Ventas", default=False, copy=False)
