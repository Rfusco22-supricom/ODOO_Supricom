from odoo import models, fields

class RecreatePickingWizard(models.TransientModel):
    _name = 'sale.order.recreate.picking.wizard'
    _description = 'Recrear Despacho Wizard'

    sale_order_id = fields.Many2one('sale.order', string="Orden de Venta")

    def action_recreate(self):
        sale_order = self.sale_order_id or self.env['sale.order'].browse(self.env.context.get('active_id'))
        if sale_order:
            # Recreate pickings
            sale_order.order_line._action_launch_stock_rule()
            
            # Now set the autorizar_despacho to True and write
            sale_order.write({'autorizar_despacho': True})
