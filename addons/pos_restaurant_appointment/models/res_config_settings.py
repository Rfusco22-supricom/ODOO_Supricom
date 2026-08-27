from odoo import fields, models, Command


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_appointment_type_ids = fields.Many2many(related="pos_config_id.appointment_type_ids", readonly=False)

    def set_values(self):
        res = super().set_values()
        is_group_pos_user = self.env.user.has_group('point_of_sale.group_pos_user')
        if is_group_pos_user and not self.pos_module_pos_restaurant_appointment:
            self.pos_appointment_type_ids = [Command.clear()]
        return res
