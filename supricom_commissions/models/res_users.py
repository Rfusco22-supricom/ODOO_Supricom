from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # Campo para mostrar en la vista de usuarios sin modo desarrollador
    is_commission_manager = fields.Boolean(
        string="Gerente de Comisiones",
        compute="_compute_is_commission_manager",
        inverse="_inverse_is_commission_manager",
        groups="base.group_system",
    )

    def _compute_is_commission_manager(self):
        commission_manager_group = self.env.ref(
            "supricom_commissions.group_commission_manager", raise_if_not_found=False
        )
        for user in self:
            user.is_commission_manager = (
                commission_manager_group in user.groups_id
                if commission_manager_group
                else False
            )

    def _inverse_is_commission_manager(self):
        commission_manager_group = self.env.ref(
            "supricom_commissions.group_commission_manager", raise_if_not_found=False
        )
        if not commission_manager_group:
            return
        for user in self:
            if user.is_commission_manager:
                user.groups_id = [(4, commission_manager_group.id)]
            else:
                user.groups_id = [(3, commission_manager_group.id)]
