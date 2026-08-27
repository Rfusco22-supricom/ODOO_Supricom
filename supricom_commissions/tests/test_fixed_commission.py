import datetime
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError

class TestFixedCommission(TransactionCase):

    def setUp(self):
        super(TestFixedCommission, self).setUp()
        self.Salesperson = self.env['res.partner'].create({'name': 'Juan Perez', 'email': 'juan@example.com'})
        self.User = self.env['res.users'].create({
            'name': 'Juan Perez', 
            'login': 'juan_test', 
            'partner_id': self.Salesperson.id,
            'email': 'juan@example.com',
            'is_vendor': True
        })
        self.ProductFixed = self.env['product.product'].create({
            'name': 'Producto Fijo',
            'list_price': 100.0,
            'standard_price': 50.0,
            'x_comision_fija_producto': 10.0
        })
        self.ProductNormal = self.env['product.product'].create({
            'name': 'Producto Normal',
            'list_price': 100.0,
            'standard_price': 50.0,
            'x_comision_fija_producto': 0.0
        })
        
        # Create Invoice
        self.Invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.env['res.partner'].create({'name': 'Cliente Test'}).id,
            'invoice_date': datetime.date.today(),
            'invoice_user_id': self.User.id,
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.ProductFixed.id,
                    'quantity': 1,
                    'price_unit': 100.0,
                }),
                (0, 0, {
                    'product_id': self.ProductNormal.id,
                    'quantity': 1,
                    'price_unit': 100.0,
                })
            ]
        })
        self.Invoice.action_post()
        
        # Create Payment
        self.Payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.Invoice.partner_id.id,
            'amount': 200.0,
            'date': datetime.date.today(),
        })
        self.Payment.action_post()
        
        # Reconcile (Simple version if possible, or standard)
        # Odoo 14+ reconciliation might vary, trying standard approach
        line_to_reconcile = self.Invoice.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        payment_line = self.Payment.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        (line_to_reconcile + payment_line).reconcile()

    def test_fixed_commission_applied(self):
        # Create Wizard
        wizard = self.env['commission.settlement.wizard'].create({
            'date_from': datetime.date.today().replace(day=1),
            'date_to': datetime.date.today().replace(day=28), # End of month approx
        })
        
        # Generate
        action = wizard.action_generate_settlement()
        settlement_id = action['domain'][0][2][0]
        settlement = self.env['commission.settlement'].browse(settlement_id)
        
        # Check Lines
        fixed_line = settlement.line_ids.filtered(lambda l: l.product_id == self.ProductFixed)
        normal_line = settlement.line_ids.filtered(lambda l: l.product_id == self.ProductNormal)
        
        self.assertEqual(len(fixed_line), 1, "Should have 1 commission line for fixed product")
        self.assertEqual(fixed_line.commission_pct, 10.0, "Fixed product should have 10% commission")
        
        # Normal line commission depends on matrix, but likely 0 if no matrix set up or low achievement.
        # Just verifying it didn't take the 10% from the other product or something weird.
        self.assertNotEqual(normal_line.commission_pct, 10.0, "Normal product should NOT have 10% commission")
