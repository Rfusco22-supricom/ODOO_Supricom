# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import date, timedelta

from odoo import Command
from odoo.tests import tagged
from odoo.addons.account_reports.tests.common import TestAccountReportsCommon

TEST_DATE = date(2025, 5, 20)


@tagged('post_install_l10n', 'post_install', '-at_install')
class TestDocumentSummary(TestAccountReportsCommon):

    @classmethod
    def l10n_in_reports_gstr1_inv_init(cls, partner=None, tax=None, invoice_line_vals=None, inv=None, post=True, invoice_date=TEST_DATE):
        if not inv:
            inv = cls.init_invoice(
                "out_invoice",
                products=cls.product_a,
                invoice_date=invoice_date,
                taxes=tax,
                company=cls.company_data['company'],
                partner=partner,
            )
        else:
            inv = inv._reverse_moves()
            inv.write({'invoice_date': invoice_date})
        if invoice_line_vals:
            inv.write({'invoice_line_ids': [Command.update(l.id, invoice_line_vals) for l in inv.line_ids]})
        if post:
            inv.action_post()
        return inv

    @classmethod
    def setUpClass(cls, chart_template_ref="in"):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company_data['company'].write({
            'vat': '24AAGCC7144L6ZE',
            'state_id': cls.env.ref('base.state_in_gj').id,
            'street': 'Test Street',
            'city': 'Ahmedabad',
            'zip': '380001',
            'country_id': cls.env.ref('base.in').id,
        })
        cls.registered_partner = cls.partner_b
        cls.registered_partner.write({
            'vat': '27BBBFF5679L8ZR',
            'state_id': cls.env.ref('base.state_in_mh').id,
            'street': 'Test Street',
            'city': 'Ahmedabad',
            'zip': '380001',
            'l10n_in_gst_treatment': 'regular',
        })
        cls.product_a.write({'l10n_in_hsn_code': '998877'})

    def test_gstr1_doc_issue(self):
        invoice = self.l10n_in_reports_gstr1_inv_init(
            partner=self.registered_partner,
            invoice_line_vals={'price_unit': 500, 'quantity': 1},
            invoice_date=TEST_DATE,
        )
        return_period = self.env['l10n_in.gst.return.period'].create({
            'company_id': self.company_data['company'].id,
            'periodicity': 'monthly',
            'year': TEST_DATE.strftime('%Y'),
            'month': TEST_DATE.strftime('%m'),
            'start_date': TEST_DATE.replace(day=1),
            'end_date': (TEST_DATE.replace(day=1) + timedelta(days=31)).replace(day=1) - timedelta(days=1),
        })
        return_period.action_generate_document_summary()
        gstr1_json = return_period._get_gstr1_json()
        expected_doc_issue = {
            'doc_det': [
                {
                    'doc_num': 1,
                    'docs': [
                        {
                            'num': 1,
                            'from': invoice.name,
                            'to': invoice.name,
                            'totnum': 1,
                            'cancel': 0,
                            'net_issue': 1,
                        }
                    ]
                }
            ]
        }
        self.assertEqual(gstr1_json.get('doc_issue'), expected_doc_issue)
