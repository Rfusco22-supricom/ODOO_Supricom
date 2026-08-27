# -*- coding: utf-8 -*-

from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    quotation_only = fields.Boolean(
        string='Solo Cotización (Quotation Only)',
        default=False,
        help="Si está marcado, se desactivará el flujo de pago y facturación y se convertirá en un flujo de cotizaciones.",
    )

    def _get_checkout_step_list(self):
        steps = super(Website, self)._get_checkout_step_list()
        if self.quotation_only:
            for step in steps:
                # Cambiar 'Payment' a 'Cotización' en el Wizard
                if 'website_sale.payment' in step[0]:
                    step[1]['name'] = 'Cotización'
                # Cambiar 'Continue shopping' a 'Volver a la Tienda' y 'Review Order' a 'Revisar Carrito'
                if 'website_sale.cart' in step[0]:
                    step[1]['name'] = 'Revisar Carrito'
                    step[1]['back_button'] = 'Volver a la Tienda'
        return steps
