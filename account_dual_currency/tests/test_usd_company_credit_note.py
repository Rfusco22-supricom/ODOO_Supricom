# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.tests import tagged

@tagged('post_install', '-at_install', 'dual_currency')
class TestUSDCompanyCreditNote(TransactionCase):
    """
    Pruebas para comprobar el funcionamiento de notas de crédito en compañías 
    cuya moneda base es el USD (Instancia B).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # 1. Crear compañía con moneda base USD
        cls.currency_usd = cls.env.ref('base.USD')
        cls.currency_ves = cls.env.ref('base.VEF') # Usamos VEF como representación de Bolívares
        
        cls.company_b = cls.env['res.company'].create({
            'name': 'Compañía Instancia B (USD)',
            'currency_id': cls.currency_usd.id,
            'is_ve_company': True,
        })
        
        # 2. Configurar moneda dual como VES
        cls.company_b.currency_id_dif = cls.currency_ves
        
        # 3. Configurar diarios y cuentas
        cls.sales_journal = cls.env['account.journal'].create({
            'name': 'Ventas USD',
            'code': 'VUSD',
            'type': 'sale',
            'company_id': cls.company_b.id,
            'currency_id': cls.currency_usd.id,
        })
        
        cls.reception_account = cls.env['account.account'].create({
            'name': 'Cuentas por Cobrar Test',
            'code': '110101.TEST',
            'account_type': 'asset_receivable',
            'company_id': cls.company_b.id,
            'reconcile': True,
        })
        
        cls.revenue_account = cls.env['account.account'].create({
            'name': 'Ingresos Test',
            'code': '410101.TEST',
            'account_type': 'income',
            'company_id': cls.company_b.id,
        })
        
        cls.partner = cls.env['res.partner'].create({
            'name': 'Cliente Test B',
            'company_id': cls.company_b.id,
        })
        
        cls.product = cls.env['product.product'].create({
            'name': 'Producto Test B',
            'type': 'service',
            'company_id': cls.company_b.id,
        })

    def test_01_usd_company_reversal_rate_copy(self):
        """
        Validar que al hacer una nota de crédito en una compañía USD,
        se copie la tasa original y no haya discrepancias en BS.
        """
        original_rate = 35.0
        invoice_date = fields.Date.today()

        # Crear Factura en USD con tasa manual
        invoice = self.env['account.move'].with_company(self.company_b).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': self.currency_usd.id,
            'journal_id': self.sales_journal.id,
            'invoice_date': invoice_date,
            'edit_trm': True,
            'tax_today': original_rate,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': 100.0, # 100 USD
                    'account_id': self.revenue_account.id,
                }),
            ],
        })
        invoice.action_post()
        
        # Verificar montos originales
        receivable_line = invoice.line_ids.filtered(lambda l: l.account_type == 'asset_receivable')
        self.assertEqual(receivable_line.balance, 100.0)
        self.assertEqual(receivable_line.amount_currency, 100.0)
        # debit_usd en este caso guarda el equivalente en VES (3500)
        self.assertEqual(receivable_line.debit_usd, 3500.0)
        
        # Crear Nota de Crédito usando el wizard
        wizard = self.env['account.move.reversal'].with_company(self.company_b).with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'date': fields.Date.today(),
            'reason': 'Devolución Test',
            'journal_id': invoice.journal_id.id,
        })
        
        result = wizard.refund_moves()
        credit_note = self.env['account.move'].browse(result['res_id'])
        
        # VERIFICACIÓN 1: ¿Se copió la tasa correctamente?
        self.assertEqual(credit_note.tax_today, original_rate, "La tasa de cambio debe ser la misma de la factura original")
        self.assertEqual(credit_note.edit_trm, True, "Debe tener edit_trm en True para preservar la tasa")
        
        # VERIFICACIÓN 2: ¿Los montos base son simétricos?
        receivable_line_cn = credit_note.line_ids.filtered(lambda l: l.account_type == 'asset_receivable')
        self.assertEqual(receivable_line_cn.balance, -100.0, "El balance debe ser exactamente el opuesto")
        self.assertEqual(receivable_line_cn.amount_currency, -100.0, "El amount_currency debe ser exactamente el opuesto")
        
        # VERIFICACIÓN 3: ¿Los montos en Bolívares son simétricos?
        # En el refund, debit_usd será 0 y credit_usd será el original debit_usd
        self.assertEqual(receivable_line_cn.credit_usd, 3500.0, "El equivalente en VES (credit_usd) debe coincidir con el original")

    def test_02_usd_company_price_unit_usd_logic(self):
        """
        Validar que price_unit_usd no se divida por la tasa si ya está en USD.
        """
        rate = 40.0
        invoice = self.env['account.move'].with_company(self.company_b).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': self.currency_usd.id,
            'journal_id': self.sales_journal.id,
            'tax_today': rate,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1.0,
                    'price_unit': 150.0,
                    'account_id': self.revenue_account.id,
                }),
            ],
        })
        
        line = invoice.invoice_line_ids[0]
        # Con la corrección, price_unit_usd debe ser igual a price_unit (150)
        # Sin la corrección, sería 150/40 = 3.75
        self.assertEqual(line.price_unit_usd, 150.0, "price_unit_usd debe ser igual a price_unit si la moneda es USD")

    def test_03_ves_company_usd_invoice_credit_note_no_constraint(self):
        """
        Reproduce el caso real de producción:
        Empresa con moneda base VES, factura en USD, nota de crédito via wizard.
        Valida que NO se lanza el error de constraint 'amount_currency_balance_sign'.
        
        Este es el escenario que fallaba: durante la auto-reconciliación de la
        nota de crédito, el motor de Odoo hacía un fix in-place de amount_currency
        con signo incorrecto (+2080 en vez de -2080) para las líneas de crédito.
        """
        # 1. Crear compañía con moneda base VES (caso estándar Venezuela)
        currency_ves = self.env.ref('base.VEF')
        currency_usd = self.env.ref('base.USD')
        
        company_ves = self.env['res.company'].create({
            'name': 'Compañía VES (Instancia A)',
            'currency_id': currency_ves.id,
        })
        company_ves.currency_id_dif = currency_usd

        # Activar moneda USD
        currency_usd.active = True

        sales_journal = self.env['account.journal'].create({
            'name': 'Ventas VES',
            'code': 'VVES',
            'type': 'sale',
            'company_id': company_ves.id,
        })

        receivable_account = self.env['account.account'].create({
            'name': 'Cuentas por Cobrar Test VES',
            'code': '110101.VES',
            'account_type': 'asset_receivable',
            'company_id': company_ves.id,
            'reconcile': True,
        })

        revenue_account = self.env['account.account'].create({
            'name': 'Ingresos Test VES',
            'code': '410101.VES',
            'account_type': 'income',
            'company_id': company_ves.id,
        })

        partner = self.env['res.partner'].create({
            'name': 'Cliente VES Test',
            'company_id': company_ves.id,
        })

        product = self.env['product.product'].create({
            'name': 'Producto VES Test',
            'type': 'service',
            'company_id': company_ves.id,
        })

        rate = 35.0
        # Crear tasa de cambio USD para la compañía VES
        self.env['res.currency.rate'].create({
            'currency_id': currency_usd.id,
            'company_id': company_ves.id,
            'name': fields.Date.today(),
            'inverse_company_rate': rate,
        })

        # 2. Crear factura en USD (moneda secundaria) en empresa VES
        invoice = self.env['account.move'].with_company(company_ves).create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'currency_id': currency_usd.id,   # factura en USD
            'journal_id': sales_journal.id,
            'invoice_date': fields.Date.today(),
            'edit_trm': True,
            'tax_today': rate,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': 1.0,
                'price_unit': 100.0,
                'account_id': revenue_account.id,
            })],
        })
        invoice.action_post()

        # 3. Crear nota de crédito via wizard (mismo flujo que producción)
        wizard = self.env['account.move.reversal'].with_company(company_ves).with_context(
            active_model='account.move',
            active_ids=invoice.ids,
        ).create({
            'date': fields.Date.today(),
            'reason': 'Test constraint fix',
            'journal_id': invoice.journal_id.id,
        })

        # Esto lanzaba ValidationError antes del fix
        result = wizard.refund_moves()
        credit_note = self.env['account.move'].browse(result['res_id'])

        # 4. Validaciones
        # La nota de crédito debe crearse sin error de constraint
        self.assertTrue(credit_note.exists(), "La nota de crédito debe haberse creado")

        receivable_cn = credit_note.line_ids.filtered(
            lambda l: l.account_type == 'asset_receivable'
        )
        self.assertTrue(receivable_cn, "Debe existir línea de cobro en la nota de crédito")

        # Invariante core: balance y amount_currency deben tener el mismo signo
        if receivable_cn.currency_id == receivable_cn.company_currency_id:
            self.assertEqual(
                receivable_cn.amount_currency, receivable_cn.balance,
                "Para líneas mismo-moneda: amount_currency debe = balance"
            )
        else:
            if receivable_cn.balance < 0:
                self.assertLessEqual(
                    receivable_cn.amount_currency, 0,
                    "amount_currency debe ser negativo en líneas de crédito"
                )

        # La tasa debe haberse copiado correctamente
        self.assertEqual(
            credit_note.tax_today, rate,
            "La tasa de cambio debe copiarse de la factura original"
        )

    def test_04_write_guard_does_not_break_normal_credit(self):
        """
        Verifica que la guarda de write() NO interfiere con escrituras legítimas
        de amount_currency en líneas de moneda extranjera (no mismo-moneda).
        """
        rate = 35.0
        invoice = self.env['account.move'].with_company(self.company_b).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'currency_id': self.currency_usd.id,
            'journal_id': self.sales_journal.id,
            'tax_today': rate,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 2.0,
                'price_unit': 200.0,
                'account_id': self.revenue_account.id,
            })],
        })

        # Para una línea en moneda de compañía (same-currency), amount_currency == balance
        line = invoice.invoice_line_ids[0]
        # La guarda no debe haber modificado nada incorrecto
        # balance y amount_currency deben tener signos consistentes
        if line.currency_id == line.company_currency_id:
            self.assertEqual(
                line.amount_currency, line.balance,
                "Same-currency line: amount_currency debe ser igual a balance"
            )
        else:
            # Para línea en moneda extranjera: signos deben ser consistentes
            if line.balance > 0:
                self.assertGreaterEqual(line.amount_currency, 0)
            elif line.balance < 0:
                self.assertLessEqual(line.amount_currency, 0)

