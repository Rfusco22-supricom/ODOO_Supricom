# models/sale_order_extension.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        self.ensure_one()
        
        # 1. Identify unique brands in order lines
        brands = self.order_line.mapped('product_id.product_tmpl_id.spiff_brand_id')
        
        # Check if immediate payment
        is_immediate = self.payment_term_id and self.payment_term_id.name and 'inmediato' in self.payment_term_id.name.lower()
        
        if is_immediate:
            # Check if any brand actually has extension days
            brands_with_ext = brands.filtered(lambda b: b.credit_extension_days > 0)
            if brands_with_ext:
                brand_names = ", ".join(brands_with_ext.mapped('name'))
                self.message_post(
                    body=_(
                        "⚠️ Extensión de crédito no aplicada: No se aplicaron los días de crédito adicionales de las marcas (%s) porque el término de pago es 'Pago inmediato'.",
                        brand_names
                    )
                )

        # 2. Check if credit extension applies (Single brand with extension days > 0)
        if len(brands) == 1 and brands.credit_extension_days > 0 and not self._context.get('skip_credit_extension') and not is_immediate:
            extension_days = brands.credit_extension_days
            current_term = self.payment_term_id
            
            # Calculate target days
            current_days = 0
            if current_term and current_term.line_ids:
                # Assuming simple payment terms with one line for simplicity in this logic
                # or taking the maximum days from lines.
                current_days = max(current_term.line_ids.mapped('nb_days'))
            
            target_days = current_days + extension_days
            
            # 3. Look for existing payment term (Simple term with matching days)
            new_term = self.env['account.payment.term'].search([
                ('line_ids.nb_days', '=', target_days),
                ('line_ids.value', '=', 'percent'),
                ('line_ids.value_amount', '=', 100.0)
            ], limit=1)
            
            if new_term:
                self.payment_term_id = new_term
                self.message_post(body=_(
                    "📅 Términos de pago extendidos automáticamente por la marca %s (+%s días extra).",
                    brands.name, extension_days
                ))
            else:
                # 4. If not found, open wizard to ask
                return {
                    'name': _('Confirmado con Extensión de Crédito'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'spiff.credit.extension.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_order_id': self.id,
                        'default_new_days': target_days,
                        'default_extension_days': extension_days,
                        'default_brand_id': brands.id,
                        'default_current_term_id': self.payment_term_id.id if self.payment_term_id else False,
                    }
                }
        elif len(brands) > 1 and not self._context.get('skip_multi_brand_check') and not is_immediate:
            # Check if any brand in the set has extension days
            brands_with_extension = brands.filtered(lambda b: b.credit_extension_days > 0)
            if brands_with_extension:
                brand_names = ", ".join(brands_with_extension.mapped('name'))
                return {
                    'name': _('Advertencia: Múltiples Marcas'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'spiff.multi.brand.warning',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_order_id': self.id,
                        'default_brand_names': brand_names,
                    }
                }

        return super(SaleOrder, self).action_confirm()
