from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_ve_igtf_active = fields.Boolean(string='Activar Lógica IGTF', default=True)
