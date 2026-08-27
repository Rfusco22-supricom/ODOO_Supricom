# -*- coding: utf-8 -*-
import requests
import logging
from odoo import models, api, tools, fields, _
from odoo.exceptions import UserError
import datetime
import re

_logger = logging.getLogger(__name__)

class BcvScraper(models.AbstractModel):
    _name = 'l10n_ve.bcv.scraper'
    _description = 'BCV Scraper Utility'

    def _get_bcv_url(self):
        return 'https://www.bcv.org.ve/'

    def _fetch_bcv_rates(self):
        """
        Fetches the content of BCV website and parses the rates for USD and EUR.
        Returns a dict: {'dolar': float, 'euro': float}
        """
        url = self._get_bcv_url()
        try:
            # Verify False because BCV cert sometimes has issues or we are in a dev environment
            # Ideally should be True with proper CA certs.
            response = requests.get(url, timeout=30, verify=False) 
            response.raise_for_status()
        except Exception as e:
            _logger.error("Failed to connect to BCV: %s", e)
            return {}

        content = response.text
        rates = {}

        # Regex patterns to find rates in the HTML structure of BCV
        # Usually they are like <div id="dolar"> ... <strong> 36,4567 </strong> ... </div>
        # But BCV structure is messy.
        # Structure seen historically:
        # <div id="dolar">
        #   <div class="field-content">
        #     <div class="col-sm-6 col-xs-6 centrado">
        #       <strong> 36,3185 </strong>
        #     </div>
        #   </div>
        # </div>
        
        # We'll use a regex that looks for id="dolar" ... <strong> value </strong>
        # Note: BCV uses comma as decimal separator.

        for code in ['dolar', 'euro']:
             # Regex to find the div id and capture the float inside a <strong> tag.
             # Use DOTALL to match newlines and allow optional attributes on the <strong> tag.
            pattern = r'id=["\']%s["\'].*?<strong[^>]*>\s*([\d.,]+)\s*</strong>' % code
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '.')
                try:
                    rates[code] = float(value_str)
                except ValueError:
                    _logger.warning("Could not parse BCV rate for %s: %s", code, value_str)
            else:
                _logger.warning("Could not find BCV rate for %s in page content.", code)
        
        return rates

    @api.model
    def update_rates(self):
        """
        Cron method to update rates.
        Iterates through companies and applies the BCV rate to the currencies configured in each company's settings.
        """
        _logger.info("Starting BCV Rate Update...")
        companies = self.env['res.company'].search([])
        
        # Check if at least one company has a BCV currency configured
        configured = any(c.bcv_usd_currency_id or c.bcv_eur_currency_id for c in companies)
        if not configured:
            _logger.info("No companies configured to monitor BCV.")
            return

        scraped_data = self._fetch_bcv_rates()
        if not scraped_data:
            _logger.error("No rates scraped from BCV. Aborting update.")
            return

        today = fields.Date.today()

        for company in companies:
            currencies_to_update = []
            if company.bcv_usd_currency_id:
                currencies_to_update.append((company.bcv_usd_currency_id, 'dolar'))
            if company.bcv_eur_currency_id:
                currencies_to_update.append((company.bcv_eur_currency_id, 'euro'))

            if not currencies_to_update:
                continue

            _logger.info("Updating rates for company: %s", company.name)
            for currency, bcv_code in currencies_to_update:
                if bcv_code in scraped_data:
                    rate_value = scraped_data[bcv_code] # This is the Inverse Rate (Bs per USD/EUR)
                    
                    # Check if rate already exists for today and this company
                    existing_rate = self.env['res.currency.rate'].search([
                        ('currency_id', '=', currency.id),
                        ('name', '=', today),
                        ('company_id', '=', company.id)
                    ], limit=1)
                    
                    if existing_rate:
                        if abs(existing_rate.inverse_rate - rate_value) > 0.0001:
                           _logger.info("Updating existing rate for %s in %s: %s", currency.name, company.name, rate_value)
                           existing_rate.inverse_rate = rate_value
                    else:
                        _logger.info("Creating new rate for %s in %s: %s", currency.name, company.name, rate_value)
                        self.env['res.currency.rate'].create({
                            'currency_id': currency.id,
                            'name': today,
                            'company_id': company.id,
                            'inverse_rate': rate_value,
                        })
                else:
                    _logger.warning("No scraped data found for %s (Code: %s)", currency.name, bcv_code)
                
        _logger.info("BCV Rate Update Completed.")
