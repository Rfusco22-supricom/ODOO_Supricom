# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import HttpCase, tagged
from odoo.tools import file_open


@tagged('-at_install', 'post_install')
class TestApplicantDetails(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_user = mail_new_test_user(
            cls.env,
            login='test_user',
            name='test_user User',
            email='test_user@test.example.com',
            notification_type='inbox',
            groups='base.group_user',
        )

        cls.department = cls.env['hr.department'].create({
            'name': 'test department',
        })

        cls.job = cls.env['hr.job'].create({
            'name': 'Any job',
            'department_id': cls.department.id,
        })

        cls.applicant = cls.env['hr.applicant'].create({
            'name': 'Test app',
            'job_id': cls.job.id,
        })

        with file_open('sign/static/demo/sample_contract.pdf', 'rb') as f:
            pdf_content = f.read()

        cls.attachment = cls.env['ir.attachment'].create({
            'type': 'binary',
            'raw': pdf_content,
            'name': 'test_employee_contract.pdf',
        })

        cls.template_2_roles = cls.env['sign.template'].create({
            'name': 'template_2_roles',
            'attachment_id': cls.attachment.id,
        })

        cls.env['sign.item'].create([
            {
                'type_id': cls.env.ref('sign.sign_item_type_text').id,
                'responsible_id': cls.env.ref('sign.sign_item_role_employee').id,
                'posX': 0.273,
                'posY': 0.158,
                'template_id': cls.template_2_roles.id,
                'width': 0.150,
                'height': 0.015,
                'required': False,
            },
            {
                'type_id': cls.env.ref('sign.sign_item_type_text').id,
                'responsible_id': cls.env.ref('hr_contract_sign.sign_item_role_job_responsible').id,
                'posX': 0.373,
                'posY': 0.258,
                'template_id': cls.template_2_roles.id,
                'width': 0.150,
                'height': 0.015,
                'required': False,
            },
        ])

        cls.contract_template = cls.env['hr.contract'].create({
            'name': 'contract template',
            'structure_type_id': cls.env.ref('hr_contract.structure_type_employee').id,
            'hr_responsible_id': cls.env.user.id,
            'wage': 5000.0,
            'sign_template_id': cls.template_2_roles.id,
        })

    def _create_sign_values(self, sign_item_ids, role_id):
        return {
            str(sign_id): 'a'
            for sign_id in sign_item_ids
            .filtered(lambda r: not r.responsible_id or r.responsible_id.id == role_id)
            .mapped('id')
        }

    def _json_url_open(self, url, data, **kwargs):
        data = {
            'id': 0,
            'jsonrpc': '2.0',
            'method': 'call',
            'params': data,
        }
        headers = {
            'Content-Type': 'application/json',
            **kwargs.get('headers', {}),
        }
        return self.url_open(url, data=json.dumps(data).encode(), headers=headers)

    def test_employee_work_email_should_not_be_updated(self):
        # In any case employee work email should not be updated
        employee = self.env['hr.employee'].create({'name': 'abc'})
        self.applicant.write({
            'emp_id': employee.id,
            'partner_name': 'abc',
        })
        employee.user_id = self.test_user.id
        self.assertEqual(employee.work_email, 'test_user@test.example.com')

        wizard = self.env['generate.simulation.link'].with_context({
            'active_model': 'hr.applicant',
            'active_id': self.applicant.id,
        }).create({
            'applicant_id': self.applicant.id,
            'contract_id': self.contract_template.id,
            'final_yearly_costs': 12000.0,
            'employee_job_id': self.job.id,
        })
        wizard_res = wizard.action_save()
        offer = self.env['hr.contract.salary.offer'].browse(wizard_res.get('res_id'))

        data = {
            'contract_id': wizard.contract_id.id,
            'offer_id': offer.id,
            'benefits': {
                'contract': {
                    'wage': 1000,
                    'final_yearly_costs': 12000,
                    'holidays': 10,
                    'l10n_be_canteen_cost': False,
                },
                'employee': {
                    'name': 'New Employee',
                    'private_email': 'new_employee@test.example.com',
                    'employee_job_id': self.job.id,
                    'department_id': self.department.id,
                    'job_title': self.job.name,
                },
                'address': {
                    'email': 'test_email1@example.com',
                },
                'bank_account': {},
            },
            'token': offer.access_token,
            'applicant_id': self.applicant.id,
            'original_link': offer.url,
        }

        result = self._json_url_open('/salary_package/submit', data=data).json()
        self.assertIn('result', result)
        result = result['result']
        sign_request = self.env['sign.request'].browse(result['request_id'])
        self._json_url_open(
            '/sign/sign/%d/%s' % (result['request_id'], result['token']),
            data={
                'signature': self._create_sign_values(
                    sign_request.template_id.sign_item_ids,
                    self.env.ref('sign.sign_item_role_employee').id,
                )
            },
        )
        new_employee = self.env['hr.contract'].browse(result['new_contract_id']).employee_id
        self.assertEqual(new_employee.work_email, 'test_user@test.example.com')
