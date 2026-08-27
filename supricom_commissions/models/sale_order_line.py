from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_min_price_sale = fields.Boolean(
        string="Venta a Precio Mínimo",
        compute="_compute_is_min_price_sale",
        store=True,
        help="Calculado automáticamente: Verdadero si el precio unitario (convertido) es igual o menor al precio mínimo del producto.",
    )

    @api.depends("price_unit", "product_id.min_price", "order_id.currency_id", "order_id.date_order")
    def _compute_is_min_price_sale(self):
        for line in self:
            line.is_min_price_sale = False
            if line.product_id and line.product_id.min_price > 0:
                min_price = line.product_id.min_price
                min_price_currency = line.product_id.min_price_currency_id
                sale_currency = line.order_id.currency_id
                
                # Convert sale price_unit to min_price currency for comparison
                if sale_currency and min_price_currency and sale_currency != min_price_currency:
                    price_in_min_curr = sale_currency._convert(
                        line.price_unit,
                        min_price_currency,
                        line.order_id.company_id,
                        line.order_id.date_order or fields.Date.today(),
                    )
                else:
                    price_in_min_curr = line.price_unit
                
                if price_in_min_curr <= min_price:
                    line.is_min_price_sale = True

    @api.constrains("price_unit", "product_id")
    def _check_min_price(self):
        for line in self:
            # Check if validation is bypassed by Manager
            if line.order_id.allow_below_min_price:
                continue
            
            # Check if min_price is enabled
            if not line.company_id.commission_use_min_price:
                continue

            if line.product_id and line.product_id.min_price > 0:
                min_price = line.product_id.min_price
                min_price_currency = line.product_id.min_price_currency_id
                sale_currency = line.order_id.currency_id
                
                if sale_currency and min_price_currency and sale_currency != min_price_currency:
                    price_in_min_curr = sale_currency._convert(
                        line.price_unit,
                        min_price_currency,
                        line.order_id.company_id,
                        line.order_id.date_order or fields.Date.today(),
                    )
                else:
                    price_in_min_curr = line.price_unit
                
                if price_in_min_curr < min_price:
                    raise ValidationError(
                        f"El precio unitario para {line.product_id.name} ({price_in_min_curr:.2f} {min_price_currency.name}) "
                        f"no puede ser menor al precio mínimo establecido ({min_price:.2f} {min_price_currency.name})."
                    )

