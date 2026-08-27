from odoo import models, fields

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    is_igtf_debit_note = fields.Boolean(
        string="¿Es para Notas de Débito IGTF?",
        help="Marque esta opción para que el sistema utilice este diario al generar automáticamente "
             "notas de débito por IGTF en pagos."
    )

    nro_ctrl_sequence_id = fields.Many2one(
        'ir.sequence',
        string="Secuencia de Número de Control",
        help="Si está configurado, el sistema usará esta secuencia para el número de control "
             "de las facturas de este diario."
    )
