# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
from odoo.tests import new_test_user
from odoo.tests.common import tagged, TransactionCase
from odoo.exceptions import UserError

TEXT = base64.b64encode(bytes("documents_fleet", 'utf-8'))


@tagged('post_install', '-at_install', 'test_document_bridge')
class TestCaseDocumentsBridgeFleet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fleet_folder = cls.env.ref('documents_fleet.documents_fleet_folder')
        company = cls.env.user.company_id
        company.documents_fleet_settings = True
        company.documents_fleet_folder = cls.fleet_folder
        cls.documents_user = new_test_user(cls.env, "test fleet manager",
            groups="documents.group_documents_user, fleet.fleet_group_manager"
        )
        # Create the Audi vehicle
        brand = cls.env["fleet.vehicle.model.brand"].create({
            "name": "Audi",
        })
        model = cls.env["fleet.vehicle.model"].create({
            "brand_id": brand.id,
            "name": "A3",
        })
        cls.fleet_vehicle = cls.env["fleet.vehicle"].create({
            "model_id": model.id,
            "driver_id": cls.documents_user.partner_id.id,
            "plan_to_change_car": False
        })

    def test_fleet_attachment(self):
        """
        Make sure the vehicle attachment is linked to the documents application

        Test Case:
        =========
            - Attach attachment to Audi vehicle
            - Check if the document is created
            - Check the res_id of the document
            - Check the res_model of the document
        """
        attachment_txt_test = self.env['ir.attachment'].with_user(self.env.user).create({
            'datas': TEXT,
            'name': 'fileText_test.txt',
            'mimetype': 'text/plain',
            'res_model': 'fleet.vehicle',
            'res_id': self.fleet_vehicle.id,
        })
        document = self.env['documents.document'].search([('attachment_id', '=', attachment_txt_test.id)])
        self.assertTrue(document.exists(), "It should have created a document")
        self.assertEqual(document.res_id, self.fleet_vehicle.id, "fleet record linked to the document ")
        self.assertEqual(document.owner_id, self.env.user, "default document owner is the current user")
        self.assertEqual(document.res_model, self.fleet_vehicle._name, "fleet model linked to the document")

    def test_disable_fleet_centralize_option(self):
        """
        Make sure that the document is not created when your Fleet Centralize is disabled.

        Test Case:
        =========
            - Disable the option Centralize your Fleet' documents option
            - Add an attachment to a fleet vehicle
            - Check whether the document is created or not
        """
        company = self.env.user.company_id
        company.documents_fleet_settings = False

        attachment_txt_test = self.env['ir.attachment'].create({
            'datas': TEXT,
            'name': 'fileText_test.txt',
            'mimetype': 'text/plain',
            'res_model': 'fleet.vehicle',
            'res_id': self.fleet_vehicle.id,
        })
        document = self.env['documents.document'].search([('attachment_id', '=', attachment_txt_test.id)])
        self.assertFalse(document.exists(), 'the document should not exist')

    def test_link_document_when_no_vehicle_exists(self):
        """
        Ensure that a document cannot be linked when no vehicles exist.

        Test Case:
        =========
            - Archive all vehicles to ensure no vehicle exists.
            - create a document in the fleet folder
            - Create a workflow rule to link to fleet.vehicle
            - Try to link the document using the workflow rule
            - Check that a UserError is raised
            - If a vehicle exists, it should be used as `default_resource_ref`.
        """
        self.env['fleet.vehicle'].search([]).write({
            'active': False
        })
        self.assertFalse(self.env['fleet.vehicle'].search([]), "There should be no active vehicles.")
        attachment = self.env['ir.attachment'].create({
            'name': "An Email without attachment",
            'type': 'binary',
            'raw':  '<p>A mail body</p>',
            'mimetype': 'application/documents-email',
            'res_model': 'documents.document',
        })
        document = self.env['documents.document'].create({
            'name': "An Email with attachment",
            'folder_id': self.fleet_folder.id,
            'attachment_id': attachment.id,
        })
        fleet_vehicle_model = self.env['ir.model'].search([('model', '=', 'fleet.vehicle')], limit=1)
        workflow_rule_link = self.env['documents.workflow.rule'].create({
            'domain_folder_id': self.fleet_folder.id,
            'name': 'workflow rule on link to record',
            'link_model': fleet_vehicle_model.id,
        })
        with self.assertRaises(UserError):
            workflow_rule_link.link_to_record(document)

        vehicle = self.env["fleet.vehicle"].create({
            "model_id": self.fleet_vehicle.model_id.id,
        })
        res = workflow_rule_link.link_to_record(document)
        context = res.get('context', {})
        self.assertEqual(context.get('default_resource_ref'), f"fleet.vehicle,{vehicle.id}")
