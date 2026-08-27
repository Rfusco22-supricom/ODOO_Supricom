# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime

from dateutil.relativedelta import relativedelta
from odoo.addons.hr_payroll.tests.common import TestPayslipBase
from odoo.addons.mail.tests.common import mail_new_test_user


class TestPayslipFlow(TestPayslipBase):

    def test_00_payslip_flow(self):
        """ Testing payslip flow and report printing """
        # activate Richard's contract
        self.richard_emp.contract_ids[0].state = 'open'

        # I create an employee Payslip
        richard_payslip = self.env['hr.payslip'].create({
            'name': 'Payslip of Richard',
            'employee_id': self.richard_emp.id
        })

        payslip_input = self.env['hr.payslip.input'].search([('payslip_id', '=', richard_payslip.id)])
        # I assign the amount to Input data
        payslip_input.write({'amount': 5.0})

        # I verify the payslip is in draft state
        self.assertEqual(richard_payslip.state, 'draft', 'State not changed!')

        richard_payslip.compute_sheet()

        # Then I click on the 'Confirm' button on payslip
        richard_payslip.action_payslip_done()

        # I verify that the payslip is in done state
        self.assertEqual(richard_payslip.state, 'done', 'State not changed!')

        # Then I click on the 'Mark as paid' button on payslip
        richard_payslip.action_payslip_paid()

        # I verify that the payslip is in paid state
        self.assertEqual(richard_payslip.state, 'paid', 'State not changed!')

        # I want to check refund payslip so I click on refund button.
        richard_payslip.refund_sheet()

        # I check on new payslip Credit Note is checked or not.
        payslip_refund = self.env['hr.payslip'].search([('name', 'like', 'Refund: '+ richard_payslip.name), ('credit_note', '=', True)])
        self.assertTrue(bool(payslip_refund), "Payslip not refunded!")

        # I want to generate a payslip from Payslip run.
        payslip_run = self.env['hr.payslip.run'].create({
            'date_end': '2011-09-30',
            'date_start': '2011-09-01',
            'name': 'Payslip for Employee'
        })

        # I create record for generating the payslip for this Payslip run.

        payslip_employee = self.env['hr.payslip.employees'].create({
            'employee_ids': [(4, self.richard_emp.id)]
        })

        # I generate the payslip by clicking on Generat button wizard.
        payslip_employee.with_context(active_id=payslip_run.id).compute_sheet()

    def test_01_batch_with_specific_structure(self):
        """ Create a batch with a given structure different than the regular pay"""

        specific_structure = self.env['hr.payroll.structure'].create({
            'name': 'End of the Year Bonus - Test',
            'type_id': self.structure_type.id,
        })

        self.richard_emp.contract_ids[0].state = 'open'

        # 13th month pay
        payslip_run = self.env['hr.payslip.run'].create({
            'date_start': datetime.date.today() + relativedelta(years=-1, month=8, day=1),
            'date_end': datetime.date.today() + relativedelta(years=-1, month=8, day=31),
            'name': 'End of the year bonus'
        })
        # I create record for generating the payslip for this Payslip run.
        payslip_employee = self.env['hr.payslip.employees'].create({
            'employee_ids': [(4, self.richard_emp.id)],
            'structure_id': specific_structure.id,
        })

        # I generate the payslip by clicking on Generat button wizard.
        payslip_employee.with_context(active_id=payslip_run.id).compute_sheet()

        self.assertEqual(len(payslip_run.slip_ids), 1)
        self.assertEqual(payslip_run.slip_ids.struct_id.id, specific_structure.id)

    def test_02_payslip_batch_with_archived_employee(self):
        # activate Richard's contract
        self.richard_emp.contract_ids[0].state = 'open'
        # archive his contact
        self.richard_emp.action_archive()

        # 13th month pay
        payslip_run = self.env['hr.payslip.run'].create({
            'date_start': datetime.date.today() + relativedelta(years=-1, month=8, day=1),
            'date_end': datetime.date.today() + relativedelta(years=-1, month=8, day=31),
            'name': 'End of the year bonus'
        })
        # I create record for generating the payslip for this Payslip run.
        payslip_employee = self.env['hr.payslip.employees'].create({
            'employee_ids': [(4, self.richard_emp.id)],
        })
        # I generate the payslip by clicking on Generat button wizard.
        payslip_employee.with_context(active_id=payslip_run.id).compute_sheet()

        self.assertEqual(len(payslip_run.slip_ids), 1)

    def test_03_payroll_struct_country_change(self):
        """ Testing the write on country_id from payroll structure """
        test_structure = self.env['hr.payroll.structure'].create({
            'name': 'Test Payroll Structure',
            'type_id': self.structure_type.id,
            'country_id': False
        })
        rule_1 = self.env['hr.salary.rule'].create({
            'name': 'Test 1',
            'code': 'T1',
            'category_id': self.env.ref('hr_payroll.BASIC').id,
            'struct_id': test_structure.id,
            'appears_on_payroll_report': True
        })
        rule_2 = self.env['hr.salary.rule'].create({
            'name': 'Test 2',
            'code': 'T2',
            'category_id': self.env.ref('hr_payroll.BASIC').id,
            'struct_id': test_structure.id,
            'appears_on_payroll_report': False
        })

        # Check a field has been created from rule_1 as x_l10n_xx_t1
        self.assertTrue(self.env['ir.model.fields'].search([('name', '=', 'x_l10n_xx_t1')]))

        # Write a new country_id on test_structure
        test_structure.write({'country_id': self.env.ref('base.us').id})

        # Check a new rule field has been created as x_l10n_us_t1
        self.assertTrue(self.env['ir.model.fields'].search([('name', '=', 'x_l10n_us_t1')]))

        # Check x_l10n_xx_t1 has been removed
        self.assertFalse(self.env['ir.model.fields'].search([('name', '=', 'x_l10n_xx_t1')]))

        # Check that the rules appears_on_payroll_report are the same after the write
        self.assertTrue(rule_1.appears_on_payroll_report)
        self.assertFalse(rule_2.appears_on_payroll_report)

    def test_04_cancel_a_done_payslip_with_payroll_admin(self):
        """Cancel a done payslip using a new user with Payroll Admin access."""
        test_user = mail_new_test_user(
            self.env, name="Test user", login="test_user",
            groups="hr_payroll.group_hr_payroll_manager"
        )
        self.richard_emp.contract_ids[0].state = 'open'
        richard_payslip = self.env['hr.payslip'].create({
            'name': 'Payslip of Richard',
            'employee_id': self.richard_emp.id,
        })
        richard_payslip.action_payslip_done()
        self.assertEqual(richard_payslip.state, 'done')
        richard_payslip.with_user(test_user).action_payslip_cancel()
        self.assertEqual(richard_payslip.state, 'cancel')

    def test_05_payslip_with_out_of_schedule_public_holiday(self):
        self.richard_emp.contract_ids[0].state = 'open'
        richard_payslip = self.env['hr.payslip'].create({
            'name': 'Payslip of Richard',
            'employee_id': self.richard_emp.id,
            'date_from': datetime.datetime.strptime('2025-11-1 00:00:00', '%Y-%m-%d %H:%M:%S'),
            'date_to': datetime.datetime.strptime('2025-11-30 23:59:59', '%Y-%m-%d %H:%M:%S')
        })
        self.env['resource.calendar.leaves'].create({
            'name': 'Generic Public Holiday',
            'date_from': datetime.datetime.strptime('2025-11-1 00:00:00', '%Y-%m-%d %H:%M:%S'),
            'date_to': datetime.datetime.strptime('2025-11-1 23:59:59', '%Y-%m-%d %H:%M:%S'),
            'resource_id': False,
            'calendar_id': self.richard_emp.resource_calendar_id.id,
            'work_entry_type_id': richard_payslip.worked_days_line_ids.work_entry_type_id.id,
            'time_type': 'leave',
        })
        richard_payslip.compute_sheet()
        self.assertEqual(richard_payslip.worked_days_line_ids.name, 'Attendance')
