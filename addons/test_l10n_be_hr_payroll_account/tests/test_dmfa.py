# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import re
from datetime import date
from odoo.tests import common, tagged
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged('dmfa')
class TestDMFA(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.belgian_company = cls.env['res.company'].create({
            'name': 'My Belgian Company - TEST',
            'country_id': cls.env.ref('base.be').id,
            'dmfa_employer_class': 456,
            'onss_registration_number': 45645,
            'onss_company_id': 45645,
        })
        cls.user = mail_new_test_user(
            cls.env,
            login='blou',
            company_ids=[(4, cls.env.ref('base.main_company').id), (4, cls.belgian_company.id)],
            groups='hr_payroll.group_hr_payroll_manager,fleet.fleet_group_manager',
        )
        cls.calendar_38h = cls.env['resource.calendar'].create({
            'name': 'Standard 38 hours/week',
            'tz': 'Europe/Brussels',
            'company_id': False,
            'hours_per_day': 7.6,
            'attendance_ids': [(5, 0, 0),
                (0, 0, {'name': 'Monday Morning', 'dayofweek': '0', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Monday Lunch', 'dayofweek': '0', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Monday Afternoon', 'dayofweek': '0', 'hour_from': 13, 'hour_to': 16.6, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Tuesday Morning', 'dayofweek': '1', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Tuesday Lunch', 'dayofweek': '1', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Tuesday Afternoon', 'dayofweek': '1', 'hour_from': 13, 'hour_to': 16.6, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Wednesday Morning', 'dayofweek': '2', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Wednesday Lunch', 'dayofweek': '2', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Wednesday Afternoon', 'dayofweek': '2', 'hour_from': 13, 'hour_to': 16.6, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Thursday Morning', 'dayofweek': '3', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Thursday Lunch', 'dayofweek': '3', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Thursday Afternoon', 'dayofweek': '3', 'hour_from': 13, 'hour_to': 16.6, 'day_period': 'afternoon'}),
                (0, 0, {'name': 'Friday Morning', 'dayofweek': '4', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'name': 'Friday Lunch', 'dayofweek': '4', 'hour_from': 12, 'hour_to': 13, 'day_period': 'lunch'}),
                (0, 0, {'name': 'Friday Afternoon', 'dayofweek': '4', 'hour_from': 13, 'hour_to': 16.6, 'day_period': 'afternoon'})
            ],
        })
        cls.calendar_4_days_36_hours = cls.env['resource.calendar'].create([{
            'name': "Test Calendar: 4 days, 36 hours/week",
            'company_id': cls.belgian_company.id,
            'hours_per_day': 9,
            'tz': "Europe/Brussels",
            'two_weeks_calendar': False,
            'full_time_required_hours': 36.0,
            'attendance_ids': [(5, 0, 0)] + [(0, 0, {
                'name': name,
                'dayofweek': dayofweek,
                'hour_from': hour_from,
                'hour_to': hour_to,
                'day_period': day_period,
                'work_entry_type_id': cls.env.ref('hr_work_entry.work_entry_type_attendance').id,
            }) for name, dayofweek, hour_from, hour_to, day_period in [
                ("Monday Morning", "0", 8.0, 12.0, "morning"),
                ("Monday Lunch", "0", 12.0, 13.0, "lunch"),
                ("Monday Afternoon", "0", 13.0, 18, "afternoon"),
                ("Tuesday Morning", "1", 8.0, 12.0, "morning"),
                ("Tuesday Lunch", "1", 12.0, 13.0, "lunch"),
                ("Tuesday Afternoon", "1", 13.0, 18, "afternoon"),
                ("Wednesday Morning", "2", 8.0, 12.0, "morning"),
                ("Wednesday Lunch", "2", 12.0, 13.0, "lunch"),
                ("Wednesday Afternoon", "2", 13.0, 18, "afternoon"),
                ("Thursday Morning", "3", 8.0, 12.0, "morning"),
                ("Thursday Lunch", "3", 12.0, 13.0, "lunch"),
                ("Thursday Afternoon", "3", 13.0, 18, "afternoon"),
            ]]
        }]).sudo(False)

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Laurie Poiret',
            'marital': 'single',
            'private_street': '58 rue des Wallons',
            'private_city': 'Louvain-la-Neuve',
            'private_zip': '1348',
            'private_country_id': cls.env.ref("base.be").id,
            'private_phone': '+0032476543210',
            'private_email': 'laurie.poiret@example.com',
            'resource_calendar_id': cls.calendar_38h.id,
            'company_id': cls.belgian_company.id,
            'address_id': cls.belgian_company.partner_id.id,
            'niss': '85073003328',
        })
        cls.env['l10n_be.dmfa.location.unit'].with_user(cls.user).create({
            'company_id': cls.employee.company_id.id,
            'code': 123,
            'partner_id': cls.employee.address_id.id,
        })

    def test_dmfa(self):
        dmfa = self.env['l10n_be.dmfa'].with_user(self.user).create({
            'reference': 'TESTDMFA',
            'company_id': self.belgian_company.id,
        })
        dmfa.with_context(dmfa_skip_signature=True).generate_dmfa_xml_report()
        self.assertFalse(dmfa.error_message)
        self.assertEqual(dmfa.validation_state, 'done')

    def test_93_dmfa_WorkingDaysSystems_4_days_week(self):
        self.belgian_company.resource_calendar_id = self.calendar_4_days_36_hours
        contract = self.env['hr.contract'].create({
            'name': 'Contract 4 days/week',
            'employee_id': self.employee.id,
            'resource_calendar_id': self.calendar_4_days_36_hours.id,
            'standard_calendar_id': self.calendar_4_days_36_hours.id,
            'company_id': self.belgian_company.id,
            'structure_type_id': self.env.ref('hr_contract.structure_type_employee_cp200').id,
            'date_start': date(2025, 1, 1),
            'wage': 3000,
        })
        payslip = self.env['hr.payslip'].create([{
            'name': 'Payslip Jan 2025',
            'contract_id': contract.id,
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 1, 31),
            'employee_id': self.employee.id,
            'struct_id': self.env.ref('l10n_be_hr_payroll.hr_payroll_structure_cp200_employee_salary').id,
            'company_id': self.belgian_company.id,
        }])
        payslip.compute_sheet()
        payslip.action_payslip_done()
        dmfa = self.env['l10n_be.dmfa'].with_user(self.user).create({
            'reference': 'TESTDMFA',
            'company_id': self.belgian_company.id,
            'year': '2025',
            'quarter': '1',
        })
        dmfa.with_context(dmfa_skip_signature=True).generate_dmfa_xml_report()
        pattern = r"<WorkingDaysSystem>(\d+)</WorkingDaysSystem>"
        working_days_system = re.search(pattern, base64.b64decode(dmfa.dmfa_xml).decode()).group(1)
        self.assertEqual(working_days_system, '400')
