from odoo import models, fields, tools

class SupricomNewCustomerSalesReport(models.Model):
    _name = 'supricom.new.customer.sales.report'
    _description = 'Reporte de Clientes Nuevos y su Primera Compra'
    _auto = False

    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    first_order_id = fields.Many2one('sale.order', string='Primera Orden', readonly=True)
    first_order_date = fields.Datetime(string='Fecha Primera Orden', readonly=True)
    first_order_amount = fields.Float(string='Monto Primera Compra', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH ordered_sales AS (
                    SELECT 
                        id,
                        partner_id,
                        company_id,
                        date_order as first_order_date,
                        amount_total as first_order_amount,
                        ROW_NUMBER() OVER(PARTITION BY partner_id ORDER BY date_order ASC, id ASC) as rn
                    FROM sale_order
                    WHERE state IN ('sale', 'done')
                )
                SELECT 
                    id,
                    partner_id,
                    id as first_order_id,
                    company_id,
                    first_order_date,
                    first_order_amount
                FROM ordered_sales
                WHERE rn = 1
            )
        """ % (self._table,))

    def action_open_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Primera Orden',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.first_order_id.id,
            'target': 'current',
        }
