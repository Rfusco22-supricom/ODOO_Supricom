from odoo.tests.common import TransactionCase
from odoo.fields import Date
from datetime import timedelta

class TestCommissionRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestCommissionRules, cls).setUpClass()
        cls.company = cls.env.company
        
        # Setup Currencies
        cls.usd = cls.env.ref("base.USD")
        cls.ves = cls.env["res.currency"].with_context(active_test=False).search([("name", "in", ["VES", "VEF", "Bs."])], limit=1)
        if not cls.ves:
            cls.ves = cls.env["res.currency"].create({
                "name": "VES",
                "symbol": "Bs.",
                "rounding": 0.01,
                "active": True
            })
        else:
            cls.ves.write({"active": True})
            
        # Create a USD Pricelist
        cls.usd_pricelist = cls.env["product.pricelist"].create({
            "name": "Lista USD",
            "currency_id": cls.usd.id,
        })
            
    def setUp(self):
        super(TestCommissionRules, self).setUp()
        self.company.write({
            "currency_id": self.usd.id,
            "commission_grace_days": 3,
            "commission_strict_full_payment": True,
            "commission_credit_threshold": 2000.0,
            "commission_payment_tolerance": 0.0, # 0% tolerance
            "commission_use_targets": True,
            "commission_base_type": "amount",
            "commission_use_pricelist_mapping": False,
        })

        # Setup vendor
        self.vendor_type = self.env["commission.vendor.type"].create({
            "name": "Test Vendor Type",
            "code": "O",
            "country": "VEN",
        })
        self.salesperson = self.env["res.users"].create({
            "name": "QA Salesperson",
            "login": "qa_salesperson",
            "vendor_type_id": self.vendor_type.id,
            "is_vendor": True,
        })
        
        # Partner
        self.partner = self.env["res.partner"].create({"name": "Test Client"})
        
        # Payment Terms
        self.term_cash = self.env["account.payment.term"].create({
            "name": "QA Immediate Payment",
            "line_ids": [(0, 0, {"value": "percent", "value_amount": 100, "nb_days": 0})]
        })
            
        self.term_credit = self.env["account.payment.term"].create({
            "name": "QA Crédito 15 Días",
            "line_ids": [(0, 0, {"value": "percent", "value_amount": 100, "nb_days": 15})]
        })

        # Product
        self.product = self.env["product.product"].create({
            "name": "Test Product",
            "list_price": 20.0, # USD Price
            "standard_price": 10.0,
        })
        
        # Assign Product Price in USD Pricelist
        self.env["product.pricelist.item"].create({
            "pricelist_id": self.usd_pricelist.id,
            "product_tmpl_id": self.product.product_tmpl_id.id,
            "fixed_price": 20.0,
            "compute_price": "fixed",
        })

    def _create_invoice(self, amount, date, term, currency):
        move = self.env["account.move"].with_company(self.company).create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "company_id": self.company.id,
            "invoice_user_id": self.salesperson.id,
            "invoice_date": date,
            "invoice_date_due": date, # Force it here
            "invoice_payment_term_id": term.id,
            "currency_id": currency.id,
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product.id,
                "quantity": 1,
                "price_unit": amount,
                "tax_ids": [(5, 0, 0)],
            })]
        })
        move.action_post()
        # Ensure the date_due is not overridden by action_post
        move.write({"invoice_date_due": date})
        return move

    def _register_payment(self, invoice, amount, date):
        payment = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'amount': amount,
            'payment_date': date,
        })
        return payment._create_payments()

    def test_01_grace_days(self):
        date_inv = Date.to_date("2026-05-01")
        
        inv_grace = self._create_invoice(100, date_inv, self.term_cash, self.company.currency_id)
        self._register_payment(inv_grace, 100, Date.to_date("2026-05-04"))
        
        inv_overdue = self._create_invoice(100, date_inv, self.term_cash, self.company.currency_id)
        self._register_payment(inv_overdue, 100, Date.to_date("2026-05-05"))
        
        wizard = self.env["commission.settlement.wizard"].with_company(self.company).create({
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
        })
        wizard.action_generate_settlement()
        
        settlement = self.env["commission.settlement"].search([
            ("salesperson_id", "=", self.salesperson.id),
            ("date_from", "=", "2026-05-01")
        ], limit=1)
        
        lines = settlement.line_ids
        self.assertEqual(len(lines), 2)
        
        line_grace = lines.filtered(lambda l: l.invoice_id == inv_grace)
        line_overdue = lines.filtered(lambda l: l.invoice_id == inv_overdue)
        
        self.assertFalse(line_grace.is_excluded, f"Grace failed! is_overdue={line_grace.is_overdue}, reason={line_grace.exclude_reason}")
        self.assertTrue(line_overdue.is_excluded, f"Overdue failed! is_overdue={line_overdue.is_overdue}, reason={line_overdue.exclude_reason}, grace_days={self.company.commission_grace_days}")

    def test_02_usd_base_pricelist(self):
        # Enable dynamic pricelist mapping
        self.company.write({"commission_use_pricelist_mapping": True})
        
        # Create a VES Pricelist that maps to the USD Pricelist for commissions
        ves_pricelist = self.env["product.pricelist"].create({
            "name": "Lista VES Oficial",
            "currency_id": self.ves.id,
            "commission_mapped_pricelist_id": self.usd_pricelist.id,
        })

        date_inv = Date.to_date("2026-05-10")
        
        # Create a dummy SO just to hold the pricelist mapping
        so = self.env["sale.order"].with_company(self.company).create({
            "partner_id": self.partner.id,
            "pricelist_id": ves_pricelist.id,
        })
        
        # Use our reliable helper to create the invoice
        invoice = self._create_invoice(1500, date_inv, self.term_cash, self.ves)
        
        # Force the origin link so the wizard finds it
        invoice.write({"invoice_origin": so.name})
        
        self._register_payment(invoice, 1500, date_inv)
        
        wizard = self.env["commission.settlement.wizard"].with_company(self.company).create({
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
        })
        wizard.action_generate_settlement()
        
        settlement = self.env["commission.settlement"].search([
            ("salesperson_id", "=", self.salesperson.id)
        ], limit=1)
        
        line = settlement.line_ids.filtered(lambda l: l.invoice_id == invoice)
        self.assertEqual(line.amount_paid, 20.0, f"Paid: {line.amount_paid}, Base Type: {self.company.commission_base_type}")

    def test_03_strict_full_payment_threshold(self):
        date_inv = Date.to_date("2026-05-15")
        
        inv_a = self._create_invoice(1500, date_inv, self.term_credit, self.usd)
        self._register_payment(inv_a, 500, date_inv) # Pago parcial
        
        inv_b = self._create_invoice(2500, date_inv, self.term_credit, self.usd)
        self._register_payment(inv_b, 2499, date_inv) # Pago casi total
        self.assertEqual(inv_b.amount_residual, 1.0, "El residual debe ser 1")
        
        wizard = self.env["commission.settlement.wizard"].with_company(self.company).create({
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
        })
        wizard.action_generate_settlement()
        
        settlement = self.env["commission.settlement"].search([
            ("salesperson_id", "=", self.salesperson.id)
        ], limit=1)
        
        line_a = settlement.line_ids.filtered(lambda l: l.invoice_id == inv_a)
        line_b = settlement.line_ids.filtered(lambda l: l.invoice_id == inv_b)
        
        self.assertFalse(line_a.is_excluded, "A is excluded")
        self.assertTrue(line_b.is_excluded, f"B is not excluded! Fully paid: {inv_b.amount_residual <= 0.0}, Credit: {line_b.is_credit}, Amount: {inv_b.amount_total}")

    def test_04_historical_closing(self):
        self.env["commission.monthly.target"].create({
            "vendedor_id": self.salesperson.partner_id.id,
            "date_from": "2026-04-01",
            "date_to": "2026-04-30",
            "achievement_percentage": 80.0, # 80%
            "company_id": self.company.id,
            "state": "done",
            "target_type": "individual",
        })
        
        self.env["commission.matrix"].create({
            "vendor_type_id": self.vendor_type.id,
            "target_achievement_pct": 0,
            "commission_percentage": 0.05, # Tasa estandar 5%
        })
        
        date_inv = Date.to_date("2026-04-10") # Factura de Abril
        inv = self._create_invoice(100, date_inv, self.term_cash, self.company.currency_id)
        inv.write({"manual_commission_override": True})
        self._register_payment(inv, 100, Date.to_date("2026-05-10")) # Pagado en Mayo
        
        wizard = self.env["commission.settlement.wizard"].with_company(self.company).create({
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
        })
        wizard.action_generate_settlement()
        
        settlement = self.env["commission.settlement"].search([
            ("salesperson_id", "=", self.salesperson.id)
        ], limit=1)
        
        line = settlement.line_ids.filtered(lambda l: l.invoice_id == inv)
        
        self.assertFalse(line.is_excluded, f"Test 4 excluded: {line.exclude_reason}")
        self.assertEqual(line.commission_pct, 0.05, f"Pct is {line.commission_pct}, Rate config targets={self.company.commission_use_targets}")

    def test_05_refunds_reduce_total_facturado(self):
        date_inv = Date.to_date("2026-05-10")
        inv = self._create_invoice(200, date_inv, self.term_cash, self.company.currency_id)
        refund = self.env["account.move"].with_company(self.company).create({
            "move_type": "out_refund",
            "partner_id": self.partner.id,
            "company_id": self.company.id,
            "invoice_user_id": self.salesperson.id,
            "invoice_date": date_inv,
            "invoice_payment_term_id": self.term_cash.id,
            "currency_id": self.company.currency_id.id,
            "invoice_line_ids": [(0, 0, {
                "product_id": self.product.id,
                "quantity": 1,
                "price_unit": -50.0,
                "tax_ids": [(5, 0, 0)],
            })],
        })
        refund.action_post()

        wizard = self.env["commission.settlement.wizard"].with_company(self.company).create({
            "date_from": "2026-05-01",
            "date_to": "2026-05-31",
        })
        wizard.action_generate_settlement()

        settlement = self.env["commission.settlement"].search([
            ("salesperson_id", "=", self.salesperson.id),
            ("date_from", "=", "2026-05-01"),
        ], limit=1)

        self.assertEqual(settlement.total_invoiced, 150.0)
