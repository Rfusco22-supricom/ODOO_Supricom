from odoo import _, fields, models


class AccountReportAsyncExport(models.Model):
    _inherit = "account.report.async.export"

    company_id = fields.Many2one(comodel_name="res.company", readonly=True, default=lambda self: self.env.company)

    def _process_reports_async_exports(self):
        super()._process_reports_async_exports()
        for export in self:
            if export.state == 'rejected':
                options = export.report_id.with_company(export.company_id).get_options({
                    'no_format': True,
                    'date': {'date_from': export.date_from, 'date_to': export.date_to},
                    'unfold_all': True,
                })
                report_closing_entry = self.env[export.report_id.custom_handler_model_name]._get_periodic_vat_entries(options)
                period_desc = report_closing_entry._get_tax_period_description()
                act_type_xmlid = 'account_reports.mail_activity_type_tax_report_error'
                report_closing_entry.activity_reschedule(
                    act_type_xmlids=[act_type_xmlid],
                    date_deadline=fields.Date.context_today(report_closing_entry)
                ) or report_closing_entry.activity_schedule(
                    act_type_xmlid=act_type_xmlid,
                    summary=_("Tax Report Error: %s", period_desc),
                )
