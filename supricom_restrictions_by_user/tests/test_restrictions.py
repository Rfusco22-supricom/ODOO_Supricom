# -*- coding: utf-8 -*-
from odoo.tests import common
from odoo.exceptions import UserError
from odoo import fields

class TestRestrictions(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a restricted user
        cls.restricted_group = cls.env.ref('supricom_restrictions_by_user.group_supricom_restricted')
        cls.restricted_user = cls.env['res.users'].create({
            'name': 'Restricted Tester',
            'login': 'restricted_tester',
            'email': 'restricted@example.com',
            'groups_id': [(6, 0, [cls.restricted_group.id])],
        })
        # Create a standard user (non-restricted)
        cls.standard_user = cls.env['res.users'].create({
            'name': 'Standard Tester',
            'login': 'standard_tester',
            'email': 'standard@example.com',
            'groups_id': [(6, 0, [])],
        })

        # Find or create a company and a cash journal
        cls.company = cls.env.company
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Cash Test Journal',
            'code': 'CSHTS',
            'type': 'cash',
            'company_id': cls.company.id,
        })
        
        # Create a past date
        cls.past_date = fields.Date.subtract(fields.Date.today(), days=5)

    def test_01_res_partner_bank_creation(self):
        """Test res.partner.bank creation is restricted."""
        PartnerBank = self.env['res.partner.bank']
        
        # Standard user can create
        bank_std = PartnerBank.with_user(self.standard_user).create({
            'acc_number': '1234567890',
            'partner_id': self.standard_user.partner_id.id,
        })
        self.assertTrue(bank_std.exists())

        # Restricted user cannot create
        with self.assertRaises(UserError):
            PartnerBank.with_user(self.restricted_user).create({
                'acc_number': '0987654321',
                'partner_id': self.restricted_user.partner_id.id,
            })

    def test_02_account_bank_statement_modification(self):
        """Test past bank statement modification/deletion is restricted."""
        # Create a past bank statement as admin
        statement = self.env['account.bank.statement'].create({
            'name': 'Past Statement',
            'journal_id': self.cash_journal.id,
        })
        line = self.env['account.bank.statement.line'].create({
            'statement_id': statement.id,
            'date': self.past_date,
            'payment_ref': 'Line 1',
            'amount': 100.0,
            'journal_id': self.cash_journal.id,
        })

        # Standard user can modify
        statement.with_user(self.standard_user).write({'name': 'Past Statement Modified by Std'})
        
        # Restricted user cannot modify
        with self.assertRaises(UserError):
            statement.with_user(self.restricted_user).write({'name': 'Past Statement Modified by Restr'})

        # Restricted user cannot delete
        with self.assertRaises(UserError):
            statement.with_user(self.restricted_user).unlink()

        # Standard user can delete
        statement.with_user(self.standard_user).unlink()

    def test_03_account_move_cash_modification(self):
        """Test past cash move modification/deletion is restricted."""
        # Create a past cash move as admin
        move = self.env['account.move'].create({
            'journal_id': self.cash_journal.id,
            'date': self.past_date,
            'move_type': 'entry',
        })

        # Standard user can modify
        move.with_user(self.standard_user).write({'ref': 'Ref Std'})
        
        # Restricted user cannot modify
        with self.assertRaises(UserError):
            move.with_user(self.restricted_user).write({'ref': 'Ref Restr'})

        # Restricted user cannot delete
        with self.assertRaises(UserError):
            move.with_user(self.restricted_user).unlink()

        # Standard user can delete
        move.with_user(self.standard_user).unlink()
