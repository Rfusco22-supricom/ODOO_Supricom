# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models
from odoo.tools import format_amount

class ProjectUpdate(models.Model):
    _inherit = 'project.update'

    @api.model
    def _get_template_values(self, project):
        vals = super()._get_template_values(project)
        if project.analytic_account_id and self.user_has_groups('account.group_account_readonly'):
            vals['show_activities'] = project.budget or vals.get('show_activities')
            vals['show_profitability'] = project.budget or vals.get('show_profitability')
            budget = project.budget
            amount_spent = project._get_budget_items()['total']['spent']
            remaining_budget = budget - amount_spent
            vals['budget'] = {
                'percentage': abs(round((amount_spent / budget) * 100 if budget != 0 and amount_spent else 0, 0)),
                'amount': format_amount(self.env, budget, project.currency_id),
                'spent_budget': format_amount(self.env, amount_spent, project.currency_id),
                'remaining_budget': format_amount(self.env, remaining_budget, project.currency_id),
                'remaining_budget_percentage': abs(round((remaining_budget / budget) * 100 if budget != 0 else 0, 0)),
                'is_revenue_budget': budget >= 0,
            }
        return vals
