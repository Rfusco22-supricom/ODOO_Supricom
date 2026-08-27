# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class DigiflexSalesMarginReport(models.Model):
    _name = 'digiflex.sales.margin.report'
    _description = 'Reporte de Ventas con Utilidad y Margen sobre Costo'
    _auto = False
    _order = 'invoice_date desc, document_number desc, id desc'

    invoice_id = fields.Many2one('account.move', string='Documento / Factura', readonly=True)
    move_line_id = fields.Many2one('account.move.line', string='Línea de Factura', readonly=True)
    invoice_date = fields.Date(string='Fecha', readonly=True)
    document_number = fields.Char(string='Número', readonly=True)

    partner_id = fields.Many2one('res.partner', string='Cliente', readonly=True)
    partner_ref = fields.Char(string='Cuenta', readonly=True, help='Código o referencia del cliente')
    partner_name = fields.Char(string='Nombre Cliente', readonly=True)

    salesperson_id = fields.Many2one('res.users', string='Vendedor', readonly=True)
    salesperson_name = fields.Char(string='Nombre Vendedor', readonly=True)

    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    product_template_id = fields.Many2one('product.template', string='Plantilla de Producto', readonly=True)
    product_type = fields.Selection([
        ('product', 'Productos'),
        ('service', 'Servicios'),
    ], string='Tipo de Venta', readonly=True)
    is_service = fields.Boolean(string='Es Servicio', readonly=True)

    sale_condition = fields.Selection([
        ('cash', 'Contado'),
        ('credit', 'Crédito'),
    ], string='Condición', readonly=True)

    movement_type = fields.Selection([
        ('sales', 'Venta'),
        ('refunds', 'Devolución'),
    ], string='Tipo Movimiento', readonly=True)

    quantity = fields.Float(string='Unidades', readonly=True, group_operator='sum')
    cost_unit = fields.Float(string='Costo Unitario', readonly=True)
    cost_total = fields.Monetary(string='Costo', currency_field='currency_id', readonly=True, group_operator='sum')
    sale_total = fields.Monetary(string='Venta', currency_field='currency_id', readonly=True, group_operator='sum')
    margin_profit = fields.Monetary(string='Utilidad', currency_field='currency_id', readonly=True, group_operator='sum')
    margin_cost_pct = fields.Float(string='MargenC (%)', readonly=True, group_operator='avg', help='Margen sobre Costo: (Utilidad / Costo) * 100')

    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)

        # Dynamic check for localized document number columns (Panama FEL / Venezuela Nro Control)
        has_fel_pa = tools.column_exists(self.env.cr, 'account_move', 'fel_pa_document_number')
        has_nro_ctrl = tools.column_exists(self.env.cr, 'account_move', 'nro_ctrl')
        has_line_cost = tools.column_exists(self.env.cr, 'account_move_line', 'product_cost')
        has_pt_cost_usd = tools.column_exists(self.env.cr, 'product_template', 'standard_price_usd')
        has_pp_cost_usd = tools.column_exists(self.env.cr, 'product_product', 'standard_price_usd')

        if has_fel_pa and has_nro_ctrl:
            doc_num_expr = "COALESCE(NULLIF(am.fel_pa_document_number, ''), NULLIF(am.nro_ctrl, ''), am.name, '/')"
        elif has_fel_pa:
            doc_num_expr = "COALESCE(NULLIF(am.fel_pa_document_number, ''), am.name, '/')"
        elif has_nro_ctrl:
            doc_num_expr = "COALESCE(NULLIF(am.nro_ctrl, ''), am.name, '/')"
        else:
            doc_num_expr = "COALESCE(am.name, '/')"

        line_cost_expr = "NULLIF(aml.product_cost, 0)" if has_line_cost else "NULL"
        pt_cost_usd_expr = "pt.standard_price_usd" if has_pt_cost_usd else "NULL"
        pp_cost_usd_expr = "pp.standard_price_usd" if has_pp_cost_usd else "NULL"

        # Cost calculation based on company currency:
        # If company currency is USD -> use standard_price (ir_property/standard_price_usd)
        # If company currency is NOT USD -> use standard_price_usd
        cost_unit_expr = """
            CASE 
                WHEN cur.name = 'USD' THEN 
                    COALESCE(%(line_cost)s, prop_cost_prod.value_float, prop_cost_tmpl.value_float, %(pt_cost_usd)s, %(pp_cost_usd)s, 0.0)
                ELSE 
                    COALESCE(%(line_cost)s, %(pt_cost_usd)s, %(pp_cost_usd)s, prop_cost_prod.value_float, prop_cost_tmpl.value_float, 0.0)
            END
        """ % {
            'line_cost': line_cost_expr,
            'pt_cost_usd': pt_cost_usd_expr,
            'pp_cost_usd': pp_cost_usd_expr,
        }

        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    aml.id AS id,
                    aml.id AS move_line_id,
                    am.id AS invoice_id,
                    COALESCE(am.invoice_date, am.date) AS invoice_date,
                    %(doc_num)s AS document_number,
                    am.partner_id AS partner_id,
                    COALESCE(NULLIF(rp.ref, ''), CAST(rp.id AS VARCHAR)) AS partner_ref,
                    COALESCE(rp.name, '/') AS partner_name,
                    COALESCE(am.invoice_user_id, rp.user_id) AS salesperson_id,
                    COALESCE(rp_user.name, ru.login, '/') AS salesperson_name,
                    aml.product_id AS product_id,
                    pp.product_tmpl_id AS product_template_id,
                    CASE 
                        WHEN COALESCE(pt.detailed_type, pt.type) = 'service' THEN 'service'
                        ELSE 'product'
                    END AS product_type,
                    CASE 
                        WHEN COALESCE(pt.detailed_type, pt.type) = 'service' THEN TRUE
                        ELSE FALSE
                    END AS is_service,
                    CASE 
                        WHEN am.invoice_payment_term_id IS NULL THEN 'cash'
                        ELSE 'credit'
                    END AS sale_condition,
                    CASE 
                        WHEN am.move_type = 'out_invoice' THEN 'sales'
                        ELSE 'refunds'
                    END AS movement_type,
                    CASE 
                        WHEN am.move_type = 'out_invoice' THEN aml.quantity
                        ELSE -aml.quantity
                    END AS quantity,
                    (%(cost_unit)s) AS cost_unit,
                    CASE 
                        WHEN am.move_type = 'out_invoice' THEN (aml.quantity * (%(cost_unit)s))
                        ELSE -(aml.quantity * (%(cost_unit)s))
                    END AS cost_total,
                    CASE 
                        WHEN am.move_type = 'out_invoice' THEN aml.price_subtotal
                        ELSE -aml.price_subtotal
                    END AS sale_total,
                    CASE 
                        WHEN am.move_type = 'out_invoice' THEN (aml.price_subtotal - (aml.quantity * (%(cost_unit)s)))
                        ELSE ((-aml.price_subtotal) - (-(aml.quantity * (%(cost_unit)s))))
                    END AS margin_profit,
                    CASE 
                        WHEN (aml.quantity * (%(cost_unit)s)) != 0 THEN 
                            (((aml.price_subtotal - (aml.quantity * (%(cost_unit)s))) / (aml.quantity * (%(cost_unit)s))) * 100.0)
                        ELSE 
                            CASE WHEN aml.price_subtotal > 0 THEN 100.0 ELSE 0.0 END
                    END AS margin_cost_pct,
                    am.company_id AS company_id,
                    COALESCE(aml.currency_id, am.currency_id) AS currency_id
                FROM account_move_line aml
                JOIN account_move am ON aml.move_id = am.id
                LEFT JOIN res_company rc ON am.company_id = rc.id
                LEFT JOIN res_currency cur ON rc.currency_id = cur.id
                LEFT JOIN res_partner rp ON am.partner_id = rp.id
                LEFT JOIN res_users ru ON COALESCE(am.invoice_user_id, rp.user_id) = ru.id
                LEFT JOIN res_partner rp_user ON ru.partner_id = rp_user.id
                LEFT JOIN product_product pp ON aml.product_id = pp.id
                LEFT JOIN product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN ir_property prop_cost_prod ON (
                    prop_cost_prod.name = 'standard_price'
                    AND prop_cost_prod.res_id = 'product.product,' || aml.product_id
                    AND prop_cost_prod.company_id = am.company_id
                )
                LEFT JOIN ir_property prop_cost_tmpl ON (
                    prop_cost_tmpl.name = 'standard_price'
                    AND prop_cost_tmpl.res_id = 'product.template,' || pp.product_tmpl_id
                    AND prop_cost_tmpl.company_id = am.company_id
                )
                WHERE am.state = 'posted'
                  AND am.move_type IN ('out_invoice', 'out_refund')
                  AND (aml.display_type = 'product' OR (aml.display_type IS NULL AND aml.product_id IS NOT NULL))
            )
        """ % {
            'table': self._table,
            'doc_num': doc_num_expr,
            'cost_unit': cost_unit_expr,
        })

    def action_open_invoice(self):
        self.ensure_one()
        return {
            'name': 'Documento / Factura',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }
