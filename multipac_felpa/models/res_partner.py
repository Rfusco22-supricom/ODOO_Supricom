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

from odoo import api, models, fields, _
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = "res.partner"

    is_panama_company = fields.Boolean(
        string='Is Panama Company',
        compute='_compute_is_panama_company',
        store=False,
    )

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_is_panama_company(self):
        is_pa = self.env.company.country_id.code == 'PA'
        for rec in self:
            rec.is_panama_company = is_pa

    # Compatibility fields for other modules
    # Venezuelan localization fields
    additional_info = fields.Char(string='Additional Info', help='Compatibility field')
    contribuyente_seniat = fields.Char(string='Contribuyente Seniat', help='Compatibility field')
    identification_id = fields.Char(string='Identification ID', help='Compatibility field')
    islr_exempt = fields.Boolean(string='ISLR Exempt', default=False, help='Compatibility field')
    islr_withholding_agent = fields.Boolean(string='ISLR Withholding Agent', default=False, help='Compatibility field')
    nationality = fields.Selection([('V', 'Venezuelan'), ('E', 'Foreign')], string='Nationality', help='Compatibility field')
    people_type_company = fields.Selection([('pjdo', 'Juridical Domiciled'), ('pjnd', 'Juridical Not Domiciled')], string='People Type Company', help='Compatibility field')
    people_type_individual = fields.Selection([('pndo', 'Natural Domiciled'), ('pnnd', 'Natural Not Domiciled'), ('pnre', 'Natural Resident')], string='People Type Individual', help='Compatibility field')
    rif = fields.Char(string='RIF', help='Compatibility field')
    spn = fields.Boolean(string='SPN', default=False, help='Compatibility field')
    vat_subjected = fields.Boolean(string='VAT Subjected', default=False, help='Compatibility field')
    wh_iva_agent = fields.Boolean(string='IVA Withholding Agent', default=False, help='Compatibility field')
    wh_iva_rate = fields.Float(string='IVA Withholding Rate', help='Compatibility field')
    
    # Address fields
    street_name = fields.Char(string='Street Name', help='Compatibility field')
    street_number = fields.Char(string='Street Number', help='Compatibility field')
    street_number2 = fields.Char(string='Street Number 2', help='Compatibility field')
    
    # Business fields
    company_name = fields.Char(string='Company Name', help='Compatibility field')
    complete_name = fields.Char(string='Complete Name', help='Compatibility field')
    legacy_is_vendor = fields.Boolean(string='Is Vendor', default=False, store=False, help='Compatibility field')
    legacy_vendor_type_id = fields.Integer(string='Vendor Type ID', store=False, help='Compatibility field - stores vendor type ID from previous implementation')
    partner_gid = fields.Integer(string='Partner GID', help='Compatibility field')
    partner_latitude = fields.Float(string='Latitude', help='Compatibility field')
    partner_longitude = fields.Float(string='Longitude', help='Compatibility field')
    
    # Warning fields
    followup_reminder_type = fields.Char(string='Followup Reminder Type', help='Compatibility field')
    invoice_warn = fields.Selection([
        ('no-message', 'No Message'),
        ('warning', 'Warning'),
        ('block', 'Block')
    ], string='Invoice Warning', help='Compatibility field')
    picking_warn = fields.Selection([
        ('no-message', 'No Message'),
        ('warning', 'Warning'),
        ('block', 'Block')
    ], string='Picking Warning', help='Compatibility field')
    purchase_warn = fields.Selection([
        ('no-message', 'No Message'),
        ('warning', 'Warning'),
        ('block', 'Block')
    ], string='Purchase Warning', help='Compatibility field')
    sale_warn = fields.Selection([
        ('no-message', 'No Message'),
        ('warning', 'Warning'),
        ('block', 'Block')
    ], string='Sale Warning', help='Compatibility field')
    
    # EDI/E-commerce fields
    is_published = fields.Boolean(string='Is Published', default=False, help='Compatibility field')
    peppol_eas = fields.Char(string='Peppol EAS', help='Compatibility field')
    peppol_endpoint = fields.Char(string='Peppol Endpoint', help='Compatibility field')
    phone_sanitized = fields.Char(string='Phone Sanitized', help='Compatibility field')
    # ubl_cii_format = fields.Char(string='UBL/CII Format', help='Compatibility field')
    vies_valid = fields.Boolean(string='VIES Valid', default=False, help='Compatibility field')

    fel_pa_recipient_type = fields.Selection([('01', "Taxpayer"), ('02', "Normal Consumer"), ('03', "Government"), ('04', "Foreign")], string="Receipentent Type", default='01')

    fel_pa_taxpayer_type = fields.Selection([('1', "Person"), ('2', "Business")], string="Taxpayer Type", default='1')

    fel_pa_dv = fields.Char(string="DV", help="DV for Panamá Taxpayer")

    fel_pa_company_name = fields.Char(string="Company Name FE", help="Company Name for Panamá Taxpayer")
    fel_pa_affiliated_fe = fields.Char(string="Affiliated FE", help="Affiliated FE for Panamá Taxpayer")

    fel_pa_ignore_verificartion = fields.Boolean('Ignore PAC Verification')

    fel_pa_county_id = fields.Many2one('fel_pa.tools.county', string="County")

    fel_pa_fe_active = fields.Boolean('Panamá FE Active', default=True)

    @api.onchange('fel_pa_county_id')
    def _onchange_fel_pa_county_id(self):
        if self.fel_pa_county_id:
            self.city_id = self.fel_pa_county_id.city_id
        else:
            self.city_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Skip Panama-specific RUC validation if company is not Panama
            if self.env.company.country_id.code != 'PA':
                continue
            if 'fel_pa_ignore_verificartion' in vals:
                if vals['fel_pa_ignore_verificartion']:
                    return super(ResPartner, self).create(vals)
            if 'parent_id' in vals:
                if vals['parent_id']:
                    return super(ResPartner, self).create(vals)
                
            if self.env.user.has_group('multipac_felpa.felpa_ruc_group_user') and 'fel_pa_recipient_type' in vals and 'l10n_latam_identification_type_id' in vals and 'fel_pa_taxpayer_type' in vals:
                if vals['fel_pa_recipient_type'] in ['01','03'] and vals['l10n_latam_identification_type_id'] in [self.env.ref('l10n_latam_base.it_vat').id, self.env.ref('multipac_felpa.it_gob').id]:
                    fel_pa_taxpayer_type = vals['fel_pa_taxpayer_type']
                    vat = False
                    if 'vat' in vals and vals['vat']:
                        vat = str(vals['vat']).strip().upper()
                    if not vat:
                        continue
                    validation_res = self.ruc_validation(vat, fel_pa_taxpayer_type)
                    if validation_res:
                        ruc, fel_pa_company_name, fel_pa_dv, fel_pa_affiliated_fe, fel_pa_taxpayer_type = validation_res
                        vals['fel_pa_company_name'] = fel_pa_company_name
                        vals['fel_pa_dv'] = fel_pa_dv
                        vals['fel_pa_affiliated_fe'] = fel_pa_affiliated_fe
                        vals['fel_pa_taxpayer_type'] = fel_pa_taxpayer_type
                        vals['vat'] = ruc
        return super(ResPartner, self).create(vals_list)
    
    def validate_ruc(self):
        action = self.env.ref('multipac_felpa.action_ruc_validator_wizard').read()[0]
        action['context'] = {
            'vat': self.vat,
            'fel_pa_recipient_type': self.fel_pa_recipient_type,
            'fel_pa_taxpayer_type': self.fel_pa_taxpayer_type,
        }
        return action
    
    def ruc_validation(self, vat, fel_pa_taxpayer_type):
        fel_pa_pac = self.env.company.fel_pa_pac
        if fel_pa_pac:
            payload = self._create_ruc_dv_payload(vat, fel_pa_pac, fel_pa_taxpayer_type)

            first_try, msg = self.env['fel_pa.tools.api_request'].create({
                'name': 'ConsultarRucDV: ' + vat,
                'action': 'ConsultarRucDV',
                'payload': payload,
                'fel_pa_pac': fel_pa_pac,
                'url': self.env.company.fel_pa_pac_partner_validation_url if fel_pa_pac == 'digifact' else self.env.company.fel_pa_pac_url,
            }).make_online_request(raise_exception=False)

            if first_try:
                return first_try
            else:
                fel_pa_taxpayer_type = '01' if fel_pa_taxpayer_type == '02' else '02'
                payload = self._create_ruc_dv_payload(vat, fel_pa_pac, fel_pa_taxpayer_type)

                second_try, msg = self.env['fel_pa.tools.api_request'].create({
                    'name': 'ConsultarRucDV: ' + vat,
                    'action': 'ConsultarRucDV',
                    'payload': payload,
                    'fel_pa_pac': fel_pa_pac,
                    'url': self.env.company.fel_pa_pac_partner_validation_url if fel_pa_pac == 'digifact' else self.env.company.fel_pa_pac_url,
                }).make_online_request(raise_exception=True)

                if second_try:
                    return second_try
                else:
                    raise UserError(_("RUC not found"))


    def _create_ruc_dv_payload(self, vat, fel_pa_pac, fel_pa_taxpayer_type):
        payload = ''

        if fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            company_token = self.env.company.fel_pa_pac_company_token or ''
            password_token = self.env.company.fel_pa_pac_password_token or ''

            payload = {
                "consultarRucDVRequest": {
                    "tokenEmpresa": company_token,
                    "tokenPassword": password_token,
                    "tipoRuc": fel_pa_taxpayer_type,
                    "ruc": vat,
                }
            }
        elif fel_pa_pac == 'digifact':
            payload = {
                "RUC": vat,
                "TIPO": int(fel_pa_taxpayer_type),
            }
        
        return payload
        

    @api.model
    def _default_fel_pa_report_template(self):
        report_obj = self.env['ir.actions.report']
        report_id = report_obj.search([('model', '=', 'account.move'), ('report_name', '=', 'multipac_felpa.report_invoice_template_custom')])
        if report_id:
            report_id = report_id[0]
        else:
            report_id = report_obj.search([('model', '=', 'account.move')])[0]
        return report_id

    def _default_fel_pa_report_template1(self):
        for rec in self:
            report_obj = rec.env['ir.actions.report']
            report_id = report_obj.search(
                [('model', '=', 'account.move'), ('report_name', '=', 'multipac_felpa.report_invoice_template_custom')], limit=1)
            if not report_id:
                report_id = report_obj.search([('model', '=', 'account.move')], limit=1)
            if rec.fel_pa_report_template_id and report_id and rec.fel_pa_report_template_id.id < report_id.id:
                rec.fel_pa_report_template_id = report_id
            rec.fel_pa_report_template_id1 = report_id

    fel_pa_report_template_id1 = fields.Many2one('ir.actions.report', string="Plantilla de Factura1", compute='_default_fel_pa_report_template1', help="Seleccione una plantilla para su factura FEL.", domain=[('model', '=', 'account.move')])
    fel_pa_report_template_id = fields.Many2one('ir.actions.report', string="Plantilla de Factura", help="Seleccione una plantilla para su factura FEL.", domain=[('model', '=', 'account.move')])