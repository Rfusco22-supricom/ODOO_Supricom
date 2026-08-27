from odoo import models, fields

class SpiffBrand(models.Model):
    _name = "spiff.brand"
    _description = "Marca de Producto (SPIFF)"
    _order = "name"

    name = fields.Char(string="Nombre de Marca", required=True)
    active = fields.Boolean(default=True)
    credit_extension_days = fields.Integer(string="Días de Extensión de Crédito", default=0, help="Días adicionales que se suman al término de pago si el pedido contiene solo esta marca.")
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
