from odoo import models, api


class HrPayrollReportParser(models.AbstractModel):
    _name = 'report.hr_payroll_reports.report_payroll_rules_document'
    _description = 'Parser para Reporte de Reglas Salariales'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Override to pass custom data to the QWeb report template."""
        if not docids and data and data.get('docids'):
            docids = data.get('docids')
        docs = self.env['hr.payroll.report.wizard'].browse(docids)
        report_data = {
            'doc_ids': docids,
            'doc_model': 'hr.payroll.report.wizard',
            'docs': docs,
        }
        if data:
            report_data.update(data)
        return report_data
