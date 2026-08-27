from odoo import models

class ReportInvoiceDual(models.AbstractModel):
    _name = 'report.forma_libre.report_invoice_template_dual'
    _description = 'Factura Fiscal Dual'

    def _get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)

        for doc in docs:
            doc.sudo().print_count += 1
            if doc.print_count > 1:
                doc.sudo().invoice_template_dual_printed = True

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': docs,
        }
