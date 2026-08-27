# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests.common import TransactionCase


class TestCreditNoteReversal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        
        cls.company = cls.env['res.company'].create({
            'name': 'Test Dual Currency Company',
            'currency_id': cls.env.ref('base.VEF').id,
        })
        
        cls.foreign_currency = cls.env.ref('base.USD')
        cls.company.currency_id_dif = cls.foreign_currency
        
        cls.sales_journal = cls.env['account.journal'].create({
            'name': 'Test Sales Journal',
            'code': 'TSALE',
            'type': 'sale',
            'company_id': cls.company.id,
        })
        
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner',
            'company_id': cls.company.id,
        })
        
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'type': 'service',
            'list_price': 100.0,
        })
        
        cls.revenue_account = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', cls.company.id)
        ], limit=1)
        
        if not cls.revenue_account:
            cls.revenue_account = cls.env['account.account'].create({
                'name': 'Test Revenue',
                'code': 'TEST400',
                'account_type': 'income',
                'company_id': cls.company.id,
            })
        
        cls.env['res.currency.rate'].create({
            'currency_id': cls.foreign_currency.id,
            'company_id': cls.company.id,
            'name': fields.Date.today(),
            'rate': 0.004458,
        })

    def test_credit_note_reversal_amount_currency_sign(self):
        manual_rate = 224.38
        invoice_date = fields.Date.today()

        invoice = self.env['account.move'].with_company(self.company).with_context(default_move_type='out_invoice').create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': self.foreign_currency.id,
            'journal_id': self.sales_journal.id,
            'invoice_date': invoice_date,
            'edit_trm': True,
            'tax_today': manual_rate,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': 20.0,
                    'account_id': self.revenue_account.id,
                }),
            ],
        })
        invoice.action_post()
        
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.currency_id, self.foreign_currency)
        self.assertEqual(invoice.tax_today, manual_rate)
        
        receivable_line = invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        self.assertTrue(receivable_line)
        original_balance = receivable_line.balance
        original_amount_currency = receivable_line.amount_currency
        
        self.assertGreater(original_balance, 0, "Balance de cuenta por cobrar debe ser positivo")
        self.assertGreater(original_amount_currency, 0, "Amount currency debe ser positivo")
        
        reverse_wizard = self.env['account.move.reversal'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'date': invoice.date,
            'reason': 'Test reversión',
            'journal_id': invoice.journal_id.id,
        })
        
        result = reverse_wizard.refund_moves()
        credit_note_id = result.get('res_id')
        self.assertTrue(credit_note_id, "Debe crearse una nota de crédito")
        
        credit_note = self.env['account.move'].browse(credit_note_id)
        
        self.assertEqual(credit_note.state, 'draft')
        self.assertEqual(credit_note.move_type, 'out_refund')
        self.assertEqual(credit_note.currency_id, self.foreign_currency)
        
        for line in credit_note.line_ids.filtered(lambda l: not l.display_type):
            if line.balance != 0 and line.amount_currency != 0:
                sign_balance = 1 if line.balance >= 0 else -1
                sign_amount = 1 if line.amount_currency >= 0 else -1
                
                self.assertEqual(
                    sign_balance, 
                    sign_amount,
                    f"Balance ({line.balance}) y amount_currency ({line.amount_currency}) deben tener el mismo signo en cuenta {line.account_id.code}"
                )
        
        receivable_line_cn = credit_note.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        self.assertTrue(receivable_line_cn)
        
        self.assertLess(receivable_line_cn.balance, 0, "Balance en nota de crédito debe ser negativo")
        self.assertLess(receivable_line_cn.amount_currency, 0, "Amount currency en nota de crédito debe ser negativo")
        
        self.assertAlmostEqual(
            abs(receivable_line_cn.balance),
            abs(original_balance),
            places=2,
            msg="Balance de nota de crédito debe ser opuesto al de la factura"
        )
        self.assertAlmostEqual(
            abs(receivable_line_cn.amount_currency),
            abs(original_amount_currency),
            places=2,
            msg="Amount currency de nota de crédito debe ser opuesto al de la factura"
        )
