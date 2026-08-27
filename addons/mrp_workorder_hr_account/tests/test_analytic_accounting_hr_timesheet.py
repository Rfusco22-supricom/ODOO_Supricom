# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests.common import new_test_user
from odoo.tests import tagged
from odoo.addons.mrp_account.tests.test_analytic_account import TestMrpAnalyticAccount


@tagged('post_install', '-at_install')
class TestMrpAnalyticAccountHrTimesheet(TestMrpAnalyticAccount):

    def test_user_can_complete_mo_despite_accounting_restrictions(self):
        """Ensure that a user who has Manufacturing and Timesheet rights but no access
        to accounting can assign finished sn and validate the MO.
        """
        # check if hr_timesheet module is installed
        if 'hr_timesheet' not in self.env["ir.module.module"]._installed():
            self.skipTest("hr_timesheet module is not installed")
        user = new_test_user(self.env, login='fgh',
                             groups='base.group_user,mrp.group_mrp_user,hr_timesheet.group_hr_timesheet_user')
        user.employee_id.write({
            'user_id': user.id,
            'hourly_cost': 100,
        })
        self.bom.operation_ids.workcenter_id.employee_ids = False
        self.bom.product_id.tracking = 'serial'
        mo = self.env['mrp.production'].create({
            'product_id': self.product.id,
            'product_qty': 1,
            'bom_id': self.bom.id,
            'analytic_distribution': {str(self.analytic_account.id): 100.0}
        })
        mo = mo.with_user(user)
        mo.action_confirm()
        wo = mo.workorder_ids
        wo.button_start()
        mo.action_generate_serial()
        wo.button_finish()
        self.assertEqual(wo.state, 'done')
        mo.button_mark_done()
        self.assertEqual(mo.state, 'done')
