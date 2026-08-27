from odoo import models, fields, api, _

class IgtfReportWizard(models.TransientModel):
    _name = 'igtf.report.wizard'
    _description = 'Wizard for IGTF Report'

    date_from = fields.Date(string='Desde', required=True)
    date_to = fields.Date(string='Hasta', required=True)

    def action_print_report(self):
        data = {
            'date_from': self.date_from,
            'date_to': self.date_to,
        }
        return self.env.ref('supricom_forma_libre_igtf.action_report_igtf').report_action(self, data=data)
