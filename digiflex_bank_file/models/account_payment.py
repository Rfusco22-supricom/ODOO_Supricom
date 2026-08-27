from odoo import models, fields, api,_


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    sent_to_bank = fields.Boolean(string='Enviado a Banco', default=False)

    def generate_bank_file(self):
        ids = self.ids
        journal_id = None
        for record in self:
            record.sent_to_bank = True
            journal_id = record.journal_id.id

        self = self.with_context(payment_ids=ids, journal_id=journal_id)
        return {
            'name': 'Descargar Archivo Banco',
            'type': 'ir.actions.act_window',
            'res_model': 'bank.file.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('digiflex_bank_file.view_bank_file_wizard_form').id,
            'target': 'new',
            'context': self.env.context,
        }




