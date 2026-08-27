# Part of Odoo. See LICENSE file for full copyright and licensing details

from odoo.tests import tagged
from odoo import Command
from .common import TestIndustryFsmCommon

@tagged('post_install', '-at_install')
class TestFsmProjectTask(TestIndustryFsmCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user_portal = cls.env['res.users'].create({
            'name': 'blue',
            'login': 'blue',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])]
        })

        cls.partner_portal = cls.env['res.partner'].create({
            'name': 'blue partner',
            'company_id': False,
            'user_ids': [Command.link(cls.user_portal.id)]
        })

        cls.project_portal, cls.fsm_project_portal = (cls.env['project.project'].with_context(
            {'mail_create_nolog': True}).create([{
            'name': 'Portal',
            'privacy_visibility': 'portal',
        }, {
            'name': 'FSM Portal',
            'privacy_visibility': 'portal',
            'is_fsm': True,
            'allow_timesheets': True,
            'company_id': cls.env.company.id,
        }]))
        cls.project_portal.message_subscribe(partner_ids=[cls.partner_portal.id])
        cls.fsm_project_portal.message_subscribe(partner_ids=[cls.partner_portal.id])

    def test_default_project_fsm_subtasks(self):
        _, fsm_project_B = self.env['project.project'].create([
            {
                'name': 'Field Service A',
                'is_fsm': True,
                'company_id': self.env.company.id,
                'allow_timesheets': True,
                'sequence': 100,
            },
            {
                'name': 'Field Service B',
                'is_fsm': True,
                'company_id': self.env.company.id,
                'allow_timesheets': True,
                'sequence': 200,
            }
        ])
        task = self.env['project.task'].create({
            'name': 'Fsm task',
            'project_id': fsm_project_B.id,
            'partner_id': self.partner.id,
        })
        subtask = self.env['project.task'].with_context(
                fsm_mode=True,
                default_parent_id=task.id,
                default_project_id=task.project_id.id
        ).create({
            'name': 'Fsm subtask',
            'partner_id': self.partner.id,
        })
        self.assertEqual(subtask.project_id, fsm_project_B)

    def test_default_user_is_set_on_fsm_task(self):
        """
        This test ensures that when a fsm task is created, the partner_id set on the current user is set as its default
        partner_id if the user is a portal user.
        """
        (self.project_portal | self.fsm_project_portal).write({
            'collaborator_ids': [
                Command.create({'partner_id': self.user_portal.partner_id.id}),
            ],
        })

        portal_task = self.env['project.task'].with_context(
            {'default_project_id': self.project_portal.id}).with_user(self.user_portal).create({'name': 'youpi'})
        fsm_portal_task = self.env['project.task'].with_context(
            {'default_project_id': self.fsm_project_portal.id}).with_user(self.user_portal).create({'name': 'fsm task'})

        self.assertEqual(fsm_portal_task.partner_id, self.partner_portal,
                         'The fsm task created by a portal user should have a default partner set.')
        self.assertFalse(portal_task.partner_id,
                         'The task created by a portal user should not have a default partner set.')

        portal_task, fsm_portal_task = self.env['project.task'].create([{
            'name': 'youpi',
            'project_id': self.project_portal.id,
        }, {
            'name': 'fsm task',
            'project_id': self.fsm_project_portal.id,
        }])
        self.assertFalse(fsm_portal_task.partner_id,
                         'The fsm task created by a standard user should not have a default partner set.')
        self.assertFalse(portal_task.partner_id,
                         'The task created by a standard user should not have a default partner set.')
