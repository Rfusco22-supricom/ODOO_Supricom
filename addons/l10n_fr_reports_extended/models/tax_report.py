from odoo import models, _
from odoo.exceptions import UserError


class FrenchReportCustomHandler(models.AbstractModel):
    _inherit = 'l10n_fr.report.handler'

    def send_vat_report(self, options):
        vals = super().send_vat_report(options)
        report = self.env['account.report'].browse(options['report_id'])

        closing_moves = self._get_tax_closing_entries_for_closed_period(report, options, self.env.company)
        if not closing_moves:
            raise UserError(_("You need to complete the tax closing process for this period before submitting the report to the French administration."))

        l10n_fr_vat_report = self.env['l10n_fr_reports.send.vat.report'].create({})
        return {
            **vals,
            'res_id': l10n_fr_vat_report.id,
        }
