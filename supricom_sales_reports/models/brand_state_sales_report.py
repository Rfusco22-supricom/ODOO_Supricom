from odoo import models, fields, tools

class SupricomBrandStateSalesReport(models.Model):
    _name = 'supricom.brand.state.sales.report'
    _description = 'Reporte de Ventas por Marca y Estado'
    _auto = False

    state_id = fields.Many2one('res.country.state', string='Estado', readonly=True)
    spiff_brand_id = fields.Many2one('spiff.brand', string='Marca (SPIFF)', readonly=True)
    price_subtotal = fields.Float(string='Monto Total Vendido', readonly=True)
    date_order = fields.Datetime(string='Fecha', readonly=True)
    order_id = fields.Many2one('sale.order', string='Orden de Venta', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    product_uom_qty = fields.Float(string='Cantidad', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    l.id as id,
                    l.order_id as order_id,
                    s.partner_id as partner_id,
                    p.state_id as state_id,
                    t.spiff_brand_id as spiff_brand_id,
                    l.product_id as product_id,
                    l.product_uom_qty as product_uom_qty,
                    l.price_subtotal as price_subtotal,
                    s.date_order as date_order,
                    s.company_id as company_id
                FROM sale_order_line l
                JOIN sale_order s ON (l.order_id = s.id)
                JOIN res_partner p ON (s.partner_id = p.id)
                JOIN product_product pr ON (l.product_id = pr.id)
                JOIN product_template t ON (pr.product_tmpl_id = t.id)
                WHERE s.state IN ('sale', 'done') AND l.display_type IS NULL
            )
        """ % (self._table,))

    def action_open_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Orden de Venta',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.order_id.id,
            'target': 'current',
        }
