from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ReportIgtfTemplate(models.AbstractModel):
    _name = 'report.logicacero_igtf.report_igtf_template'
    _description = 'IGTF Report Template'

    @api.model
    def _get_report_values(self, docids, data=None):
        date_from = data.get('date_from')
        date_to = data.get('date_to')
        
        _logger.info("IGTF Report: Generating for %s - %s", date_from, date_to)

        # Buscar Pagos
        domain = [
            ('payment_type', '=', 'inbound'),
            ('state', '=', 'posted'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('mount_igtf', '>', 0),
            ('debit_note_igtf_id', '!=', False)
        ]
        _logger.info("IGTF Report: Domain used: %s", domain)
        
        payments = self.env['account.payment'].search(domain, order='date asc')
        
        _logger.info("IGTF Report: Found %s payments", len(payments))

        report_lines = []
        for payment in payments:
            # Document Type
            doc_type = 'PAGO'
            
            invoices = payment.igtf_invoice_ids.filtered(lambda m: m.is_invoice()) or payment.reconciled_invoice_ids.filtered(lambda m: m.is_invoice())
            doc_name = ', '.join(invoices.mapped('name')) if invoices else payment.debit_note_igtf_id.name
            
            rate = payment.tax_today if hasattr(payment, 'tax_today') and payment.tax_today else 1.0
            
            # Amount in Bs
            igtf_amount_bs = payment.mount_igtf * rate
            igtf_base_amount_bs = payment.amount * rate
            
            if invoices:
                total_untaxed = sum(invoices.mapped('amount_untaxed'))
                total_amount = sum(invoices.mapped('amount_total'))
                if total_amount > 0:
                    igtf_base_amount_bs = (payment.amount * rate) * (total_untaxed / total_amount)

            report_lines.append({
                'payment': payment,
                'doc_type': doc_type,
                'doc_name': doc_name,
                'igtf_amount': igtf_amount_bs,
                'igtf_base_amount': igtf_base_amount_bs,
                'currency': payment.company_id.currency_id,
            })

        return {
            'doc_ids': docids,
            'doc_model': 'account.payment',
            'docs': payments,
            'report_lines': report_lines,
            'date_from': date_from,
            'date_to': date_to,
        }
