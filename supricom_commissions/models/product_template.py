from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = "product.template"

    min_price_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda Precio Mínimo",
        default=lambda self: self.env.ref("base.USD", raise_if_not_found=False),
        help="Moneda en la que está definido el precio mínimo (por defecto USD).",
    )
    min_price = fields.Monetary(
        string="Precio Mínimo",
        currency_field="min_price_currency_id",
        help="Precio mínimo de venta permitido para este producto (en la moneda especificada).",
    )
    is_special_commission = fields.Boolean(
        string="Comisión Especial",
        help="Si se marca, este producto usa una tasa fija de comisión en lugar de la matriz estándar.",
    )
    # fixed_commission_rate = fields.Float(
    #     string="% Comisión Fija",
    #     help="Porcentaje de comisión fijo si el producto tiene comisión especial.",
    # )
    commission_type = fields.Selection(
        [("percentage", "Matriz de Cumplimiento"), ("fixed", "Monto Fijo ($)")],
        string="Tipo de Comisión",
        default="percentage",
        help="Determina si el producto paga comisión por porcentaje o un bono fijo en dólares.",
    )
    commission_fixed_amount = fields.Float(
        string="Monto Fijo Comisión ($)",
        help="Monto fijo en dólares que se pagará por CADA unidad vendida de este producto.",
    )
    x_comision_fija_producto = fields.Float(
        string="% Comisión Fija por Producto",
        help="Si este valor es mayor a 0, se usará como tasa de comisión fija ignorando la matriz de cumplimiento.",
    )

    commission_use_fixed_amount = fields.Boolean(
        compute="_compute_commission_settings",
        string="Usa Monto Fijo Global",
    )
    commission_use_fixed_percentage = fields.Boolean(
        compute="_compute_commission_settings",
        string="Usa % Fijo Global",
    )
    commission_is_explicit_amount = fields.Boolean(
        compute="_compute_commission_settings",
        string="Es Monto Fijo Explícito",
    )
    commission_is_explicit_percentage = fields.Boolean(
        compute="_compute_commission_settings",
        string="Es % Fijo Explícito",
    )

    @api.depends_context('company')
    def _compute_commission_settings(self):
        for record in self:
            company = self.env.company
            
            # Evaluar Monto Fijo
            record.commission_is_explicit_amount = False
            if not company.commission_use_fixed_amount:
                record.commission_use_fixed_amount = False
            else:
                amt_prods = company.commission_fixed_product_ids
                amt_tags = company.commission_fixed_product_tag_ids
                amt_categs = company.commission_fixed_product_category_ids
                
                if not amt_prods and not amt_tags and not amt_categs:
                    record.commission_use_fixed_amount = True
                else:
                    in_prod = any(v.id in amt_prods.ids for v in record.product_variant_ids) if amt_prods else False
                    in_categ = record.categ_id.id in amt_categs.ids if amt_categs else False
                    in_tag = any(tag.id in amt_tags.ids for tag in record.product_tag_ids) if hasattr(record, 'product_tag_ids') and amt_tags else False
                    if in_prod or in_categ or in_tag:
                        record.commission_use_fixed_amount = True
                        record.commission_is_explicit_amount = True
                    else:
                        record.commission_use_fixed_amount = False

            # Evaluar Porcentaje Fijo
            record.commission_is_explicit_percentage = False
            if not company.commission_use_fixed_percentage:
                record.commission_use_fixed_percentage = False
            else:
                pct_prods = company.commission_fixed_pct_product_ids
                pct_tags = company.commission_fixed_pct_product_tag_ids
                pct_categs = company.commission_fixed_pct_product_category_ids
                
                if not pct_prods and not pct_tags and not pct_categs:
                    record.commission_use_fixed_percentage = True
                else:
                    in_prod = any(v.id in pct_prods.ids for v in record.product_variant_ids) if pct_prods else False
                    in_categ = record.categ_id.id in pct_categs.ids if pct_categs else False
                    in_tag = any(tag.id in pct_tags.ids for tag in record.product_tag_ids) if hasattr(record, 'product_tag_ids') and pct_tags else False
                    if in_prod or in_categ or in_tag:
                        record.commission_use_fixed_percentage = True
                        record.commission_is_explicit_percentage = True
                    else:
                        record.commission_use_fixed_percentage = False
        for record in self:
            company = self.env.company
            
            # Evaluar Monto Fijo
            if not company.commission_use_fixed_amount:
                record.commission_use_fixed_amount = False
            else:
                amt_prods = company.commission_fixed_product_ids
                amt_tags = company.commission_fixed_product_tag_ids
                amt_categs = company.commission_fixed_product_category_ids
                
                if not amt_prods and not amt_tags and not amt_categs:
                    record.commission_use_fixed_amount = True
                else:
                    in_prod = any(v.id in amt_prods.ids for v in record.product_variant_ids) if amt_prods else False
                    in_categ = record.categ_id.id in amt_categs.ids if amt_categs else False
                    in_tag = any(tag.id in amt_tags.ids for tag in record.product_tag_ids) if hasattr(record, 'product_tag_ids') and amt_tags else False
                    record.commission_use_fixed_amount = bool(in_prod or in_categ or in_tag)

            # Evaluar Porcentaje Fijo
            if not company.commission_use_fixed_percentage:
                record.commission_use_fixed_percentage = False
            else:
                pct_prods = company.commission_fixed_pct_product_ids
                pct_tags = company.commission_fixed_pct_product_tag_ids
                pct_categs = company.commission_fixed_pct_product_category_ids
                
                if not pct_prods and not pct_tags and not pct_categs:
                    record.commission_use_fixed_percentage = True
                else:
                    in_prod = any(v.id in pct_prods.ids for v in record.product_variant_ids) if pct_prods else False
                    in_categ = record.categ_id.id in pct_categs.ids if pct_categs else False
                    in_tag = any(tag.id in pct_tags.ids for tag in record.product_tag_ids) if hasattr(record, 'product_tag_ids') and pct_tags else False
                    record.commission_use_fixed_percentage = bool(in_prod or in_categ or in_tag)
