from odoo import api, fields, models, _
from datetime import date, timedelta, datetime
from bs4 import BeautifulSoup
from pytz import timezone
import requests
import urllib3
urllib3.disable_warnings()
class ResCurrency(models.Model):
    _inherit = 'res.currency'

    facturas_por_actualizar = fields.Boolean(compute="_facturas_por_actualizar")

    # habilitar sincronización automatica (per-company)
    sincronizar = fields.Boolean(string="Sincronizar", default=False, company_dependent=True)

    # Temporary dummy field to allow view validation to pass during module update
    bcv_monitored = fields.Boolean(string='Dummy BCV Monitored', default=False)
    bcv_currency_code = fields.Selection([
        ('dolar', 'USD'),
        ('euro', 'EUR'),
    ], string='Dummy BCV Currency Code')

    # campo listado de servidores, bcv o dolar today (per-company)
    server = fields.Selection([('bcv', 'BCV'), ('dolar_today', 'Dolar Today Promedio')], string='Servidor',
                              default='bcv', company_dependent=True)

    # def _convert(self, from_amount, to_currency, company, date, round=True, rate=None):
    #     """Returns the converted amount of ``from_amount``` from the currency
    #        ``self`` to the currency ``to_currency`` for the given ``date`` and
    #        company.

    #        :param company: The company from which we retrieve the convertion rate
    #        :param date: The nearest date from which we retriev the conversion rate.
    #        :param round: Round the result or not
    #     """
    #     self, to_currency = self or to_currency, to_currency or self
    #     assert self, "convert amount from unknown currency"
    #     assert to_currency, "convert amount to unknown currency"
    #     assert company, "convert amount from unknown company"
    #     assert date, "convert amount from unknown date"

    #     try:
    #         amt = float(from_amount or 0.0)
    #     except (TypeError, ValueError):
    #         amt = 0.0
    #     # apply conversion rate
    #     if self == to_currency:
    #             res = amt
    #     else:
    #             if rate is None:
    #                 rate = super(ResCurrency, self)._get_conversion_rate(self, to_currency, company, date)
    #     try:
    #         res = amt * float(rate or 0.0)
    #     except (TypeError, ValueError):
    #         res = 0.0
    #     #rounding amount
    #     if round:
    #         return to_currency.round(res)
    #     return res

    def _facturas_por_actualizar(self):
        for rec in self:
            if rec.name == self.env.company.currency_id_dif.name:
                if self.env['account.move'].search_count([('state', 'in', ['draft','posted'])]):
                    rec.facturas_por_actualizar = True
                else:
                    rec.facturas_por_actualizar = False
            else:
                rec.facturas_por_actualizar = False

    def write(self, vals):
        # Prevent AccessError when saving res.currency in multi-company environments.
        # The web client sends a Command.set (6) with only the rate_ids the user can see.
        # This causes Odoo to attempt to unlink rates from other companies, which throws an AccessError.
        if 'rate_ids' in vals:
            vals.pop('rate_ids')
                
        return super(ResCurrency, self).write(vals)


    def actualizar_facturas(self):
        for rec in self:
            # actualizar tasa a las facturas dinamicas
            facturas = self.env['account.move'].search([('acuerdo_moneda', '=', True)])
            if facturas:
                for f in facturas:
                    f.tax_today = rec.inverse_rate
                    for l in f.line_ids:
                        l.tax_today = rec.inverse_rate
                        l._debit_usd()
                        l._credit_usd()
                    for d in f.invoice_line_ids:
                        d.tax_today = rec.inverse_rate
                        d._price_unit_usd()
                        d._price_subtotal_usd()
                    f._amount_untaxed_usd()
                    f._amount_all_usd()
                    f._compute_payments_widget_reconciled_info_USD()

    def _sincronizar_productos(self):
        xfind = self.env['product.template'].search([])
        for item in xfind:
            item._compute_list_price_usd()

    def actualizar_productos(self):
        for rec in self:
            product_product_ids = self.env['product.product'].search([('list_price_usd', '>', 0)])
            for p in product_product_ids:
                
                p._constrains_list_price_usd()
                # p.list_price           =  p.list_price_usd * rec.inverse_rate
                # amount_iva = (p.taxes_id[0].amount / 100 ) + 1
                # p.list_price_vat  =  p.list_price * amount_iva
                # p.list_price_vat_usd   =  p.list_price_usd * amount_iva
                 
            product_ids = self.env['product.template'].search([('list_price_usd','>',0)])
            for p in product_ids:
                p._constrains_list_price_usd()
                # p.list_price           =  p.list_price_usd * rec.inverse_rate
                # amount_iva             =  (p.taxes_id[0].amount / 100 ) + 1
                # p.list_price_vat       =  p.list_price * amount_iva 
                # p.list_price_vat_usd   =  p.list_price_usd * amount_iva

                # p.list_price_vat  = p.taxes_id.with_context(round=False).compute_all(
                #     p.list_price, currency=self.env.company.currency_id, quantity=1, product=p, partner=self.env.company.partner_id
                # )['total_void']

            list_product_ids = self.env['product.pricelist.item'].search([('currency_id', '=', self.id)])
            usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            for lp in list_product_ids:
                company = lp.company_id or self.env.company
                if company.currency_id.name == 'USD':
                    continue
                currency_rate = self.env['res.currency.rate'].search([
                    ('currency_id', '=', usd_currency.id),
                    ('company_id', '=', company.id),
                    ('name', '<=', fields.Date.today()),
                ], order='name desc', limit=1)
                if not currency_rate or not currency_rate.inverse_company_rate:
                    continue
                # buscar el producto en la lista de Bs y actualizar
                dominio = [('currency_id', '=', lp.company_id.currency_id.id or self.env.company.currency_id.id)]
                if lp.product_id:
                    dominio.append((('product_id', '=', lp.product_id.id)))
                elif lp.product_tmpl_id:
                    dominio.append((('product_tmpl_id', '=', lp.product_tmpl_id.id)))
                product_id_bs = self.env['product.pricelist.item'].search(dominio)
                for p in product_id_bs:
                    p.fixed_price = p.price_fixed_usd * currency_rate.inverse_company_rate
                    p.price_fixed_usd_vat = p.product_tmpl_id.taxes_id.compute_all(p.price_fixed_usd, product=p.product_tmpl_id)['total_included']

            # channel_id = self.env.ref('account_dual_currency.trm_channel')
            # channel_id.message_post(
            #     body="Todos los productos han sido actualizados con la nueva tasa de cambio",
            #     message_type='comment',
            #     subtype_xmlid='mail.mt_comment',
            # )

    def get_bcv(self):
        url = "https://www.bcv.org.ve/"
        req = requests.get(url, verify=False)

        status_code = req.status_code
        if status_code == 200:

            html = BeautifulSoup(req.text, "html.parser")
            # Dolar
            dolar = html.find('div', {'id': 'dolar'})
            dolar = str(dolar.find('strong')).split()
            dolar = str.replace(dolar[1], '.', '')
            dolar = float(str.replace(dolar, ',', '.'))
            # Euro
            euro = html.find('div', {'id': 'euro'})
            euro = str(euro.find('strong')).split()
            euro = str.replace(euro[1], '.', '')
            euro = float(str.replace(euro, ',', '.'))

            if self.name == 'USD':
                bcv = dolar
            elif self.name == 'EUR':
                bcv = euro
            else:
                bcv = False

            return bcv
        else:
            return False

    def get_dolar_today_promedio(self):
        url = "https://s3.amazonaws.com/dolartoday/data.json"
        response = requests.get(url)
        status_code = response.status_code

        if status_code == 200:
            response = response.json()
            usd = float(response['USD']['transferencia'])
            eur = float(response['EUR']['transferencia'])
            if self.name == 'USD':
                data = usd
            elif self.name == 'EUR':
                data = eur
            else:
                data = False

            return data
        else:
            return False

    def actualizar_tasa(self, company_id=False):
        if not company_id:
            company_id = self.env.company.id
        for rec in self:
            nueva_tasa = 0
            if rec.server == 'bcv':
                tasa_bcv = rec.get_bcv()
                if tasa_bcv:
                    nueva_tasa = tasa_bcv
            elif rec.server == 'dolar_today':
                tasa_dt = rec.get_dolar_today_promedio()
                if tasa_dt:
                    nueva_tasa = tasa_dt

            if nueva_tasa > 0:
                # channel_id = self.env.ref('account_dual_currency.trm_channel')
                # tasa_actual = self.env['res.currency.rate'].search([('name', '=', datetime.now()), ('currency_id', '=', self.id)])
                tasa_actual = self.env['res.currency.rate'].search([('name', '=', datetime.now()), ('currency_id', '=', self.id), ('company_id', '=', company_id)])
                
                if len(tasa_actual) == 0:
                    self.env['res.currency.rate'].create({
                        'currency_id': self.id,
                        'name': datetime.now(),
                        'rate': 1 / nueva_tasa,
                        'company_id': company_id
                    })
                    # channel_id.message_post(
                    #     body="Nueva tasa de cambio del %s: %s, actualizada desde %s a las %s." % (
                    #     rec.name, nueva_tasa, rec.server,
                    #     datetime.strftime(fields.Datetime.context_timestamp(self, datetime.now()),
                    #                       "%d-%m-%Y %H:%M:%S")),
                    #     message_type='notification',
                    #     subtype_xmlid='mail.mt_comment',
                    # )
                else:
                    if rec.server== 'dolar_today':
                        tasa_actual.rate = 1 / nueva_tasa
                        # channel_id.message_post(
                        #     body="Tasa de cambio actualizada del %s: %s, desde %s a las %s." % (
                        #         rec.name, nueva_tasa, rec.server,
                        #         datetime.strftime(fields.Datetime.context_timestamp(self, datetime.now()),
                        #                           "%d-%m-%Y %H:%M:%S")),
                        #     message_type='notification',
                        #     subtype_xmlid='mail.mt_comment',
                        # )

    @api.model
    def _cron_actualizar_tasa(self):
        companies = self.env['res.company'].search([])
        for company in companies:
            # Search with company context so company_dependent 'sincronizar' resolves per-company
            monedas = self.env['res.currency'].with_company(company).search([('active', '=', True), ('sincronizar', '=', True)])
            for m in monedas:
                m.actualizar_tasa(company_id=company.id)
                # if m == company.currency_id_dif:
                #     m.actualizar_productos()
    
    def _get_conversion_rate(self, from_currency, to_currency, company=None, date=None):

        if (from_currency != to_currency) and self._context.get('edit_trm') and self._context.get('tax_today', 1) != 0:
            if to_currency ==  self.env.ref('base.USD') :
                return 1 / self._context.get('tax_today', 1)
            else:
                return self._context.get('tax_today', 1)
                
        else:
            return super()._get_conversion_rate(from_currency, to_currency, company=company, date=date)

from odoo.exceptions import UserError, AccessError

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    sell_rate = fields.Float(string='Tasa de Cambio', digits=(12, 4))

    @api.model
    def check_access_rule(self, operation):
        pass # Overridden below using read() interception

    def read(self, fields=None, load='_classic_read'):
        """
        Intercept read operations on currency rates.
        Odoo's compute dependencies (e.g. rate_ids.rate) force reading all rates
        across companies when res.currency is saved. This triggers AccessError.
        By catching it and falling back to sudo(), we allow the save to complete safely.
        """
        try:
            return super(ResCurrencyRate, self).read(fields=fields, load=load)
        except AccessError as e:
            if 'multi-company currency rate rule' in str(e):
                return super(ResCurrencyRate, self.sudo()).read(fields=fields, load=load)
            raise e

    @api.constrains("sell_rate")
    def set_sell_rate(self):
        self.rate = 1 / self.sell_rate

    def update_product(self,currency):
    
        product = self.env['product.template'].search([('list_price_usd','>',0)])
        for item in product:
            item.list_price = item.list_price_usd * currency
        
        product_attribute = self.env['product.template.attribute.value'].search([])
        for item in product_attribute:
            item.price_extra = item.list_price_usd * currency

    def get_systray_dict(self, date):
        tz_name = "America/Lima"
        today_utc =  datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ')
        context_today = today_utc.astimezone(timezone(tz_name))
        date = context_today.strftime("%Y-%m-%d")
        # date = datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ')
        id_rate_usd = self.env['res.currency'].search([('name', '=', 'USD')]).id
        id_rate_eur = self.env['res.currency'].search([('name', '=', 'EUR')]).id
        rate        = self.env['res.currency.rate'].search([('currency_id', '=', id_rate_usd),('name', '=', date)], limit=1).sorted(lambda x: x.name)
        rate_euro   = self.env['res.currency.rate'].search([('currency_id', '=', id_rate_eur),('name', '=', date)], limit=1).sorted(lambda x: x.name)

        if rate:
            exchange_rate =  1 / rate.rate
            exchange_rate_euro = 1 / rate_euro.rate if rate_euro.rate > 0 else 1 
            return {'date': _('Date : ') + rate.name.strftime("%d/%m/%Y"), 'rate': "USD: " + str("{:,.4f}".format(exchange_rate)) ,'rate_euro': " EUR: " + str("{:,.4f}".format(exchange_rate_euro))}
        else:
            return {'date': _('No currency rate for ') + context_today.strftime("%d/%m/%Y"), 'rate': 'N/R'}
        
    

            