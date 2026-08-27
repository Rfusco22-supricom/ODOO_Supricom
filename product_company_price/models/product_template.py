# -*- coding: utf-8 -*-

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    company_sale_price = fields.Float(
        string="Precio Base",
        compute='_compute_company_sale_price',
        inverse='_inverse_company_sale_price',
        store=False,
        digits='Product Price',
    )

    company_sale_price_usd = fields.Float(
        string="Precio Base USD",
        compute='_compute_company_sale_price',
        inverse='_inverse_company_sale_price_usd',
        store=False,
        digits='Product Price',
    )

    company_has_dual_currency = fields.Boolean(
        string="Compañía con doble moneda",
        compute='_compute_company_has_dual_currency',
        store=False,
    )

    company_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string="Moneda de la compañía",
        compute='_compute_company_currency_id',
        store=False,
    )

    @api.depends_context('company')
    def _compute_company_has_dual_currency(self):
        """True si la moneda base de la compañía activa NO es USD.
        En ese caso tiene sentido mostrar el precio en USD como referencia.
        """
        has_dual = self.env.company.currency_id.name != 'USD'
        for template in self:
            template.company_has_dual_currency = has_dual

    @api.depends_context('company')
    def _compute_company_currency_id(self):
        """Retorna siempre la moneda base de la compañía activa (no la del producto)."""
        currency = self.env.company.currency_id
        for template in self:
            template.company_currency_id = currency

    @api.depends('list_price')
    @api.depends_context('company')
    def _compute_company_sale_price(self):
        company = self.env.company
        pricelist = self._get_company_default_pricelist(company)
        for template in self:
            if pricelist:
                item = self._get_company_pricelist_item(pricelist, template)
                if item:
                    template.company_sale_price = item.fixed_price
                    template.company_sale_price_usd = item.fixed_price_usd
                else:
                    template.company_sale_price = template.list_price
                    # Fallback: derive USD from list_price using exchange rate
                    if company.currency_id.name == 'USD':
                        template.company_sale_price_usd = template.list_price
                    else:
                        tasa = self._get_exchange_rate()
                        if tasa and tasa > 0:
                            template.company_sale_price_usd = template.list_price / tasa
                        else:
                            template.company_sale_price_usd = template.list_price
            else:
                template.company_sale_price = template.list_price
                if company.currency_id.name == 'USD':
                    template.company_sale_price_usd = template.list_price
                else:
                    tasa = self._get_exchange_rate()
                    if tasa and tasa > 0:
                        template.company_sale_price_usd = template.list_price / tasa
                    else:
                        template.company_sale_price_usd = template.list_price

    def _inverse_company_sale_price(self):
        """When Bs price is set, update pricelist item and recalculate USD."""
        company = self.env.company
        pricelist = self._get_company_default_pricelist(company)
        if not pricelist:
            _logger.warning(
                "No default pricelist found for company %s (%s).",
                company.name, company.id
            )
            return
        tasa = self._get_exchange_rate()
        for template in self:
            vals = {'fixed_price': template.company_sale_price}
            # Recalculate USD from the new Bs price
            if company.currency_id.name == 'USD':
                vals['fixed_price_usd'] = template.company_sale_price
            else:
                if tasa and tasa > 0:
                    vals['fixed_price_usd'] = template.company_sale_price / tasa
            self._write_company_pricelist_item(pricelist, template, vals)

    def _inverse_company_sale_price_usd(self):
        """When USD price is set, update pricelist item and recalculate Bs."""
        company = self.env.company
        pricelist = self._get_company_default_pricelist(company)
        if not pricelist:
            _logger.warning(
                "No default pricelist found for company %s (%s).",
                company.name, company.id
            )
            return
        tasa = self._get_exchange_rate()
        for template in self:
            vals = {'fixed_price_usd': template.company_sale_price_usd}
            # Recalculate Bs from the new USD price
            if company.currency_id.name == 'USD':
                vals['fixed_price'] = template.company_sale_price_usd
            else:
                if tasa and tasa > 0:
                    vals['fixed_price'] = template.company_sale_price_usd * tasa
            self._write_company_pricelist_item(pricelist, template, vals)

    # ── view override ────────────────────────────────────────────────

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        self._apply_company_price_visibility(arch, view_type)
        return arch, view

    @api.model
    def _apply_company_price_visibility(self, arch, view_type):
        """Toggle visibility of USD fields based on company currency."""
        has_dual = self.env.company.currency_id.name != 'USD'
        if view_type in ('list', 'tree'):
            col_invisible = '0' if has_dual else '1'
            for node in arch.xpath("//field[@name='company_sale_price_usd' or @name='standard_price_usd']"):
                node.set('column_invisible', col_invisible)
        elif view_type == 'form':
            invisible = '0' if has_dual else '1'
            # Update labels and divs for company_sale_price_usd
            for node in arch.xpath("//label[@for='company_sale_price_usd'] | //div[@name='company_pricing_usd']"):
                node.set('invisible', invisible)
        return arch


    # ── helpers ──────────────────────────────────────────────


    @api.model
    def _get_company_default_pricelist(self, company):
        """Get the default pricelist for the company.
        
        Priority:
        1. The pricelist with is_default_company_price=True for this company
        2. The first pricelist with company_id = company
        3. Auto-create one if none exists
        """
        # 1. Pricelist marked as default for company pricing
        pricelist = self.env['product.pricelist'].sudo().search([
            ('is_default_company_price', '=', True),
            ('company_id', '=', company.id),
        ], limit=1)
        if pricelist:
            return pricelist

        # 2. Fallback: first pricelist for this company
        pricelist = self.env['product.pricelist'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)
        if pricelist:
            return pricelist

        # 3. Auto-create
        pricelist = self.env['product.pricelist'].sudo().create({
            'name': '%s - Lista de precios' % company.name,
            'company_id': company.id,
            'currency_id': company.currency_id.id,
            'is_default_company_price': True,
        })
        _logger.info(
            "Created default pricelist '%s' for company %s",
            pricelist.name, company.name
        )
        return pricelist

    def _get_company_pricelist_item(self, pricelist, template):
        """Search for the fixed-price pricelist item for this template."""
        return self.env['product.pricelist.item'].sudo().search([
            ('pricelist_id', '=', pricelist.id),
            ('product_tmpl_id', '=', template.id),
            ('applied_on', '=', '1_product'),
            ('compute_price', '=', 'fixed'),
        ], limit=1)

    def _write_company_pricelist_item(self, pricelist, template, vals):
        """Find or create the pricelist item and write vals to it."""
        item = self._get_company_pricelist_item(pricelist, template)
        if item:
            item.sudo().write(vals)
        else:
            create_vals = {
                'pricelist_id': pricelist.id,
                'product_tmpl_id': template.id,
                'applied_on': '1_product',
                'compute_price': 'fixed',
            }
            create_vals.update(vals)
            self.env['product.pricelist.item'].sudo().create(create_vals)

    @api.model
    def _get_exchange_rate(self):
        """Get the exchange rate (inverse_rate) from the secondary currency."""
        currency_dif = getattr(self.env.company, 'currency_id_dif', None)
        if currency_dif:
            return currency_dif.inverse_rate
        return 0

    @api.model
    def _cron_update_company_prices(self):
        """Recalculate Precio Base (Bs) from Precio Base USD for VE companies."""
        ve_companies = self.env['res.company'].sudo().search([]).filtered(
            lambda c: getattr(c, 'is_ve_company', False) and c.currency_id.name != 'USD'
        )
        for company in ve_companies:
            currency_dif = getattr(company, 'currency_id_dif', None)
            if not currency_dif or currency_dif.inverse_rate <= 0:
                _logger.warning(
                    "Skipping company %s: no valid exchange rate.",
                    company.name
                )
                continue
            tasa = currency_dif.inverse_rate
            pricelist = self.with_company(company)._get_company_default_pricelist(company)
            if not pricelist:
                continue
            items = self.env['product.pricelist.item'].sudo().search([
                ('pricelist_id', '=', pricelist.id),
                ('applied_on', '=', '1_product'),
                ('compute_price', '=', 'fixed'),
                ('fixed_price_usd', '>', 0),
            ])
            count = 0
            for item in items:
                new_bs_price = item.fixed_price_usd * tasa
                if item.fixed_price != new_bs_price:
                    item.write({'fixed_price': new_bs_price})
                    count += 1
            _logger.info(
                "Company %s: updated %d product prices from USD (rate: %s).",
                company.name, count, tasa
            )

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        self.env['product.template']._apply_company_price_visibility(arch, view_type)
        return arch, view
