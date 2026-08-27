from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_ve_igtf_active = fields.Boolean(
        related='company_id.l10n_ve_igtf_active',
        readonly=False,
        string='Activar Lógica IGTF'
    )
