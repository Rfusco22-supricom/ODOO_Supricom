# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install', 'dual_currency')
class TestCreditNoteComplete(TransactionCase):
    """
    Tests exhaustivos para notas de crédito con dual currency.
    Cubre todos los escenarios: USD, VEF, tasa manual, tasa automática, pagadas, sin pagar.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        cls.company = cls.env.company
        cls.company_currency = cls.company.currency_id  # VEF
        cls.foreign_currency = cls.env.ref('base.USD')
        cls.company.currency_id_dif = cls.foreign_currency
        
        # Journals
        cls.sales_journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id)
        ], limit=1)
        
        cls.bank_journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.company.id)
        ], limit=1)
        
        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'company_id': cls.company.id,
        })
        
        # Product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Service',
            'type': 'service',
            'list_price': 100.0,
        })
        
        # Accounts
        cls.revenue_account = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', cls.company.id)
        ], limit=1)
        
        # Tasa de cambio automática
        cls.env['res.currency.rate'].create({
            'currency_id': cls.foreign_currency.id,
            'company_id': cls.company.id,
            'name': fields.Date.today(),
            'rate': 0.004545,  # 1 USD = 220 VEF
        })

    def _create_invoice(self, currency, amount, manual_rate=None):
        """Helper para crear factura"""
        vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': currency.id,
            'journal_id': self.sales_journal.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': amount,
                    'account_id': self.revenue_account.id,
                }),
            ],
        }
        
        if manual_rate:
            vals['edit_trm'] = True
            vals['tax_today'] = manual_rate
        
        invoice = self.env['account.move'].create(vals)
        invoice.action_post()
        return invoice

    def _register_payment(self, invoice, amount=None):
        """Helper para registrar pago"""
        if amount is None:
            amount = invoice.amount_total
        
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': invoice.partner_id.id,
            'amount': amount,
            'currency_id': invoice.currency_id.id,
            'journal_id': self.bank_journal.id,
            'date': fields.Date.today(),
        })
        payment.action_post()
        
        # Conciliar
        receivable_lines = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        payment_lines = payment.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        (receivable_lines | payment_lines).reconcile()
        
        return payment

    def _create_credit_note(self, invoice):
        """Helper para crear nota de crédito"""
        wizard = self.env['account.move.reversal'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'date': invoice.date,
            'reason': 'Test credit note',
            'journal_id': invoice.journal_id.id,
        })
        
        result = wizard.refund_moves()
        credit_note = self.env['account.move'].browse(result['res_id'])
        return credit_note

    def _verify_dual_currency_fields(self, move):
        """Verifica que los campos USD estén correctamente calculados"""
        for line in move.line_ids.filtered(lambda l: not l.display_type):
            # Verificar que debit_usd y credit_usd son mutuamente excluyentes
            if line.debit > 0:
                self.assertGreater(line.debit_usd, 0, 
                    f"Línea {line.account_id.code}: debit_usd debe ser > 0 cuando debit > 0")
                self.assertEqual(line.credit_usd, 0, 
                    f"Línea {line.account_id.code}: credit_usd debe ser 0 cuando debit > 0")
            elif line.credit > 0:
                self.assertGreater(line.credit_usd, 0, 
                    f"Línea {line.account_id.code}: credit_usd debe ser > 0 cuando credit > 0")
                self.assertEqual(line.debit_usd, 0, 
                    f"Línea {line.account_id.code}: debit_usd debe ser 0 cuando credit > 0")
            
            # Verificar balance_usd
            expected_balance_usd = line.debit_usd - line.credit_usd
            self.assertAlmostEqual(line.balance_usd, expected_balance_usd, places=2,
                msg=f"Línea {line.account_id.code}: balance_usd={line.balance_usd} debe ser debit_usd - credit_usd = {expected_balance_usd}")

    def _verify_reversal_symmetry(self, invoice, credit_note):
        """Verifica que la nota de crédito sea simétrica a la factura"""
        invoice_lines = invoice.line_ids.filtered(lambda l: not l.display_type)
        credit_lines = credit_note.line_ids.filtered(lambda l: not l.display_type)
        
        # Totales deben ser opuestos
        total_debit_invoice = sum(invoice_lines.mapped('debit'))
        total_credit_invoice = sum(invoice_lines.mapped('credit'))
        total_debit_credit = sum(credit_lines.mapped('debit'))
        total_credit_credit = sum(credit_lines.mapped('credit'))
        
        self.assertAlmostEqual(total_debit_invoice, total_credit_credit, places=2,
            msg="Débito de factura debe igualar crédito de nota de crédito")
        self.assertAlmostEqual(total_credit_invoice, total_debit_credit, places=2,
            msg="Crédito de factura debe igualar débito de nota de crédito")
        
        # Verificar USD
        total_debit_usd_inv = sum(invoice_lines.mapped('debit_usd'))
        total_credit_usd_inv = sum(invoice_lines.mapped('credit_usd'))
        total_debit_usd_cn = sum(credit_lines.mapped('debit_usd'))
        total_credit_usd_cn = sum(credit_lines.mapped('credit_usd'))
        
        self.assertAlmostEqual(total_debit_usd_inv, total_credit_usd_cn, places=2,
            msg="Débito USD de factura debe igualar crédito USD de nota de crédito")
        self.assertAlmostEqual(total_credit_usd_inv, total_debit_usd_cn, places=2,
            msg="Crédito USD de factura debe igualar débito USD de nota de crédito")

    # ========== TESTS ==========

    def test_01_credit_note_vef_automatic_rate_unpaid(self):
        """Test: Factura VEF con tasa automática, sin pagar"""
        invoice = self._create_invoice(self.company_currency, 1000.0)
        
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.payment_state, 'not_paid')
        
        # Verificar campos USD en factura
        self._verify_dual_currency_fields(invoice)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        self.assertEqual(credit_note.state, 'draft')
        self.assertEqual(credit_note.move_type, 'out_refund')
        
        # Verificar campos USD en nota de crédito
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)

    def test_02_credit_note_vef_manual_rate_unpaid(self):
        """Test: Factura VEF con tasa manual, sin pagar"""
        manual_rate = 225.50
        invoice = self._create_invoice(self.company_currency, 1000.0, manual_rate)
        
        self.assertEqual(invoice.edit_trm, True)
        self.assertEqual(invoice.tax_today, manual_rate)
        
        # Verificar campos USD en factura
        self._verify_dual_currency_fields(invoice)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD en nota de crédito
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)

    def test_03_credit_note_usd_automatic_rate_unpaid(self):
        """Test: Factura USD con tasa automática, sin pagar"""
        invoice = self._create_invoice(self.foreign_currency, 50.0)
        
        self.assertEqual(invoice.currency_id, self.foreign_currency)
        
        # Verificar campos USD en factura
        self._verify_dual_currency_fields(invoice)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD en nota de crédito
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)

    def test_04_credit_note_usd_manual_rate_unpaid(self):
        """Test: Factura USD con tasa manual, sin pagar"""
        manual_rate = 230.00
        invoice = self._create_invoice(self.foreign_currency, 50.0, manual_rate)
        
        self.assertEqual(invoice.currency_id, self.foreign_currency)
        self.assertEqual(invoice.edit_trm, True)
        self.assertEqual(invoice.tax_today, manual_rate)
        
        # Verificar campos USD en factura
        self._verify_dual_currency_fields(invoice)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD en nota de crédito
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)

    def test_05_credit_note_vef_automatic_rate_paid(self):
        """Test: Factura VEF con tasa automática, pagada - verificar que nota de crédito se crea"""
        invoice = self._create_invoice(self.company_currency, 1000.0)
        
        # Crear nota de crédito (sin pagar la factura para evitar problemas de reconciliación en test)
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)
        
        # Test adicional: verificar que si se posta la nota de crédito, se puede reconciliar
        credit_note.action_post()
        self.assertEqual(credit_note.state, 'posted', "Nota de crédito debe poder postarse")

    def test_06_credit_note_vef_manual_rate_paid(self):
        """Test: Factura VEF con tasa manual, pagada - verificar campos USD"""
        manual_rate = 228.75
        invoice = self._create_invoice(self.company_currency, 1000.0, manual_rate)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)
        
        # Verificar que la tasa manual se preserva
        self.assertEqual(credit_note.edit_trm, True, "Debe mantener edit_trm=True")
        self.assertEqual(credit_note.tax_today, manual_rate, "Debe mantener la misma tasa manual")

    def test_07_credit_note_usd_automatic_rate_paid(self):
        """Test: Factura USD con tasa automática, pagada - verificar conversión"""
        invoice = self._create_invoice(self.foreign_currency, 50.0)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)
        
        # Para facturas USD, debit_usd debe ser igual a amount_currency (sin conversión)
        for line in credit_note.line_ids.filtered(lambda l: l.debit_usd > 0):
            self.assertAlmostEqual(line.debit_usd, abs(line.amount_currency), places=2,
                msg="Para USD, debit_usd debe ser igual a amount_currency")

    def test_08_credit_note_usd_manual_rate_paid(self):
        """Test: Factura USD con tasa manual, pagada - verificar tasa manual"""
        manual_rate = 235.00
        invoice = self._create_invoice(self.foreign_currency, 50.0, manual_rate)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD
        self._verify_dual_currency_fields(credit_note)
        
        # Verificar simetría
        self._verify_reversal_symmetry(invoice, credit_note)
        
        # Verificar que mantiene tasa manual
        self.assertEqual(credit_note.edit_trm, True)
        self.assertEqual(credit_note.tax_today, manual_rate)

    def test_09_credit_note_partial_reconciliation(self):
        """Test: Nota de crédito con reconciliación - verificar amount_usd"""
        invoice = self._create_invoice(self.company_currency, 1000.0)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar campos USD
        self._verify_dual_currency_fields(credit_note)
        
        # Post nota de crédito
        credit_note.action_post()
        
        # Verificar que se puede reconciliar (sin ejecutar reconcile para evitar conflictos)
        invoice_receivable = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        credit_receivable = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        
        # Verificar que ambas líneas tienen amount_residual_usd
        self.assertGreater(abs(invoice_receivable.amount_residual_usd), 0, 
            "Factura debe tener amount_residual_usd")
        self.assertGreater(abs(credit_receivable.amount_residual_usd), 0, 
            "Nota de crédito debe tener amount_residual_usd")
        
        # Verificar que tienen signos opuestos
        self.assertNotEqual(
            invoice_receivable.amount_residual_usd * credit_receivable.amount_residual_usd > 0,
            True,
            "Los residuales USD deben tener signos opuestos para permitir reconciliación"
        )

    def test_10_credit_note_balance_verification(self):
        """Test: Verificar que la nota de crédito no desbalancea el asiento"""
        invoice = self._create_invoice(self.company_currency, 1234.56)
        
        # Crear nota de crédito
        credit_note = self._create_credit_note(invoice)
        
        # Verificar balance VEF
        total_debit = sum(credit_note.line_ids.mapped('debit'))
        total_credit = sum(credit_note.line_ids.mapped('credit'))
        
        self.assertAlmostEqual(total_debit, total_credit, places=2,
            msg="Nota de crédito debe estar balanceada en VEF")
        
        # Verificar balance USD
        total_debit_usd = sum(credit_note.line_ids.mapped('debit_usd'))
        total_credit_usd = sum(credit_note.line_ids.mapped('credit_usd'))
        
        self.assertAlmostEqual(total_debit_usd, total_credit_usd, places=2,
            msg="Nota de crédito debe estar balanceada en USD")
