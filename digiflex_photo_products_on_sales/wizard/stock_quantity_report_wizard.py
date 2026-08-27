# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockQuantityReportWizard(models.TransientModel):
    _name = 'stock.quantity.report.wizard'
    _description = 'Asistente de Reporte de Existencia con/sin Foto'

    company_id = fields.Many2one(
        'res.company',
        string="Compañía",
        required=True,
        default=lambda self: self.env.company
    )
    location_ids = fields.Many2many(
        'stock.location',
        string="Ubicaciones",
        domain="[('usage', '=', 'internal')]",
        help="Si se deja vacío, se incluirán todas las ubicaciones internas."
    )
    category_ids = fields.Many2many(
        'product.category',
        string="Categorías de Producto",
        help="Filtrar por categorías específicas."
    )
    product_ids = fields.Many2many(
        'product.product',
        string="Productos",
        help="Filtrar por productos específicos."
    )
    show_image = fields.Boolean(
        string="Incluir Foto del Producto",
        default=True,
        help="Marcar para incluir la imagen del producto en el reporte PDF."
    )
    only_with_stock = fields.Boolean(
        string="Solo con Existencia > 0",
        default=True,
        help="Mostrar únicamente los productos que posean cantidad a mano mayor a cero."
    )

    def action_print_report(self):
        self.ensure_one()
        data = {
            'wizard_id': self.id,
            'form': self.read()[0]
        }
        return self.env.ref('digiflex_photo_products_on_sales.action_report_stock_quantity_photo').report_action(self, data=data)
