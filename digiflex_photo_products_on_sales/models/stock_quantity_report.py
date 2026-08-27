# -*- coding: utf-8 -*-
from odoo import models, api


class ReportStockQuantityPhoto(models.AbstractModel):
    _name = 'report.digiflex_photo_products_on_sales.report_stock_qty'
    _description = 'Reporte de Existencias de Productos (Con/Sin Foto)'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        wizard_id = data.get('wizard_id')
        wizard = self.env['stock.quantity.report.wizard'].browse(wizard_id) if wizard_id else False

        domain = [('location_id.usage', '=', 'internal')]

        if wizard:
            if wizard.company_id:
                domain.append(('company_id', '=', wizard.company_id.id))
            if wizard.location_ids:
                domain.append(('location_id', 'in', wizard.location_ids.ids))
            if wizard.category_ids:
                domain.append(('product_id.categ_id', 'child_of', wizard.category_ids.ids))
            if wizard.product_ids:
                domain.append(('product_id', 'in', wizard.product_ids.ids))
            if wizard.only_with_stock:
                domain.append(('quantity', '>', 0))

        quants = self.env['stock.quant'].search(domain, order='location_id, product_id')

        # Agrupar quants por producto y ubicación para evitar duplicados si aplica, o listar líneas detalladas
        grouped_lines = []
        for q in quants:
            grouped_lines.append({
                'product': q.product_id,
                'default_code': q.product_id.default_code or '',
                'product_name': q.product_id.display_name,
                'category': q.product_id.categ_id.complete_name,
                'location': q.location_id.display_name,
                'quantity': q.quantity,
                'reserved_quantity': q.reserved_quantity,
                'available_quantity': q.quantity - q.reserved_quantity,
                'uom': q.product_uom_id.name,
                'image': q.product_id.image_128 if (wizard and wizard.show_image) else False,
            })

        return {
            'doc_ids': docids,
            'doc_model': 'stock.quantity.report.wizard',
            'wizard': wizard,
            'lines': grouped_lines,
            'show_image': wizard.show_image if wizard else True,
            'company': wizard.company_id if (wizard and wizard.company_id) else self.env.company,
        }
