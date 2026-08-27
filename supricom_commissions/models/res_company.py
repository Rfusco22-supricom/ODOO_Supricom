from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = "res.company"

    commission_base_type = fields.Selection(
        [("margin", "Rentabilidad"), ("amount", "Venta Total")],
        string="Base de Comisión",
        default="margin",
        help="Define si la comisión se calcula sobre la rentabilidad (Precio - Costo) o sobre el monto total de la venta.",
    )
    commission_target_mode = fields.Selection(
        [("individual", "Individual (Por Vendedor)"), ("branch", "Sucursal (Compañía Global)")],
        string="Modo de Meta de Cumplimiento",
        default="individual",
        help="Si es 'Sucursal', evalúa el % de cumplimiento sumando las ventas de todos los vendedores y comparándolo con la meta global de la compañía.",
    )
    commission_use_targets = fields.Boolean(
        string="Usar Metas de Cumplimiento",
        default=True,
        help="Si está activo, se usará la Matriz de Comisiones para determinar el % basado en cumplimiento. Si está inactivo, se usará la tasa base (0% cumplimiento) de la matriz.",
    )
    commission_use_min_price = fields.Boolean(
        string="Validar Precio Mínimo",
        default=True,
        help="Si está activo, se penalizarán o marcarán las ventas por debajo del precio mínimo.",
    )
    commission_show_profitability = fields.Boolean(
        string="Mostrar Costo y Rentabilidad",
        default=True,
        help="Mostrar las columnas de Costo, Rentabilidad y Base Pagada en las vistas y reportes.",
    )
    commission_credit_threshold = fields.Float(
        string="Umbral de Crédito",
        default=2000.0,
        help="Facturas de crédito menores a este monto se pagan en el mes (como contado). Mayores a este monto quedan pendientes hasta su cobro.",
    )
    commission_payment_tolerance = fields.Float(
        string="Tolerancia de Pago Completo (%)",
        default=5.0,
        help="Margen de tolerancia para considerar una factura 100% cobrada (útil para retenciones de impuestos).",
    )
    commission_use_pricelist_mapping = fields.Boolean(
        string="Mapeo Dinámico de Listas de Precios",
        default=False,
        help="Permite configurar por cada lista de precios cuál será la lista equivalente a usar para el recálculo de comisiones.",
    )
    commission_strict_full_payment = fields.Boolean(
        string="Comisión solo por Factura Cobrada Completa",
        default=True,
        help="Si está activo, las facturas a crédito solo pagan comisión si están 100% cobradas.",
    )
    commission_cash_rate = fields.Float(
        string="% Comisión (Contado)",
        default=0.5,
        help="Porcentaje base para facturas de contado.",
    )
    commission_credit_rate = fields.Float(
        string="% Comisión (Crédito)",
        default=0.5,
        help="Porcentaje base para facturas de crédito.",
    )
    commission_grace_days = fields.Integer(
        string="Días de Gracia (Mora)",
        default=3,
        help="Días adicionales después del vencimiento antes de considerar el pago como mora.",
    )
    commission_min_target_pct = fields.Float(
        string="% Meta Mínima de Ventas",
        default=80.0,
        help="Porcentaje mínimo de cumplimiento de meta para generar comisión (ej. 80.0 para 80%). Si no lo alcanza, 0% comisión.",
    )
    commission_max_target_cap = fields.Float(
        string="Tope Máximo de Meta (%)",
        default=150.0,
        help="Tope máximo de porcentaje de cumplimiento de meta (ej. 150.0 para 150%).",
    )
    commission_collection_matrix_ids = fields.One2many(
        "commission.collection.matrix",
        "company_id",
        string="Matriz de Cobranza (Morosidad)",
        help="Reglas de penalización por días de retraso post-vencimiento.",
    )

    commission_use_fixed_amount = fields.Boolean(
        string="Habilitar Comisión Fija por Producto",
        default=True,
        help="Permite definir montos fijos de comisión por producto.",
    )
    commission_fixed_product_ids = fields.Many2many(
        "product.product",
        string="Productos Específicos con Comisión Fija",
        help="Si se especifican, solo estos productos aplicarán para comisiones de monto fijo.",
    )
    commission_fixed_product_tag_ids = fields.Many2many(
        "product.tag",
        string="Etiquetas de Producto con Comisión Fija",
        help="Productos que tengan estas etiquetas aplicarán para comisión de monto fijo.",
    )
    commission_fixed_product_category_ids = fields.Many2many(
        "product.category",
        string="Categorías de Producto con Comisión Fija",
        help="Productos dentro de estas categorías aplicarán para comisión de monto fijo.",
    )

    commission_use_fixed_percentage = fields.Boolean(
        string="Habilitar Comisión % Fijo por Producto",
        default=True,
        help="Permite definir un porcentaje de comisión fijo por producto, ignorando la matriz.",
    )
    commission_fixed_pct_product_ids = fields.Many2many(
        "product.product",
        relation="res_company_comm_fixed_pct_prod_rel",
        string="Productos Específicos con % Fijo",
        help="Solo estos productos aplicarán para comisiones de % fijo.",
    )
    commission_fixed_pct_product_tag_ids = fields.Many2many(
        "product.tag",
        relation="res_company_comm_fixed_pct_tag_rel",
        string="Etiquetas de Producto con % Fijo",
        help="Productos con estas etiquetas aplicarán para comisión de % fijo.",
    )
    commission_fixed_pct_product_category_ids = fields.Many2many(
        "product.category",
        relation="res_company_comm_fixed_pct_categ_rel",
        string="Categorías de Producto con % Fijo",
        help="Productos en estas categorías aplicarán para comisión de % fijo.",
    )

    @api.constrains('commission_fixed_product_ids', 'commission_fixed_pct_product_ids')
    def _check_fixed_commission_products_overlap(self):
        for record in self:
            overlap = set(record.commission_fixed_product_ids.ids).intersection(set(record.commission_fixed_pct_product_ids.ids))
            if overlap:
                product_names = ", ".join(self.env['product.product'].browse(list(overlap)).mapped('display_name'))
                raise ValidationError(f"No puede configurar el mismo producto para 'Monto Fijo' y '% Fijo' simultáneamente. Productos duplicados: {product_names}")

    @api.constrains('commission_fixed_product_tag_ids', 'commission_fixed_pct_product_tag_ids')
    def _check_fixed_commission_tags_overlap(self):
        for record in self:
            overlap = set(record.commission_fixed_product_tag_ids.ids).intersection(set(record.commission_fixed_pct_product_tag_ids.ids))
            if overlap:
                tag_names = ", ".join(self.env['product.tag'].browse(list(overlap)).mapped('name'))
                raise ValidationError(f"No puede configurar la misma etiqueta para 'Monto Fijo' y '% Fijo' simultáneamente. Etiquetas duplicadas: {tag_names}")

    @api.constrains('commission_fixed_product_category_ids', 'commission_fixed_pct_product_category_ids')
    def _check_fixed_commission_categories_overlap(self):
        for record in self:
            overlap = set(record.commission_fixed_product_category_ids.ids).intersection(set(record.commission_fixed_pct_product_category_ids.ids))
            if overlap:
                category_names = ", ".join(self.env['product.category'].browse(list(overlap)).mapped('display_name'))
                raise ValidationError(f"No puede configurar la misma categoría para 'Monto Fijo' y '% Fijo' simultáneamente. Categorías duplicadas: {category_names}")

