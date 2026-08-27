from odoo import fields, models


class SaleReport(models.Model):
    _inherit = 'sale.report'

    spiff_brand_id = fields.Many2one('spiff.brand', string='Marca (SPIFF)', readonly=True)

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['spiff_brand_id'] = "t.spiff_brand_id"
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += ", t.spiff_brand_id"
        return res
