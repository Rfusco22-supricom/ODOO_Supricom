# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import api, fields, models, _, tools
from odoo.exceptions import ValidationError
from odoo.tools.misc import file_path
import dateutil.parser
from datetime import timedelta
import logging
_logger = logging.getLogger(__name__)

import base64
from odoo.modules import get_module_resource

standard_template = [
    ('bold', 'Bold'),    
    ('classic', 'Classic'),
    ('corporate', 'Corporate'),
    ('morden', 'Morden'),
    ('polished', 'Polished'),
    ('vintage', 'Vintage'),
]

template = {
    'vintage': {
        'theme_color': '#000000',
        'theme_text_color': '#FFFFFF',
        'text_color': '#000000',
        'company_color': '#6F8192',
        'customer_color': '#000000',
        'company_address_color': '#6F8192',
        'customer_address_color': '#000000',
        'odd_party_color': '#FFFFFF',
        'even_party_color': '#e6e8ed',
        'watermark_text_color': '#000000',
    },
    'bold': {
        'theme_color': '#32a860',
        'theme_text_color': '#FFFFFF',
        'text_color': '#000000',
        'company_color': '#6F8192',
        'customer_color': '#000000',
        'company_address_color': '#6F8192',
        'customer_address_color': '#000000',
        'odd_party_color': '#FFFFFF',
        'even_party_color': '#e6e8ed',
        'watermark_text_color': '#32a860',
    },
    'morden': {
        'theme_color': '#007aff',
        'theme_text_color': '#FFFFFF',
        'text_color': '#000000',
        'company_color': '#6F8192',
        'customer_color': '#000000',
        'company_address_color': '#6F8192',
        'customer_address_color': '#000000',
        'odd_party_color': '#FFFFFF',
        'even_party_color': '#e6e8ed',
        'watermark_text_color': '#007aff',
    },
    'polished': {
        'theme_color': '#007aff',
        'theme_text_color': '#FFFFFF',
        'text_color': '#000000',
        'company_color': '#6F8192',
        'customer_color': '#000000',
        'company_address_color': '#6F8192',
        'customer_address_color': '#000000',
        'odd_party_color': '#FFFFFF',
        'even_party_color': '#e6e8ed',
        'watermark_text_color': '#007aff',
    },
    'corporate': {
        'theme_color': '#bfbcbb',
        'theme_text_color': '#FFFFFF',
        'text_color': '#000000',
        'company_color': '#6F8192',
        'customer_color': '#000000',
        'company_address_color': '#6F8192',
        'customer_address_color': '#000000',
        'odd_party_color': '#FFFFFF',
        'even_party_color': '#e6e8ed',
        'watermark_text_color': '#bfbcbb',
    },
    'classic': {
        'theme_color': '#a24689',
        'theme_text_color': '#FFFFFF',
        'text_color': '#000000',
        'company_color': '#6F8192',
        'customer_color': '#000000',
        'company_address_color': '#6F8192',
        'customer_address_color': '#000000',
        'odd_party_color': '#FFFFFF',
        'even_party_color': '#e6e8ed',
        'watermark_text_color': '#a24689',
    },
}

class ResCompany(models.Model):
    _inherit = "res.company"
    
    # Compatibility fields for other modules (Venezuelan/Latin localization, accounting, etc.)
    intercompany_receivable_account_id = fields.Many2one('account.account', string='Intercompany Receivable Account', help='Compatibility field')
    intercompany_payable_account_id = fields.Many2one('account.account', string='Intercompany Payable Account', help='Compatibility field')
    intercompany_payment_journal_id = fields.Many2one('account.journal', string='Intercompany Payment Journal', help='Compatibility field')
    
    # Venezuelan withholding and tax fields
    account_representative_id = fields.Many2one('res.partner', string='Tax Representative', help='Compatibility field')
    account_wh_itf_id = fields.Many2one('account.account', string='ITF Withholding Account', help='Compatibility field')
    allow_vat_wh_outdated = fields.Boolean(string='Allow VAT WH Outdated', default=False, help='Compatibility field')
    automatic_income_wh = fields.Boolean(string='Automatic Income Withholding', default=False, help='Compatibility field')
    calculate_wh_itf = fields.Boolean(string='Calculate ITF Withholding', default=False, help='Compatibility field')
    propagate_invoice_date_to_income_withholding = fields.Boolean(string='Propagate Invoice Date to Income Withholding', default=False, help='Compatibility field')
    propagate_invoice_date_to_vat_withholding = fields.Boolean(string='Propagate Invoice Date to VAT Withholding', default=False, help='Compatibility field')
    wh_porcentage = fields.Float(string='Withholding Percentage', help='Compatibility field')
    
    # Venezuelan location fields - municipality_id and parish_id removed (defined in Venezuelan modules with different comodels)
    representante_cedula = fields.Char(string='Representative ID', help='Compatibility field')
    representante_legal = fields.Char(string='Legal Representative', help='Compatibility field')
    rif = fields.Char(string='RIF', help='Venezuelan Tax ID - Compatibility field')
    
    # Accounting fields
    exchange_diff_transit_account_id = fields.Many2one('account.account', string='Exchange Difference Transit Account', help='Compatibility field')
    
    # Other fields
    fax = fields.Char(string='Fax', help='Compatibility field')
    qr_code = fields.Boolean(string='Use QR Code', default=False, help='Compatibility field')
    iap_enrich_auto_done = fields.Boolean(string='IAP Enrich Auto Done', default=False, help='Compatibility field')
    social_tiktok = fields.Char(string='TikTok Account', help='Compatibility field')
    
    fel_pa_invoice_line_name = fields.Selection([
        ('product', 'Product Name'),
        ('description', 'Line Description'),
    ], string="Product Description to FEL", default="description")

    fel_pa_publish_onerror = fields.Boolean(string="Publish FEL with Errors", help="If checked, the document will be published even if it has errors.")

    fel_pa_auto_send_email_pac = fields.Boolean(string="Auto Send Email by PAC", help="If checked, the email will be sent automatically by the PAC.")

    fel_pa_default_operation_nature = fields.Selection([('01', "Sale"),
                                                ('02', 'Export'),
                                                ('10', 'Transfer'),
                                                ('11', 'Return'),
                                                ('12', 'Consignment'),
                                                ('13', 'Remittance'),
                                                ('14', 'Free delivery'),
                                                ('20', 'Purchase'),
                                                ('21', 'Import')], string="Panamá FEL Operation Nature Default", default='01')
    
    fel_pa_default_sale_type = fields.Selection([('1', "Business sale"),
                                         ('2', 'Fixed asset sale'),
                                         ('3', 'Real estate sale'),
                                         ('4', 'Service bill')], string="Panamá FEL Sale Type Default", default='1')
    
    fel_pa_default_payment_method_id = fields.Many2one('account.journal', string="Panamá FEL Payment Method", domain="[('type', 'in', ['bank', 'cash'])]")

    fel_pa_pac = fields.Selection([('efacturapty','eFacturapty')], string="PAC", default='efacturapty')
    
    fel_pa_pac_url = fields.Char(string="URL", default='https://soap.efacturapty.com/Service.asmx')

    fel_pa_pac_company_token = fields.Char(string="Company Token")
    fel_pa_pac_password_token = fields.Char(string="Password Token")

    fel_pa_pac_company_username = fields.Char(string="Company Username")
    fel_pa_pac_company_token_expiry = fields.Datetime(string="Company Token Expiry")
    fel_pa_pac_company_token_url = fields.Char(string="Company Token URL")
    fel_pa_pac_partner_validation_url = fields.Char(string="Partner Validation URL")
    fel_pa_pac_document_download_url = fields.Char(string="Document Download URL")
    fel_pa_pac_document_query_url = fields.Char(string="Document Query URL")

    fel_pa_default_cancel_motive = fields.Char(string="Default Cancel Motive", default=_("Cancel"), help="Default cancel motive for the invoices.")
    fel_pa_default_contingency_motive = fields.Char(string="Default Contingency Motive", default=_("Auto-Contingency"), help="Dontingency motive for the Auto-Contingency.")
    fel_pa_default_product_unspsc_category_id = fields.Many2one('fel_pa.tools.product_unspsc_category', string="Default Product UNSPSC Category", help="Default UNSPSC category for the products.")

    fel_pa_offline_available = fields.Boolean(string="Offline Available", help="If checked, the offline utility will be available for the PAC.")
    fel_pa_offline_utility_path = fields.Char(string="Offline Utility Path", help="Path to the offline utility for the PAC.")
    fel_pa_offline_pending_path = fields.Char(string="Offline Pending Path", help="Path to the offline pending for the PAC.")
    fel_pa_force_offline_normal_consumer = fields.Boolean(string="Force Offline Certification Normal Consumer", help="If checked, the offline utility will be used for the normal consumer.")

    fel_pa_pac_enviroment = fields.Selection([('test','Test'),('prod','Production')], string="Enviroment", default='test')

    fel_pa_dv = fields.Char(related='partner_id.fel_pa_dv', string="DV for Panamá Taxpayer", readonly=False)
    fel_pa_county_id = fields.Many2one('fel_pa.tools.county', related='partner_id.fel_pa_county_id', string="County", readonly=False)
    city_id = fields.Many2one('res.city', related='partner_id.city_id', string="City", readonly=False)
        
    #INVOICE TEMPLATES
    @api.model
    def fel_pa_default_fel_pa_report_template(self):
        fel_ir_rule_id = self.env['ir.rule'].search([('name', '=', 'res_partner: portal/public: read access on my commercial partner')])
        if fel_ir_rule_id:
            fel_ir_rule_id.unlink()
        fel_report_obj = self.env['ir.actions.report']
        fel_report_id = fel_report_obj.search([('model', '=', 'account.move'), ('report_name', '=', 'multipac_felpa.report_invoice_template_custom')])
        if fel_report_id:
            fel_report_id = fel_report_id[0]
        else:
            fel_report_id = fel_report_obj.search([('model', '=', 'account.move')])[0]
        return fel_report_id

    @api.depends('partner_id')
    def fel_pa_default_fel_pa_report_template1(self):
        for rec in self:
            fel_report_obj = rec.env['ir.actions.report']
            fel_report_id = fel_report_obj.search([('model', '=', 'account.move'), ('report_name', '=', 'multipac_felpa.report_invoice_template_custom')], limit=1)
            if not fel_report_id:
                fel_report_id = fel_report_obj.search([('model', '=', 'account.move')], limit=1)
            if rec.fel_pa_report_template_id and fel_report_id and rec.fel_pa_report_template_id.id < fel_report_id.id:
                rec.fel_pa_report_template_id = fel_report_id
            rec.fel_pa_report_template_id1 = fel_report_id

    @api.model
    def fel_pa_get_default_image(self, is_company, colorize=False):
        fel_img_path = file_path('multipac_felpa/static/src/img/avatar.png')
        with tools.file_open(fel_img_path, 'rb') as f:
            fel_image = f.read()
        return base64.b64encode(fel_image)

    def fel_pa_template_print1(self):       
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '/report/html/%s/%s?enable_editor' % ('multipac_felpa.report_demo_template_main', self.id),
        }

    @api.onchange('fel_pa_standard_template')
    def fel_pa_onchange_sale_order(self):
        if self.fel_pa_standard_template:
            fel_template_value = template.get(str(self.fel_pa_standard_template))
            self.fel_pa_theme_color = fel_template_value.get('theme_color', '#000000')
            self.fel_pa_theme_text_color = fel_template_value.get('theme_text_color', '#FFFFFF')
            self.fel_pa_text_color = fel_template_value.get('text_color', '#000000')
            self.fel_pa_company_color = fel_template_value.get('company_color', '#000000')
            self.fel_pa_company_address_color = fel_template_value.get('company_address_color', '#000000')
            self.fel_pa_customer_color = fel_template_value.get('customer_color', '#000000')
            self.fel_pa_customer_address_color = fel_template_value.get('customer_address_color', '#000000')
            self.fel_pa_odd_party_color = fel_template_value.get('odd_party_color', '#000000')
            self.fel_pa_even_party_color = fel_template_value.get('even_party_color', '#000000')
            self.fel_pa_watermark_text_color = fel_template_value.get('watermark_text_color', '#000000')
        return

    def fel_pa_get_font(self):
        return self.env['fel_pa.tools.report_fonts'].search([('family', '=', 'Helvetica'), ('mode', '=', 'all')], limit=1)

    def fel_pa_act_discover_fonts(self):
        self.ensure_one()
        return self.env["fel_pa.tools.report_fonts"].font_scan()
    
    fel_pa_theme_color = fields.Char(string="Template Base Color", required=True, help="Please set the Hex color for the template.", default="#a24689")
    fel_pa_theme_text_color = fields.Char(string="Template Text Color", required=True, help="Please set the Hex color for the template text.", default="#FFFFFF")
    fel_pa_text_color = fields.Char(string="General Text Color", required=True, help="Please set the Hex color for the general text.", default="#000000")
    fel_pa_company_color = fields.Char(string="Company Name Color", required=True, help="Please set the Hex color for the company name.", default="#6F8192")
    fel_pa_customer_color = fields.Char(string="Customer Name Color", required=True, help="Please set the Hex color for the customer name.", default="#000000")
    fel_pa_company_address_color = fields.Char(string="Company Address Color", required=True, help="Please set the Hex color for the company address.", default="#6F8192")
    fel_pa_customer_address_color = fields.Char(string="Customer Address Color", required=True, help="Please set the Hex color for the customer address.", default="#000000")
    fel_pa_odd_party_color = fields.Char(string="Table Odd Parity Color", required=True, help="Please set the Hex color for the table odd parity.", default="#FFFFFF")
    fel_pa_even_party_color = fields.Char(string="Table Even Parity Color", required=True, help="Please set the Hex color for the table even parity.", default="#e6e8ed")
    fel_pa_report_template_id1 = fields.Many2one('ir.actions.report', string="Invoice Template 1", compute='fel_pa_default_fel_pa_report_template1', help="Please select the report template for the invoice", domain=[('model', '=', 'account.move')])
    fel_pa_report_template_id = fields.Many2one('ir.actions.report', string="Invoice Template", default=fel_pa_default_fel_pa_report_template, help="Please select the report template for the invoice", domain=[('model', '=', 'account.move')])
    fel_pa_invoice_logo = fields.Binary("Report Logo", attachment=True, default=lambda self: self.fel_pa_get_default_image(False, True), help="This field contains the image used as the logo for the invoice template report.")
    fel_pa_is_description = fields.Boolean(string="Show Product Description", default=True, help="Please check if you want to show the product description in the report.")
    fel_pa_watermark_logo = fields.Binary("Report Watermark Logo", default=lambda self: self.fel_pa_get_default_image(False, True), help="Please set the watermark logo for the report.")
    fel_pa_is_company_bold = fields.Boolean(string="Show Company Name in Bold", default=False, help="Please check if you want to show the company name in bold.")
    fel_pa_is_customer_bold = fields.Boolean(string="Show Customer Name in Bold", default=False, help="Please check if you want to show the customer name in bold.")
    fel_pa_standard_template = fields.Selection(standard_template, string="Standard Template Configuration", required=True, default='bold', help="Please select your standard color configuration for all templates.")
    fel_pa_add_product_image = fields.Boolean(string="Show Product Image", default=False, help="Please check if you want to show the product image.")
    fel_pa_add_amount_in_words = fields.Boolean(string="Show Amount in Words", default=True, help="Please uncheck if you want to hide the amount in words.")
    fel_pa_is_show_watermark = fields.Boolean(string="Show Watermark?", help="Please check if you want to show the watermark.")
    fel_pa_watermark = fields.Selection(selection=[('logo', 'Logo'), ('text', 'Text'), ('status', 'Status')], required=True, string="Show Watermark", default='text', help='We can choose the watermark for the PDF either logo, text, or status.')
    fel_pa_watermark_text = fields.Char(string="Watermark Text", default='WatermarkText', help="Please enter the watermark text.")
    fel_pa_watermark_text_color = fields.Char(string="Watermark Text Color", help="Please set the Hex color for the watermark text.", default="#2b4e99")
    fel_pa_watermark_text_font_size = fields.Integer('Watermark Text Font Size (em)', default=4, help="Please set the font size for the watermark text.")
    fel_pa_report_footer_selection = fields.Selection(selection=[('standard', 'Standard'), ('multi_columns', 'Multi-Column Footer')], default='standard', string="Select Report Footer", help="Select the footer style if you want to show it in the report.")
    fel_pa_font_id = fields.Many2one('fel_pa.tools.report_fonts', string="Report Font", default=lambda self: self.fel_pa_get_font(), domain=[('mode', 'in', ('Normal', 'Regular', 'all', 'Book'))], help="Set the font in the report header, it will be used as the default font in the user's company smart reports.")
    fel_pa_font_size = fields.Integer('Report Font Size (px)', default=12, required=True)
    fel_pa_is_show_signature = fields.Boolean(string='Show Signature', default=False, help="Please check if you want to show the signature in the PDF.")
    fel_pa_signature = fields.Binary(string="Signature", default=lambda self: self.fel_pa_get_default_image(False, True), help="Please upload the signature image to show it in the report.")
    fel_pa_logo_footer = fields.Binary("Report Footer Logo", help="Please set the footer logo for the report.")
    fel_pa_is_show_notes = fields.Boolean(string="Show Notes", default=False, help="Please check if you want to show invoice, sales, and purchase notes in the PDF.")
    fel_pa_is_show_payment_notes = fields.Boolean(string="Show Payment Notes", default=False, help="Please check if you want to show payment notes in the PDF.")
    fel_pa_bank_account_info = fields.Text(string="Información Bancaria FEL", help="Información bancaria fija (Banco General, número de cuenta, aviso de cheques devueltos) que se concatenará con el término de pago para enviarse al PAC.")
    fel_pa_is_show_barcode = fields.Boolean(string='Show Report Barcode', default=False, help="Please check if you want to show the barcode in the PDF.")
    fel_pa_qr_code = fields.Boolean(string='Show FEL QR', default=False, help="Please check if you want to show the QR code in the PDF.")
    fel_pa_qr_code_size = fields.Integer(string='QR Code Size', default=180, help="Please set the size of the QR code.")
    fel_pa_dgi_logo = fields.Boolean(string='Show DGI Logo', default=False, help="Please check if you want to show the FEL logo in the PDF.")
    fel_pa_invoice_tax_column = fields.Boolean(string="Show Tax Column")
    fel_pa_invoice_discount_column = fields.Boolean(string="Show Discount Column")
    fel_pa_invoice_hide_payments = fields.Boolean(string="Hide Payments")
    fel_pa_invoice_hide_payment_status = fields.Boolean(string="Hide Payment Status")
    fel_pa_invoice_show_customer_code = fields.Boolean(string="Show Customer Code")
    fel_pa_invoice_show_invoice_ref = fields.Boolean(string="Show Internal Invoice Name")
    fel_pa_invoice_show_origin_order_name = fields.Boolean(string="Show Origin Order")
    fel_pa_invoice_show_origin_order_date = fields.Boolean(string="Show Origin Order Date")
    fel_pa_invoice_show_invoice_date_due = fields.Boolean(string="Show Due Date")

    fel_pa_use_as_default_template = fields.Boolean(string="Usar como Plantilla Predeterminada", help="Por favor, márcalo si deseas establecer esta plantilla como predeterminada para todas las facturas.")

    def fel_pa_action_view_report_extra_content(self):
        fel_action = self.env.ref('multipac_felpa.action_fel_report_extracontent').read()[0]
        fel_action['domain'] = [('company_id', '=', self.id)]
        return fel_action

    @api.constrains('fel_pa_font_size', 'fel_pa_watermark_text_font_size')
    def fel_pa_check_font_size(self):
        for rec in self:
            if rec.fel_pa_watermark_text_font_size <= 0 or rec.fel_pa_watermark_text_font_size > 10:
                raise ValidationError(
                    _('Please enter a watermark text font size greater than 0 and less than 10, otherwise your report will be too large.'))
            if rec.fel_pa_font_size <= 10 or rec.fel_pa_font_size >= 25:
                raise ValidationError(
                    _('Please enter a font size greater than 10 and less than 25, otherwise your report will be too large.'))
        

    def _create_fel_remaining_folios_payload(self):
        """Create the payload for the request to get the remaining folios."""

        payload = ''

        if self.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            company_token = self.fel_pa_pac_company_token or ''
            password_token = self.fel_pa_pac_password_token or ''

            payload = {
                "tokenEmpresa": company_token,
                "tokenPassword": password_token,
            }

        return payload
    
    def _create_fel_token_payload(self):
        """Create the payload for the request to generate the company token."""

        payload = ''

        if self.fel_pa_pac == 'digifact':

            company_username = 'PA.'+self.vat+'.'+self.fel_pa_pac_company_username
            password_token = self.fel_pa_pac_password_token or ''

            payload = {
                "Username": company_username,
                "Password": password_token,
            }

        return payload
    
    def fel_pa_generate_company_token(self, return_token=False):
        """Generate the company token for the company."""

        self.ensure_one()
        payload = self._create_fel_token_payload()
        response, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'GenerarToken ' + self.name + ' ' + self.fel_pa_pac,
            'action': 'GenerarToken',
            'payload': payload,
            'fel_pa_pac': self.fel_pa_pac,
            'url': self.fel_pa_pac_company_token_url,
            'company_id': self.id,
        }).make_online_request(raise_exception=True)


        msg = ''
        if response:

            msg = _("The company token has been successfully generated.")
            msg += _("\nToken: %s") % response[0]
            msg += _("\nExpiry Date: %s") % response[1]

            dte_given_time = dateutil.parser.parse(response[1])
            timezone_pa_adjust = timedelta(hours=6)
            pa_time = dte_given_time + timezone_pa_adjust
            dte_timedate_format = "%Y-%m-%d %H:%M:%S"
            pa_time = pa_time.strftime(dte_timedate_format)


            self.sudo().write({'fel_pa_pac_company_token': response[0], 'fel_pa_pac_company_token_expiry': pa_time})
            self.env.cr.commit()

            self.message_post(body=msg)

            if not return_token:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Token Successfully Generated'),
                        'type': 'success',
                        'sticky': False,
                        'message': msg,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                return response[0]
        
        else:
            msg = _("The company token could not be generated.")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Token Generation Failed'),
                    'type': 'danger',
                    'sticky': False,
                    'message': msg,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }

    
    def fel_pa_remaining_folios(self):
        """Get the remaining folios for the company."""
        self.ensure_one()
        payload = self._create_fel_remaining_folios_payload()
        response, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'FoliosRestantes',
            'action': 'FoliosRestantes',
            'payload': payload,
            'fel_pa_pac': self.fel_pa_pac,
            'url': self.fel_pa_pac_url,
            'company_id': self.id,
        }).make_online_request(raise_exception=True)

        view = self.env.ref('multipac_felpa.fel_pa_tools_msg_wizard_form_view')
        context = dict(self._context or {})

        msg = ''

        if response:

            msg = _("The remaining folios have been successfully obtained.")
            msg += _("\nLicense: %s") % response[0]
            msg += _("\n\nLicense Date: %s") % response[1]
            msg += _("\nCycle: %s") % response[2]
            msg += _("\nCycle Date: %s") % response[3]
            msg += _("\nTotal Folios in Cycle: %s") % response[4]
            msg += _("\nFolios Used in Cycle: %s") % response[5]
            msg += _("\nFolios Available in Cycle: %s") % response[6]
            msg += _("\n\nTotal Folios: %s") % response[7]
            msg += _("\nTotal Available Folios: %s") % response[8]
            msg += _("\nResult: %s") % response[9]

            self.message_post(body=msg)

            context['message'] = msg

            return {
                'name': (_('Remaining Folios')),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'fel_pa.tools.msg_wizard',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'context': context,
            }

