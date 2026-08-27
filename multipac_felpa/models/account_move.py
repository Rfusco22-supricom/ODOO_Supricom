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

from odoo import api, models, fields, _, tools
from odoo.tools.misc import formatLang
from odoo.tools import float_is_zero
from odoo.exceptions import UserError
import pytz
import re
from datetime import datetime, timedelta
import dateutil.parser
from dateutil.tz import gettz
try:
    import qrcode
except ImportError:
    qrcode = None
try:
    import base64
except ImportError:
    base64 = None
from io import BytesIO

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Compatibility fields for other modules
    # Venezuelan localization fields
    acuerdo_moneda = fields.Boolean(string='Acuerdo Moneda', default=False, help='Compatibility field')
    amount_residual_usd = fields.Float(string='Amount Residual USD', help='Compatibility field')
    amount_tax_bs = fields.Float(string='Amount Tax BS', help='Compatibility field')
    amount_tax_usd = fields.Float(string='Amount Tax USD', help='Compatibility field')
    amount_total_bs = fields.Float(string='Amount Total BS', help='Compatibility field')
    amount_total_usd = fields.Float(string='Amount Total USD', help='Compatibility field')
    amount_untaxed_bs = fields.Float(string='Amount Untaxed BS', help='Compatibility field')
    amount_untaxed_usd = fields.Float(string='Amount Untaxed USD', help='Compatibility field')
    company_type1 = fields.Char(string='Company Type', help='Compatibility field')
    fecha_importacion = fields.Date(string='Fecha Importación', help='Compatibility field')
    identification_id1 = fields.Char(string='Identification ID', help='Compatibility field')
    invoice_payments_widget_bs = fields.Text(string='Invoice Payments Widget BS', help='Compatibility field')
    islr_number_asignado = fields.Char(string='ISLR Number Asignado', help='Compatibility field')
    iva_number_asignado = fields.Char(string='IVA Number Asignado', help='Compatibility field')
    igtf_amount_suggested = fields.Float(string='IGTF Amount Suggested', help='Compatibility field')
    igtf_amount_suggested_bs = fields.Float(string='IGTF Amount Suggested BS', help='Compatibility field')
    igtf_base_suggested = fields.Float(string='IGTF Base Suggested', help='Compatibility field')
    igtf_base_suggested_bs = fields.Float(string='IGTF Base Suggested BS', help='Compatibility field')
    l10n_ve_igtf_applied = fields.Boolean(string='IGTF Applied', default=False, help='Compatibility field')
    maq_fiscal_p = fields.Boolean(string='Maq Fiscal P', default=False, help='Compatibility field')
    marck_paper = fields.Boolean(string='Marck Paper', default=False, help='Compatibility field')
    nationality1 = fields.Char(string='Nationality', help='Compatibility field')
    nro_ctrl = fields.Char(string='Nro Control', help='Compatibility field')
    nro_expediente_impor = fields.Char(string='Nro Expediente Impor', help='Compatibility field')
    nro_planilla_impor = fields.Char(string='Nro Planilla Impor', help='Compatibility field')
    paper_anu = fields.Boolean(string='Paper Anu', default=False, help='Compatibility field')
    people_type_company1 = fields.Char(string='People Type Company', help='Compatibility field')
    people_type_individual1 = fields.Char(string='People Type Individual', help='Compatibility field')
    retain_full_iva = fields.Boolean(string='Retain Full IVA', default=False, help='Compatibility field')
    rif = fields.Char(string='RIF', help='Compatibility field')
    sin_cred = fields.Boolean(string='Sin Cred', default=False, help='Compatibility field')
    supplier_invoice_number = fields.Char(string='Supplier Invoice Number', help='Compatibility field')
    tax_today = fields.Float(string='Tax Today', help='Compatibility field')
    use_invoice_base = fields.Boolean(string='Use Invoice Base', default=False, help='Compatibility field')
    vat_apply = fields.Boolean(string='VAT Apply', default=False, help='Compatibility field')
    wh_iva = fields.Boolean(string='WH IVA', default=False, help='Compatibility field')
    
    # Other compatibility fields
    exchange_differential_count = fields.Integer(string='Exchange Differential Count', help='Compatibility field')
    exchange_differential_widget = fields.Text(string='Exchange Differential Widget', help='Compatibility field')
    
    # Panama withholding certificate integration
    is_panama_company = fields.Boolean(
        string='Es Empresa de Panamá',
        compute='_compute_is_panama_company',
    )
    fel_pa_withholding_ids = fields.Many2many(
        'fel_pa.withholding',
        'fel_pa_withholding_move_rel',
        'move_id',
        'withholding_id',
        string='Certificados de Retención',
        copy=False,
    )

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_is_panama_company(self):
        is_pa = self.env.company.country_id.code == 'PA'
        for rec in self:
            rec.is_panama_company = is_pa

    fel_pa_has_confirmed_withholding = fields.Boolean(
        string='Tiene Retención Confirmada',
        compute='_compute_fel_pa_has_confirmed_withholding',
        store=True,
    )

    @api.depends('fel_pa_withholding_ids.state')
    def _compute_fel_pa_has_confirmed_withholding(self):
        for move in self:
            move.fel_pa_has_confirmed_withholding = any(w.state == 'confirmed' for w in move.fel_pa_withholding_ids)

    def _is_pa_foreign_customer(self):
        self.ensure_one()
        # REQUERIMIENTO: Exclusivo para la empresa de Panamá
        if self.company_id.country_id.code != 'PA':
            return False

        # Verificar si el contacto está clasificado como extranjero
        partner = self.partner_id
        if not partner:
            return False
        
        # Tipo de receptor '04' (Extranjero) de Panamá FEL o destino de operación '2'
        is_foreign = partner.fel_pa_recipient_type == '04' or \
                     partner.commercial_partner_id.fel_pa_recipient_type == '04' or \
                     self.fel_pa_operation_destination == '2'
        
        # Fallback: Si el país no es Panamá
        if not is_foreign:
            country = partner.country_id or partner.commercial_partner_id.country_id
            if country and country.code not in ['PA', 'pa']:
                is_foreign = True
                
        return is_foreign

    def _get_pa_exempt_tax(self):
        self.ensure_one()
        # Buscar dinámicamente el impuesto exento (0%) de la compañía actual
        return self.env['account.tax'].search([
            ('company_id', '=', self.company_id.id),
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', 0.0),
        ], limit=1)

    def action_create_withholding(self):
        """Creates a withholding certificate for this vendor bill."""
        self.ensure_one()
        
        # Calculate positive taxes (Causado) and negative taxes (Retenido)
        itbms_causado = 0.0
        itbms_retenido = 0.0
        for line in self.invoice_line_ids:
            for tax in line.tax_ids:
                if tax.amount > 0:
                    itbms_causado += (line.price_subtotal * tax.amount / 100)
                elif tax.amount < 0:
                    itbms_retenido += abs(line.price_subtotal * tax.amount / 100)

        withholding = self.env['fel_pa.withholding'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'date': fields.Date.context_today(self),
            'line_ids': [(0, 0, {
                'move_id': self.id,
                'base_imponible': self.amount_untaxed,
                'itbms_causado': reversed(self.amount_tax) if self.amount_tax < 0 else (self.amount_tax if not itbms_retenido else itbms_causado),
                'itbms_retenido': itbms_retenido,
            })],
        })
        # Link the withholding to this invoice
        self.write({'fel_pa_withholding_ids': [(4, withholding.id)]})
        return {
            'name': _('Certificado de Retención'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'fel_pa.withholding',
            'res_id': withholding.id,
            'target': 'current',
        }

    picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Related Pickings",
        store=True,
        compute="_compute_picking_ids",
        help="Related pickings (only when the invoice has been generated from a sale "
        "order).",
    )

    delivery_count = fields.Integer(
        string="Delivery Orders", compute="_compute_picking_ids", store=True
    )

    @api.depends("invoice_line_ids", "invoice_line_ids.move_line_ids")
    def _compute_picking_ids(self):
        for invoice in self:
            invoice.picking_ids = invoice.mapped(
                "invoice_line_ids.move_line_ids.picking_id"
            )
            invoice.delivery_count = len(invoice.picking_ids)

    def action_show_picking(self):
        """This function returns an action that display existing pickings
        of given invoice.
        It can either be a in a list or in a form view, if there is only
        one picking to show.
        """
        self.ensure_one()
        form_view_name = "stock.view_picking_form"
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        if len(self.picking_ids) > 1:
            result["domain"] = f"[('id', 'in', {self.picking_ids.ids})]"
        else:
            form_view = self.env.ref(form_view_name)
            result["views"] = [(form_view.id, "form")]
            result["res_id"] = self.picking_ids.id
        return result

    fel_pa_state = fields.Selection([('draft', 'Draft'),
                                     ('accepted', 'Accepted'),
                                     ('rejected', 'Rejected'),
                                     ('contingency', 'Contingency'),
                                     ('cancelled', 'Cancelled'),], string="Panamá FEL State", default='draft', copy=False, tracking=True)

    fel_pa_pdf_download_count = fields.Integer(
        string="Descargas PDF FEL",
        default=0,
        copy=False,
        help="Número de descargas del PDF FEL efectuadas directamente desde el PAC."
    )

    fel_pa_emission_type = fields.Selection([('01', "Prior Authorization, normal operation"),
                                             ('02', "Prior Authorization, contingency operation"),
                                             ('03', "Post emission Authorization, normal operation"),
                                             ('04', "Post emission Authorization, contingency operation")], string="Panamá FEL Emission Type", default='01')
    
    fel_pa_document_type_id = fields.Many2one('fel_pa.tools.document_type', string="Panamá FEL Document Type", copy=False, domain="[('journal_id', '=', journal_id),('active', '=', True)]")

    @api.onchange('journal_id')
    def _onchange_journal_document_type(self):
        for rec in self:
            if not rec.journal_id or not rec.fel_pa_active:
                continue
            if rec.fel_pa_document_references_ids:
                continue
            # FIX: Credit notes (out_refund) must use document type '04', not the
            # journal default which is typically '01' (Internal bill). Using the
            # wrong type causes the PAC to stamp the document as a regular invoice.
            if rec.move_type == 'out_refund':
                credit_note_doc_type = rec.journal_id.fel_pa_document_type_ids.filtered(
                    lambda dt: dt.document_type == '04' and dt.active
                )
                if credit_note_doc_type:
                    rec.fel_pa_document_type_id = credit_note_doc_type[0].id
                    continue
            if rec.journal_id.fel_pa_default_document_type_id:
                rec.fel_pa_document_type_id = rec.journal_id.fel_pa_default_document_type_id.id
    
    fel_pa_contingency_id = fields.Many2one('fel_pa.tools.contingency', string="Panamá FEL Contingency", copy=False)

    fel_pa_document_code = fields.Char(string="Panamá FEL Document Code", help="Document Code for Panamá FEL", related='fel_pa_document_type_id.code')
    fel_pa_document_number = fields.Char(string="Panamá FEL Document Number", help="Document Number for Panamá FEL", copy=False, readonly=True, tracking=True)

    fel_pa_operation_nature = fields.Selection([('01', "Sale"),
                                                ('02', 'Export'),
                                                ('10', 'Transfer'),
                                                ('11', 'Return'),
                                                ('12', 'Consignment'),
                                                ('13', 'Remittance'),
                                                ('14', 'Free delivery'),
                                                ('20', 'Purchase'),
                                                ('21', 'Import')], string="Panamá FEL Operation Nature")
    
    fel_pa_operation_destination = fields.Selection([('1', "Panamá"),
                                                     ('2', 'Foreign')], string="Panamá FEL Operation Destination", default='1')
    
    @api.onchange('partner_id')
    def _onchange_partner_operation_destination(self):
        for rec in self:
            if rec.partner_id and rec.partner_id.country_id and rec.partner_id.country_id.code != 'PA':
                rec.fel_pa_operation_destination = '2'
            else:
                rec.fel_pa_operation_destination = '1'
            
            # REQUERIMIENTO: Actualizar impuestos si es cliente extranjero en Panamá
            if rec._is_pa_foreign_customer():
                # Asignar la posición fiscal nativa en vez de forzar impuestos en las líneas.
                fp = rec.partner_id.property_account_position_id or rec.partner_id.fiscal_position_id or self.env['account.fiscal.position'].search([
                    ('name', 'ilike', 'exento'), ('company_id', '=', rec.company_id.id)
                ], limit=1)
                if fp:
                    rec.fiscal_position_id = fp
    
    fel_pa_sale_type = fields.Selection([('1', "Business sale"),
                                         ('2', 'Fixed asset sale'),
                                         ('3', 'Real estate sale'),
                                         ('4', 'Service bill')], string="Panamá FEL Sale Type")
    
    fel_pa_interes_information = fields.Text(string="Panamá FEL Interes Information", help="Interes Information for Panamá FEL")

    fel_pa_payment_method_id = fields.Many2one('account.journal', string="Panamá FEL Payment Method", domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]")

    fel_pa_active = fields.Boolean(string="Panamá FEL Active", related='journal_id.fel_pa_active')
    fel_pa_certify = fields.Boolean(string="Panamá FEL Certify")

    fel_pa_cufe = fields.Char(string="Panamá FEL CUFE", help="CUFE for Panamá FEL", copy=False, tracking=True)
    fel_pa_qr_url = fields.Char(string="Panamá FEL QR Code URL", help="QR Code URL for Panamá FEL", copy=False)
    fel_pa_qr = fields.Binary(string="Panamá FEL QR Code", help="QR Code for Panamá FEL", copy=False)
    fel_pa_date_reception = fields.Datetime(string="Panamá FEL Date Reception", help="Date Reception for Panamá FEL", copy=False)
    fel_pa_authorization_protocol = fields.Char(string="Panamá FEL Authorization Protocol", help="Authorization Protocol for Panamá FEL", copy=False)
    fel_pa_total_in_letters = fields.Char(string="Panamá FEL Total in Letters", help="Total in Letters for Panamá FEL", copy=False)

    fel_pa_cancel_motive = fields.Char(string="Panamá FEL Cancel Motive", help="Cancel Motive for Panamá FEL", copy=False)

    fel_pa_issue_date = fields.Char("Panamá FEL Issue Date", help="Document Issue Date for Panamá FEL", copy=False)
    fel_pa_pos_order = fields.Boolean('Panamá FEL Pos Order')
    fel_pa_offline_generate_invoice = fields.Boolean('Panamá FEL Offline Generated')

    fel_pa_document_references_ids = fields.Many2many('account.move', 'fel_pa_document_references_rel', 'move_id', 'document_id', string="Panamá FEL Document References", copy=False, domain="[('state', 'in', ['posted']), ('company_id', '=', company_id), ('id', '!=', id), ('fel_pa_cufe', '!=', False)]")

    fel_pa_pac = fields.Selection(string="PAC", related='company_id.fel_pa_pac', readonly=True)

    @api.onchange('journal_id')
    def _onchange_journal_fel_pa_certify(self):
        """Sets the fel_pa_certify for the invoice using the selected journal."""
        for rec in self:
            if rec.journal_id and not rec.fel_pa_pos_order and not rec.fel_pa_certify:
                rec.fel_pa_certify = rec.journal_id.fel_pa_certify

    @api.model
    def default_get(self, default_fields):
        """Sets the default values for the invoice."""
        values = super(AccountMove, self).default_get(default_fields)
        # Only set Panama FEL defaults if the company is Panama
        if self.env.company.country_id.code == 'PA':
            if self.env.company.fel_pa_default_payment_method_id:
                values['fel_pa_payment_method_id'] = self.env.company.fel_pa_default_payment_method_id.id
            if self.env.company.fel_pa_default_sale_type:
                values['fel_pa_sale_type'] = self.env.company.fel_pa_default_sale_type
            if self.env.company.fel_pa_default_operation_nature:
                values['fel_pa_operation_nature'] = self.env.company.fel_pa_default_operation_nature
            self._onchange_journal_fel_pa_certify()
        return values
    
    def _compute_fel_pa_qr_code(self, qr_url):
        """Generates the QR code for the invoice."""
        for rec in self:
            qr_image = False
            if rec.fel_pa_qr_url:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=3,
                    border=4,
                )
                qr.add_data(qr_url)
                qr.make(fit=True)
                img = qr.make_image()
                temp = BytesIO()
                img.save(temp, format="PNG")
                qr_image = base64.b64encode(temp.getvalue())
            rec.update({'fel_pa_qr': qr_image})

    def _create_fel_pa_query_payload(self, type='pdf', extra_payload=None):
        """Query payload for the invoice."""

        payload = ''

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            company_token = self.company_id.fel_pa_pac_company_token or ''
            password_token = self.company_id.fel_pa_pac_password_token or ''

            if type == 'email_tracking':

                payload = {
                    "tokenEmpresa": company_token,
                    "tokenPassword": password_token,
                    "cufe": self.fel_pa_cufe,
                }

            elif type == 'cancel':

                motive = _('Cancelation by User')
                if self.fel_pa_cancel_motive or extra_payload:
                    motive = extra_payload or self.fel_pa_cancel_motive

                payload = {
                    "tokenEmpresa": company_token,
                    "tokenPassword": password_token,
                    "motivoAnulacion": motive,
                    "datosDocumento": {
                        "codigoSucursalEmisor": self.journal_id.fel_pa_code_branch_issuer or self.journal_id.code,
                        "numeroDocumentoFiscal": self.fel_pa_document_number,
                        "puntoFacturacionFiscal": self.fel_pa_document_code,
                        "tipoDocumento": self.fel_pa_document_type_id.document_type,
                        "tipoEmision": self.fel_pa_emission_type,
                    }
                }

            else:
                dict_payload ={
                    "codigoSucursalEmisor": self.journal_id.fel_pa_code_branch_issuer or self.journal_id.code,
                    "numeroDocumentoFiscal": self.fel_pa_document_number,
                    "puntoFacturacionFiscal": self.fel_pa_document_code,
                    "tipoDocumento": self.fel_pa_document_type_id.document_type,
                    "tipoEmision": self.fel_pa_emission_type,
                }

                if type == 'pdf':
                    dict_payload['serialDispositivo'] = ''

                payload = {
                    "tokenEmpresa": company_token,
                    "tokenPassword": password_token,
                    "datosDocumento": dict_payload
                }

                if type == 'email':
                    payload['correo'] = self.partner_id.email

        elif self.company_id.fel_pa_pac == 'digifact':

            payload = {
                "CUFE": self.fel_pa_cufe,
                "FORMAT": type.upper(),
                "NUMBER": self.fel_pa_document_number,
                'TIPODOC': self.fel_pa_document_type_id.document_type,
            }

        return payload
    
    def _create_fel_pa_attachment(self, name, pdf_content, type='pdf'):
        """Creates or updates an attachment for the invoice PDF/XML, eliminating historical duplicate attachments."""
        mimetype = 'application/pdf' if type == 'pdf' else 'text/xml'
        
        # Buscar adjuntos previos del mismo documento y tipo para refrescar en lugar de acumular histórico
        existing_attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id),
            ('mimetype', '=', mimetype),
            '|', ('name', '=', name), ('name', 'ilike', 'FEL-%')
        ])
        
        if existing_attachments:
            attachment = existing_attachments[0]
            attachment.sudo().write({
                'name': name,
                'datas': pdf_content,
                'mimetype': mimetype,
            })
            if len(existing_attachments) > 1:
                existing_attachments[1:].sudo().unlink()
        else:
            attachment = self.env['ir.attachment'].sudo().create({
                'name': name,
                'mimetype': mimetype,
                'res_model': 'account.move',
                'type': 'binary',
                'public': False,
                'datas': pdf_content,
                'res_id': self.id
            })

        if type == 'pdf':
            self.sudo().write({'message_main_attachment_id': attachment.id})

        return attachment

    def _get_fel_pa_action_for_attachment(self, attachment_id):
        """Returns the action to download the attachment with cache-busting token."""
        import time
        unique_token = attachment_id.checksum or str(int(time.time()))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true&unique=%s' % (attachment_id.id, unique_token),
            'target': 'self',
            'nodestroy': False,
            'context': self._context,
        }

    def fel_pa_pdf_download(self):
        """Downloads the PDF for the invoice and increments the download counter."""
        for rec in self:
            rec.fel_pa_pdf_download_count += 1

        if self.fel_pa_cufe:
            import re
            match = re.search(r'\-[\d]{6}(\d{8})(\d{10})', self.fel_pa_cufe)
            if match:
                doc_number = match.group(2)
                if self.fel_pa_document_number != doc_number:
                    self.fel_pa_document_number = doc_number

        payload = self._create_fel_pa_query_payload()

        result_fel, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'DescargaPDF: ' + str(self.id),
            'action': 'DescargaPDF',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_pac_document_download_url if self.company_id.fel_pa_pac == 'digifact' else self.company_id.fel_pa_pac_url,
            'company_id': self.company_id.id,
        }).make_online_request(raise_exception=False)

        if not result_fel:
            if self.fel_pa_state == 'accepted':
                try:
                    report_action = self.env.ref('account.account_invoices', raise_if_not_found=False)
                    if not report_action:
                        report_action = self.env['ir.actions.report'].sudo().search([('model', '=', 'account.move')], limit=1)
                    pdf_content = report_action.sudo().with_context(no_attachment=True)._render_qweb_pdf(report_action.id, [self.id])[0]
                    pdf_b64 = base64.b64encode(pdf_content).decode('utf-8')
                except Exception:
                    raise UserError(_("The PDF could not be downloaded. Error: %s") % msg)
            else:
                raise UserError(_("The PDF could not be downloaded. Error: %s") % msg)
        else:
            pdf_b64 = result_fel[0]
            try:
                import base64
                import io
                raw_pdf = base64.b64decode(pdf_b64)

                pdf_text = ""
                try:
                    reader = None
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(io.BytesIO(raw_pdf))
                    except Exception:
                        try:
                            from PyPDF2 import PdfFileReader
                            reader = PdfFileReader(io.BytesIO(raw_pdf))
                        except Exception:
                            reader = None

                    if reader:
                        num_pages = len(reader.pages) if hasattr(reader, 'pages') else reader.getNumPages()
                        for i in range(num_pages):
                            page = reader.pages[i] if hasattr(reader, 'pages') else reader.getPage(i)
                            if hasattr(page, 'extract_text'):
                                try:
                                    pdf_text += page.extract_text() or ""
                                except Exception:
                                    pass
                            if hasattr(page, 'extractText'):
                                try:
                                    pdf_text += page.extractText() or ""
                                except Exception:
                                    pass
                except Exception as pe:
                    import logging
                    logging.getLogger(__name__).warning("Error extracting text from PAC PDF: %s", pe)

                is_mismatched_cufe = False
                if self.fel_pa_cufe:
                    if pdf_text:
                        is_mismatched_cufe = self.fel_pa_cufe not in pdf_text
                    else:
                        is_mismatched_cufe = self.fel_pa_cufe.encode('utf-8') not in raw_pdf

                is_rejected_stamp = bool('RECHAZADO' in pdf_text or 'Rechazado' in pdf_text or 'RECHAZADA' in pdf_text or b'RECHAZADO' in raw_pdf)

                if self.fel_pa_state == 'accepted' and is_rejected_stamp:
                    existing_atts = self.env['ir.attachment'].sudo().search([
                        ('res_model', '=', 'account.move'),
                        ('res_id', '=', self.id),
                        ('mimetype', '=', 'application/pdf')
                    ])
                    if existing_atts:
                        existing_atts.unlink()

                    report_action = self.fel_pa_report_template_id or self.company_id.fel_pa_report_template_id or self.env.ref('account.account_invoices', raise_if_not_found=False)
                    if not report_action:
                        report_action = self.env['ir.actions.report'].sudo().search([
                            ('model', '=', 'account.move'),
                            ('report_type', '=', 'qweb-pdf')
                        ], limit=1)
                    if report_action:
                        pdf_content = report_action.sudo().with_context(no_attachment=True)._render_qweb_pdf(report_action.id, [self.id])[0]
                        raw_pdf = pdf_content
                        pdf_b64 = base64.b64encode(pdf_content).decode('utf-8')

                try:
                    report_sudo = self.env['ir.actions.report'].sudo().search([('model', '=', 'account.move')], limit=1)
                    if report_sudo:
                        stream = io.BytesIO(raw_pdf)
                        merged_stream = report_sudo.merge_extra_content_pdf(self.id, stream)
                        if merged_stream and merged_stream != stream:
                            merged_bytes = merged_stream.getvalue()
                            if merged_bytes:
                                pdf_b64 = base64.b64encode(merged_bytes).decode('utf-8')
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Error processing PDF merge in fel_pa_pdf_download: %s", e)
            except Exception as outer_e:
                import logging
                logging.getLogger(__name__).warning("Error in fel_pa_pdf_download processing: %s", outer_e)

            attachment = self._create_fel_pa_attachment('FEL-' + str(self.fel_pa_document_number), pdf_b64)
            return self._get_fel_pa_action_for_attachment(attachment)
        
    def fel_pa_xml_download(self):
        """Downloads the XML for the invoice."""
        if self.fel_pa_cufe:
            import re
            match = re.search(r'\-[\d]{6}(\d{8})(\d{10})', self.fel_pa_cufe)
            if match:
                doc_number = match.group(2)
                if self.fel_pa_document_number != doc_number:
                    self.fel_pa_document_number = doc_number

        payload = self._create_fel_pa_query_payload(type='xml')

        result_fel, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'DescargaXML: ' + str(self.id),
            'action': 'DescargaXML',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_pac_document_download_url if self.company_id.fel_pa_pac == 'digifact' else self.company_id.fel_pa_pac_url,
            'company_id': self.company_id.id,
        }).make_online_request(raise_exception=False)

        if not result_fel:
            raise UserError(_("The PDF could not be downloaded. Error: %s") % msg)
        else:
            attachment = self._create_fel_pa_attachment('FEL-' + str(self.fel_pa_document_number), result_fel[0], type='xml')
            return self._get_fel_pa_action_for_attachment(attachment)
        
    def fel_pa_send_email(self, raise_exception=False):
        """Send the invoice by email by FEL PAC."""

        if self.partner_id.email:
            payload = self._create_fel_pa_query_payload(type='email')

            result_fel, msg = self.env['fel_pa.tools.api_request'].create({
                'name': 'EnvioCorreo: ' + str(self.id),
                'action': 'EnvioCorreo',
                'payload': payload,
                'fel_pa_pac': self.company_id.fel_pa_pac,
                'url': self.company_id.fel_pa_pac_url,
                'company_id': self.company_id.id,
            }).make_online_request(raise_exception=False)

            if not result_fel:
                raise UserError(_("The email could not be sent. Error: %s") % msg)
            else:
                self.message_post(body=_("The email by PAC has been sent successfully."))
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Email Successfully Sent'),
                        'type': 'success',
                        'sticky': False,
                        'message': _('The email by PAC has been sent successfully. PAC Message: %s') % msg,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
        else:
            if raise_exception:
                raise UserError(_("The partner does not have an email address."))
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Missing Partner Email'),
                        'type': 'danger',
                        'sticky': False,
                        'message': _('The partner does not have an email address.'),
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }

    def action_referenced_debit_note(self):
        """Generates a debit note for the invoice."""
        for rec in self:
            
            fel_pa_document_type_id = self.env['fel_pa.tools.document_type'].search([('journal_id', '=', rec.journal_id.id), ('document_type', '=', '05'), ('active', '=', True)], limit=1)

            ctx = self._context.copy()
            ctx.update({
                'default_journal_id': rec.journal_id.id,
                'default_fel_pa_document_type_id': fel_pa_document_type_id.id,
                'default_partner_id': rec.partner_id.id,
                'default_fel_pa_document_references_ids': [(6, 0, [rec.id])],
            })

            return {
                'name': _('Create invoice/bill'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'account.move',
                'view_id': self.env.ref('account.view_move_form').id,
                'context': ctx
            }

    def _get_fel_phone_number(self, phone):
        """
        Validates and formats the phone number to ensure it matches the allowed formats.
        Allowed formats: 999-9999 or 9999-9999.
        Removes the country code if present (e.g., +507).
        """
        if phone:
            phone = re.sub(r'^\+507\s*', '', phone)
            phone = re.sub(r'\D', '', phone)
            
            if re.match(r'^\d{3}-\d{4}$', phone) or re.match(r'^\d{4}-\d{4}$', phone):
                return phone
            elif len(phone) == 7:
                return f"{phone[:3]}-{phone[3:]}"
            elif len(phone) == 8:
                return f"{phone[:4]}-{phone[4:]}"
        return None

    def _get_fel_issue_date(self):
        """Get the emission date in the correct format."""
        current_time = datetime.now(gettz("America/Panama"))
        date = current_time.isoformat(timespec='seconds')
        if not self.invoice_date:
            date = current_time.isoformat(timespec='seconds')
        if current_time.date() != self.invoice_date:
            zone = pytz.timezone('America/Panama')
            invoice_date_with_tz = zone.localize(datetime.combine(self.invoice_date, datetime.min.time()))
            formatted_date = invoice_date_with_tz.replace(microsecond=0).isoformat()
            date = formatted_date[:23] + '00'
        self.fel_pa_issue_date = date
        return date
    
    def _convert_fel_date(self, date):
        """Converts the date for the invoice."""
        dte_given_time = dateutil.parser.parse(date)
        timezone_pa_adjust = timedelta(hours=6)
        pa_time = dte_given_time + timezone_pa_adjust
        return pa_time.strftime("%Y-%m-%d %H:%M:%S")


    def _fel_pa_document_data(self):
        """
        Prepares the main document data to be sent in the invoice.
        """

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
            document_data = dict(
                codigoSucursalEmisor=self.journal_id.fel_pa_code_branch_issuer or self.journal_id.code,
                tipoSucursal=self.journal_id.fel_pa_branch_type,
                datosTransaccion=self._fel_pa_prepare_transaction_data(),
                listaItems=self._fel_pa_prepare_items_data(),
                totalesSubTotales=self._fel_pa_prepare_totals_data()
            )

            if self.fel_pa_cufe:
                document_data['usoPosterior'] = dict(cufe=self.fel_pa_cufe)

        elif self.company_id.fel_pa_pac == 'digifact':

            document_data = self._fel_pa_prepare_transaction_data()

        return document_data
    
    def _post(self, soft=True):
        """Post the journal entry of the move."""
        if soft or len(self) == 0:
            return super(AccountMove, self)._post(soft)

        for move in self:
            if not move.is_invoice(include_receipts=True):
                return super(AccountMove, self)._post(soft)
            
            if not move.fel_pa_active or not move.fel_pa_certify:
                return super(AccountMove, self)._post(soft)

            if not move.fel_pa_document_type_id:
                raise UserError(_("The document type is required to post the invoice."))

            # SAFETY NET: Notas de Crédito deben usar tipo '04' o '06'.
            # El onchange ya lo asigna en la UI, pero si la NC fue creada
            # por importación, script o automatización, el onchange no se
            # dispara y el tipo podría ser el default del diario ('01').
            if move.move_type == 'out_refund' and move.fel_pa_document_type_id.document_type not in ('04', '06'):
                correct_type = move.journal_id.fel_pa_document_type_ids.filtered(
                    lambda dt: dt.document_type == '04' and dt.active
                )
                if correct_type:
                    move.fel_pa_document_type_id = correct_type[0]
                else:
                    raise UserError(_(
                        "La Nota de Crédito requiere un tipo de documento '04' "
                        "(Nota de Crédito referente a FE) activo en el diario '%s'. "
                        "Verifique la configuración del diario en Panamá FEL → Tipos de Documento."
                    ) % move.journal_id.name)
            
            move._fel_pa_set_document_number()

            move._fel_pa_remove_unnecesary_tax()

            invoice_response = super(AccountMove, self)._post(soft)

            move._handle_fel_pa()

            return invoice_response
        
    def fel_pa_process_after_post(self):
        """Process the invoice after being posted."""
        self._fel_pa_set_document_number()
        self._fel_pa_remove_unnecesary_tax()
        return self._handle_fel_pa()

    def _fel_pa_remove_unnecesary_tax(self):
        """Removes unnecesary tax_ids from the invoice to FEL."""

        #Discount lines
        filtered_lines = self.invoice_line_ids.filtered(lambda x: x.display_type == "product" and x.price_total < 0)
        if filtered_lines:
            filtered_lines.write({'tax_ids': False})

        #Product lines
        filtered_lines = self.invoice_line_ids.filtered(lambda x: x.display_type == "product" and x.price_total > 0 and x.product_id and x.product_id.fel_pa_exclude_from_invoice)
        if filtered_lines:
            filtered_lines.write({'tax_ids': False})
        
        
    def _handle_fel_pa(self):
        """Handles the FEL process for the invoice."""
        if self.fel_pa_state == 'accepted':
            return
            
        
        if self.fel_pa_pos_order:
            self._handle_fel_pa_pos()
        elif self.company_id.fel_pa_force_offline_normal_consumer and self.partner_id.fel_pa_recipient_type == '02':
            self._handle_fel_pa_contingency()
        elif self.fel_pa_contingency_id or self.journal_id.fel_pa_active_contingency_id:
            self._handle_fel_pa_contingency()
        elif self.move_type in ["in_invoice", "out_invoice", "out_refund"] and self.company_id.fel_pa_pac:
            self.fel_pa_handle_online()

    def _handle_fel_pa_pos(self):
        """Handles the FEL process for the pos invoice. Generic Process"""
        if not self.fel_pa_offline_generate_invoice:
            if self.company_id.fel_pa_force_offline_normal_consumer and self.partner_id.fel_pa_recipient_type == '02':
                self._handle_fel_pa_contingency()
            elif self.fel_pa_contingency_id or self.journal_id.fel_pa_active_contingency_id:
                self._handle_fel_pa_contingency()
            elif self.move_type in ["in_invoice", "out_invoice", "out_refund"] and self.company_id.fel_pa_pac:
                self.fel_pa_handle_online()

    def _handle_fel_pa_contingency(self):
        """Handles the contingency process for the invoice."""

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
            if self.partner_id.fel_pa_recipient_type == '02' and self.company_id.fel_pa_offline_available:
                contingency = self.fel_pa_contingency_id or self.journal_id.fel_pa_active_contingency_id
                if not contingency:
                    contingency = self.env['fel_pa.tools.contingency'].search([('company_id', '=', self.company_id.id), ('active', '=', True), ('journal_id', '=', self.journal_id.id)], limit=1)
                    if not contingency:
                        contingency = self.env['fel_pa.tools.contingency'].sudo().create({
                            'motive': self.company_id.fel_pa_default_contingency_motive or _('Auto-Contingency'),
                            'company_id': self.company_id.id,
                            'journal_id': self.journal_id.id,
                            'active': True
                        })

                if self.fel_pa_emission_type not in ['03','04']:
                    self.write({'fel_pa_emission_type': '03'})
                self.write({'fel_pa_contingency_id': contingency.id})
                self.fel_pa_handle_offline()
            else:
                self.fel_pa_handle_online()
        elif self.company_id.fel_pa_pac == 'digifact':
            self.fel_pa_handle_online()
    
    def fel_pa_process_all_contigency(self):
        """Process all the FEL contingency."""
        contingency_invoices = self.env['account.move'].search([
            ('fel_pa_state', '=', 'contingency'),
        ])
        for invoice in contingency_invoices:
            try:
                invoice.fel_pa_handle_online()
            except Exception as e:
                invoice.message_post(body=str(e))
        
    def _create_enviar_payload(self, xml_data):
        payload = ''

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            company_token = self.company_id.fel_pa_pac_company_token or ''
            password_token = self.company_id.fel_pa_pac_password_token or ''

            payload = dict(
                tokenEmpresa=company_token,
                tokenPassword=password_token,
                documento=xml_data
            )
        
        elif self.company_id.fel_pa_pac == 'digifact':

            payload = xml_data

        return payload
    
    def fel_pa_email_tracking(self):
        """
        Returns the email tracking of the mails from the invoice sent by the PAC.
        """

        payload = self._create_fel_pa_query_payload(type='email_tracking')

        result, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'RastreoCorreo: ' + str(self.id),
            'action': 'RastreoCorreo',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_pac_url,
            'company_id': self.company_id.id,
        }).make_online_request(raise_exception=False)

        view = self.env.ref('multipac_felpa.fel_pa_tools_msg_wizard_form_view')
        context = dict(self._context or {})

        msg = ''

        if result:

            msg = _("The email tracking have been successfully obtained.")
            msg += "\n"

            i = 1
            for line in result:
                msg += "\n" + _("Email No. %s") % i
                msg += _("\nEmail: %s") % line.get('correo', '')
                msg += _("\nDate: %s") % line.get('creado_en', '')
                msg += _("\nEstate: %s") % line.get('estado', '')
                msg += _("\nMessage ID: %s") % line.get('messageId', '')
                msg += "\n"
                i += 1

            context['message'] = msg

            return {
                'name': (_('Email Tracking Results')),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'fel_pa.tools.msg_wizard',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'context': context,
            }
    
    def fel_pa_document_state(self):
        """
        Returns the state of the invoice.
        """

        payload = self._create_fel_pa_query_payload(type='state')

        result, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'EstadoDocumento: ' + str(self.id),
            'action': 'EstadoDocumento',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_pac_document_query_url if self.company_id.fel_pa_pac == 'digifact' else self.company_id.fel_pa_pac_url,
            'company_id': self.company_id.id,
        }).make_online_request(raise_exception=False)

        view = self.env.ref('multipac_felpa.fel_pa_tools_msg_wizard_form_view')
        context = dict(self._context or {})

        msg = ''

        if result:

            msg = _("The document state have been successfully obtained.")
            msg += _("\nCUFE: %s") % result[0]
            msg += _("\nIssue Date: %s") % result[1]
            msg += _("\nReception Date: %s") % result[2]
            msg += _("\nDocument State: %s") % result[3]
            if result[4]:
                msg += _("\nMessage Document: %s") % result[4]
            if result[5]:
                msg += _("\nResult: %s") % result[5]

            self.message_post(body=msg)

            context['message'] = msg

            return {
                'name': (_('Document State')),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'fel_pa.tools.msg_wizard',
                'views': [(view.id, 'form')],
                'view_id': view.id,
                'target': 'new',
                'context': context,
            }
        
    def fel_pa_handle_offline(self):
        """
        Handles the invoice and sends it to the FEL.
        """
        if not self.company_id.fel_pa_offline_utility_path:
            raise UserError(_("The Offline Utility Path is not set for the company."))
        if not self.company_id.fel_pa_offline_pending_path:
            raise UserError(_("The Offline Pending Path is not set for the company."))

        payload = self._create_enviar_payload(self._fel_pa_document_data())
        
        result_fel, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'Enviar: ' + str(self.id),
            'action': 'Enviar',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_offline_utility_path,
            'company_id': self.company_id.id,
        }).make_offline_request()

        if not result_fel:
            if not self.company_id.fel_pa_publish_onerror:
                raise UserError(_("The invoice could not be sent to the FEL. Error: %s") % msg)
            else:
                self.fel_pa_state = 'rejected'
                self.message_post(body=_("The invoice could not be sent to the FEL, please validate the information and try again. Error: %s") % msg)
                return False
        else:
            self.fel_pa_state = 'contingency'
            self.fel_pa_cufe = result_fel[0]
            self.fel_pa_qr_url = result_fel[1]
            self._compute_fel_pa_qr_code(result_fel[1])
            self.fel_pa_total_in_letters = str(number2text(self.amount_total, self.currency_id.currency_unit_label))
        
        
    def fel_pa_handle_online(self):
        """
        Handles the invoice and sends it to the FEL.
        """

        if self.fel_pa_cufe and self.company_id.fel_pa_pac != 'efacturapty':
            payload = self._create_fel_pa_query_payload(type='state')

            result, msg = self.env['fel_pa.tools.api_request'].create({
                'name': 'EstadoDocumento: ' + str(self.id),
                'action': 'EstadoDocumento',
                'payload': payload,
                'fel_pa_pac': self.company_id.fel_pa_pac,
                'url': self.company_id.fel_pa_pac_url,
                'company_id': self.company_id.id,
            }).make_online_request(raise_exception=False)

            if not result:
                if not self.company_id.fel_pa_publish_onerror:
                    raise UserError(_("The invoice could not be sent to the FEL. Error: %s") % msg)
                else:
                    self.fel_pa_state = 'rejected'
                    self.message_post(body=_("The invoice could not be sent to the FEL, please validate the information and try again. Error: %s") % msg)
                    return False
            elif result and result[3] and result[3].lower() in ['autorizada', 'autorizado', 'aceptada', 'aceptado']:
                msg = _("The document state have been successfully obtained.")
                msg += _("\nCUFE: %s") % result[0]
                msg += _("\nIssue Date: %s") % result[1]
                msg += _("\nReception Date: %s") % result[2]
                msg += _("\nDocument State: %s") % result[3]
                msg += _("\nMessage Document: %s") % result[4]
                msg += _("\nResult: %s") % result[5]

                self.message_post(body=msg)
                self.fel_pa_state = 'accepted'
                self._compute_fel_pa_qr_code(self.fel_pa_qr_url)
                self.fel_pa_date_reception = self._convert_fel_date(result[2])

        else:
            payload = self._create_enviar_payload(self._fel_pa_document_data())
            
            result_fel, msg = self.env['fel_pa.tools.api_request'].create({
                'name': 'Enviar: ' + str(self.id),
                'action': 'Enviar',
                'payload': payload,
                'fel_pa_pac': self.company_id.fel_pa_pac,
                'url': self.company_id.fel_pa_pac_url,
                'company_id': self.company_id.id,
            }).make_online_request(raise_exception=False)

            if not result_fel:
                if msg and ('duplicado' in msg.lower() or 'ya existe' in msg.lower() or 'duplicada' in msg.lower()):
                    if self._fel_pa_sync_duplicate():
                        return True

                if not self.company_id.fel_pa_publish_onerror:
                    raise UserError(_("The invoice could not be sent to the FEL. Error: %s") % msg)
                else:
                    self.fel_pa_state = 'rejected'
                    self.message_post(body=_("The invoice could not be sent to the FEL, please validate the information and try again. Error: %s") % msg)
                    return False
            else:
                self.fel_pa_state = 'accepted'
                self.fel_pa_cufe = result_fel[0]
                self.fel_pa_qr_url = result_fel[1]
                self._compute_fel_pa_qr_code(result_fel[1])
                self.fel_pa_date_reception = self._convert_fel_date(result_fel[2])
                self.fel_pa_authorization_protocol = result_fel[3]
        self.fel_pa_total_in_letters = str(number2text(self.amount_total, self.currency_id.currency_unit_label))

    def _fel_pa_sync_duplicate(self):
        """
        Intenta sincronizar un documento que ya fue enviado al PAC (por ejemplo, si hubo un timeout 
        pero el documento sí se procesó y ahora da 'Documento duplicado').
        """
        self.ensure_one()
        payload = self._create_fel_pa_query_payload(type='state')

        result, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'EstadoDocumentoSync: ' + str(self.id),
            'action': 'EstadoDocumento',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_pac_document_query_url if self.company_id.fel_pa_pac == 'digifact' else self.company_id.fel_pa_pac_url,
            'company_id': self.company_id.id,
        }).make_online_request(raise_exception=False)

        if result and result[3] and result[3].lower() in ['autorizada', 'autorizado', 'aceptada', 'aceptado']:
            self.fel_pa_state = 'accepted'
            self.fel_pa_cufe = result[0]
            if result[2] and result[2] != 'N/A':
                self.fel_pa_date_reception = self._convert_fel_date(result[2])
            
            # Asignar un código QR en base al CUFE
            qr_url = f"https://fe.dgi.mef.gob.pa/Consultas/FacturasPorCUFE?cufe={self.fel_pa_cufe}"
            self.fel_pa_qr_url = qr_url
            self._compute_fel_pa_qr_code(qr_url)
            
            message = _("El documento ya había sido procesado previamente en el PAC y ha sido sincronizado con éxito.")
            message += _("\nCUFE: %s") % result[0]
            self.message_post(body=message)
            return True

        # Fallback: Try to download XML to check if it's actually authorized and get CUFE
        try:
            xml_payload = self._create_fel_pa_query_payload(type='xml')
            xml_result, xml_msg = self.env['fel_pa.tools.api_request'].create({
                'name': 'DescargaXMLSync: ' + str(self.id),
                'action': 'DescargaXML',
                'payload': xml_payload,
                'fel_pa_pac': self.company_id.fel_pa_pac,
                'url': self.company_id.fel_pa_pac_document_download_url if self.company_id.fel_pa_pac == 'digifact' else self.company_id.fel_pa_pac_url,
                'company_id': self.company_id.id,
            }).make_online_request(raise_exception=False)
            
            if xml_result and xml_result[0]:
                import base64
                import re
                xml_content = base64.b64decode(xml_result[0]).decode('utf-8', errors='ignore')
                # Search for CUFE in XML
                match = re.search(r'<[a-zA-Z0-9:]*dCUFE[^>]*>([^<]+)</', xml_content, re.IGNORECASE)
                if match:
                    self.fel_pa_state = 'accepted'
                    self.fel_pa_cufe = match.group(1).strip()
                    
                    self._get_fel_issue_date()
                    date_rec_match = re.search(r'<[a-zA-Z0-9:]*dFecRec[^>]*>([^<]+)</', xml_content, re.IGNORECASE)
                    if date_rec_match:
                        self.fel_pa_date_reception = self._convert_fel_date(date_rec_match.group(1).strip())
                    elif not self.fel_pa_date_reception:
                        from datetime import datetime
                        self.fel_pa_date_reception = self._convert_fel_date(datetime.now().isoformat())
                    
                    # Set qr url
                    qr_url = f"https://fe.dgi.mef.gob.pa/Consultas/FacturasPorCUFE?cufe={self.fel_pa_cufe}"
                    self.fel_pa_qr_url = qr_url
                    self._compute_fel_pa_qr_code(qr_url)
                    
                    message = _("El documento ya había sido procesado previamente en el PAC y ha sido sincronizado automáticamente mediante recuperación de XML.")
                    message += _("\nCUFE: %s") % self.fel_pa_cufe
                    self.message_post(body=message)
                    return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Fallback XML sync failed: %s", e)
            
        return False

    def action_sync_fel_pa_document(self):
        """
        Sincroniza manualmente el documento si se quedó en estado de borrador u otro estado
        y ya existe en el PAC.
        """
        import re
        for move in self:
            if move.fel_pa_cufe:
                # User manually entered the CUFE. Let's accept it.
                cufe_match = re.search(r'(FE[a-zA-Z0-9\-]+)', move.fel_pa_cufe)
                if cufe_match:
                    move.fel_pa_cufe = cufe_match.group(1)
                    
                move.fel_pa_state = 'accepted'
                move._get_fel_issue_date()
                if not move.fel_pa_date_reception:
                    from datetime import datetime
                    move.fel_pa_date_reception = move._convert_fel_date(datetime.now().isoformat())
                    
                qr_url = f"https://fe.dgi.mef.gob.pa/Consultas/FacturasPorCUFE?cufe={move.fel_pa_cufe}"
                move.fel_pa_qr_url = qr_url
                move._compute_fel_pa_qr_code(qr_url)
                message = _("El documento fue sincronizado manualmente mediante CUFE ingresado: %s") % move.fel_pa_cufe
                move.message_post(body=message)
                if move.state == 'draft':
                    move.action_post()
                continue
                
            if move.fel_pa_state != 'accepted':
                success = move._fel_pa_sync_duplicate()
                if success and move.state == 'draft':
                    move.action_post()
                if not success:
                    raise UserError(_("No se pudo sincronizar el documento. Verifique que ya esté emitido en el portal PAC."))

    def _fel_pa_set_document_number(self):
        """
        Sets the document number for the invoice.
        """
        if not self.fel_pa_document_number:
            transaction_number = self.fel_pa_document_type_id._get_next_number()
            self.fel_pa_document_number = transaction_number
    
    def _fel_pa_prepare_transaction_data(self):
        """
        Prepares the transaction data for the invoice.
        """
        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
            transaction_data = dict(
                tipoEmision=self.fel_pa_emission_type,
                tipoDocumento=self.fel_pa_document_type_id.document_type,
                numeroDocumentoFiscal=str(self.fel_pa_document_number),
                puntoFacturacionFiscal=self.fel_pa_document_code,
                naturalezaOperacion=self.fel_pa_operation_nature,
                tipoOperacion='1' if self.move_type in ['out_invoice', 'out_refund'] else '2',
                destinoOperacion=self.fel_pa_operation_destination,
                formatoCAFE=int(self.journal_id.fel_pa_cafe_format),
                entregaCAFE=int(self.journal_id.fel_pa_cafe_delivery),
                envioContenedor=int(self.journal_id.fel_pa_container_sent),
                procesoGeneracion=1,
                tipoVenta=self.fel_pa_sale_type,
                fechaEmision=self._get_fel_issue_date()
            )

            info_parts = []
            bank_info = (self.company_id.fel_pa_bank_account_info or '').strip()
            if bank_info:
                clean_bank_info = tools.html2plaintext(bank_info).strip()
                if clean_bank_info:
                    info_parts.append(clean_bank_info)
            elif self.partner_bank_id:
                bank_name = self.partner_bank_id.bank_id.name or ''
                acc_number = self.partner_bank_id.acc_number or ''
                if bank_name or acc_number:
                    info_parts.append(_("Banco: %s - Cuenta: %s") % (bank_name, acc_number))

            if self.company_id.fel_pa_is_show_payment_notes and self.invoice_payment_term_id:
                info_parts.append(_("Términos de Pago: %s") % self.invoice_payment_term_id.name)

            if self.company_id.fel_pa_is_show_notes and self.narration:
                clean_narration = tools.html2plaintext(self.narration).strip() if self.narration else ''
                if clean_narration:
                    info_parts.append(_("Nota: %s") % clean_narration)

            custom_interes = (self.fel_pa_interes_information or '').strip()
            if custom_interes and custom_interes not in info_parts:
                info_parts.append(custom_interes)

            if info_parts:
                transaction_data['informacionInteres'] = " | ".join(info_parts)

            if self.fel_pa_emission_type in ['02', '04'] and self.fel_pa_contingency_id:
                panama_tz = pytz.timezone('America/Panama')
                start_date_utc = self.fel_pa_contingency_id.start_date.replace(tzinfo=pytz.utc)
                start_date_panama = start_date_utc.astimezone(panama_tz)
                transaction_data['fechaInicioContingencia'] = start_date_panama.strftime('%Y-%m-%d %H:%M:%S%z')
                transaction_data['motivoContingencia'] = self.fel_pa_contingency_id.motive

            transaction_data['cliente'] = self._fel_pa_prepare_client_data()

            if self.fel_pa_document_type_id.document_type in ['04', '05']:
                transaction_data['listaDocsFiscalReferenciados'] = self._fel_pa_prepare_fiscal_references()

            if self.fel_pa_operation_destination == '2':
                transaction_data['datosFacturaExportacion'] = self._fel_pa_prepare_export_data()
        elif self.company_id.fel_pa_pac == 'digifact':

            aditional_info = [
                {"Name": "TipoEmision", "Data": None, "Value": self.fel_pa_emission_type},
                {"Name": "NumeroDF", "Data": None, "Value": str(self.fel_pa_document_number)},
                {"Name": "PtoFactDF", "Data": None, "Value": self.fel_pa_document_code},
                {"Name": "CodigoSeguridad", "Data": None, "Value": f"{self.id:09}"},
                {"Name": "NaturalezaOperacion", "Data": None, "Value": self.fel_pa_operation_nature},
                {"Name": "TipoOperacion", "Data": None, "Value": '1' if self.move_type in ['out_invoice', 'out_refund'] else '2'},
                {"Name": "DestinoOperacion", "Data": None, "Value": self.fel_pa_operation_destination},
                {"Name": "FormatoGeneracion", "Data": None, "Value": self.journal_id.fel_pa_cafe_format},
                {"Name": "ManeraEntrega", "Data": None, "Value": self.journal_id.fel_pa_cafe_delivery},
                {"Name": "EnvioContenedor", "Data": None, "Value": self.journal_id.fel_pa_container_sent},
                {"Name": "ProcesoGeneracion", "Data": None, "Value": '1'},
                {"Name": "TipoTransaccion", "Data": None, "Value": self.fel_pa_sale_type},
                {"Name": "TipoSucursal", "Data": None, "Value": self.journal_id.fel_pa_branch_type},
            ]

            ignored_lines = self.invoice_line_ids.filtered(
                lambda x: x.display_type == "product" and x.price_total > 0 and x.product_id and x.product_id.fel_pa_exclude_from_invoice)
            ignored_amount = sum(ignored_lines.mapped('price_total'))

            transaction_data = dict(
                Version="1.00",
                CountryCode="PA",
                Header=dict(
                    DocType=self.fel_pa_document_type_id.document_type,
                    IssuedDateTime=self._get_fel_issue_date(),
                    AdditionalIssueType=2 if self.company_id.fel_pa_pac_enviroment == 'test' else 1,
                    AdditionalIssueDocInfo=aditional_info,
                ),
                Seller=self._fel_pa_prepare_seller_data(),
                Buyer=self._fel_pa_prepare_client_data(),
                ThirdParties=None,
                Items=self._fel_pa_prepare_items_data(),
                Charges=None,
                Totals=self._fel_pa_prepare_totals_data(),
                Payments=self._fel_pa_prepare_payment_methods_data(ignored_amount),
                AdditionalDocumentInfo=dict(AdditionalInfo=[dict(AditionalInfo=[{"Name": "TiempoPago", "Data": None, "Value": "1"}])])
            )

            if self.fel_pa_document_type_id.document_type in ['04', '05']:
                transaction_data['AdditionalDocumentInfo']['AdditionalInfo'][0]['AditionalData'] = self._fel_pa_prepare_fiscal_references()
        return transaction_data
    
    def _fel_pa_prepare_seller_data(self):
        """
        Prepares the seller data for the invoice.
        """
        phone = self.company_id.phone or self.company_id.mobile
        fel_phone = self._get_fel_phone_number(phone)
        seller_data = dict(
            TaxID=self.company_id.vat,
            TaxIDType="2",
            TaxIDAdditionalInfo=[{"Name": "DigitoVerificador", "Data": None, "Value": self.company_id.fel_pa_dv}],
            Name=self.company_id.name,
            Contact={'PhoneList': {"Phone": [fel_phone]}},
            BranchInfo=dict(
                Code=self.journal_id.fel_pa_code_branch_issuer or self.journal_id.code,
                AddressInfo={"Address": self.company_id.street or '', "City": self.company_id.city or '', "District": self.company_id.city_id.name if self.company_id.city_id else 'PANAMA', "State": self.company_id.state_id.name or 'PANAMA', "Country": "PA"},
                AdditionalBranchInfo=[{"Name": "CoordEm", "Data": None, "Value": self.journal_id.fel_pa_coordinates if self.journal_id.fel_pa_coordinates else '+8.9824,-79.5199'},
                                       {"Name": "CodUbi", "Data": None, "Value": self.company_id.fel_pa_county_id.fel_pa_code}],
            ),
        )

        return seller_data
    
    def _fel_pa_prepare_fiscal_references(self):
        """
        Prepares the fiscal references for the invoice.
        """
        fiscal_references = []

        if not self.fel_pa_document_references_ids:
            raise UserError(_("The credit note or debit note must have a reference to the original(s) invoice(s)."))

        for reference in self.fel_pa_document_references_ids.filtered(lambda x: x.fel_pa_cufe):
            if self.company_id.fel_pa_pac == 'digifact':
                fiscal_references.append({'Info': [{'Name': 'NombEmRef', 'Data': None, 'Value': "FE generada en ambiente de pruebas - sin valor comercial ni fiscal" if self.company_id.fel_pa_pac_enviroment == 'test' else self.company_id.name},
                                                    {'Name': 'FechaDFRef', 'Data': None, 'Value': reference.fel_pa_issue_date},
                                                    {'Name': 'CUFERef', 'Data': None, 'Value': reference.fel_pa_cufe}],
                                                    'Name': None})
            elif self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
                fiscal_references.append(dict(
                    fechaEmisionDocFiscalReferenciado=reference.fel_pa_issue_date,
                    cufeFEReferenciada=str(reference.fel_pa_cufe)
                ))

        return dict(Data=fiscal_references) if self.company_id.fel_pa_pac == 'digifact' else dict(docFiscalReferenciado=fiscal_references)
    
    def _fel_pa_prepare_export_data(self):
        """
        Prepares the export data for the invoice.
        """
        export_data = dict(
            condicionesEntrega=self.invoice_incoterm_id.code if self.invoice_incoterm_id else 'EXW',
        )

        if self.currency_id.name not in ['USD', 'PAB'] and self.currency_id.display_name not in ['USD', 'PAB']:
            export_data['monedaOperExportacion'] = self.currency_id.name
            export_data['tipoDeCambio'] = str(self.currency_id.with_context(date=self.invoice_date).rate)
            export_data['montoMonedaExtranjera'] = self.amount_total

        return export_data

    def _fel_pa_prepare_client_data(self):
        """
        Prepares the client data for the invoice.
        """
        phone = self.partner_id.phone or self.partner_id.mobile
        fel_phone = self._get_fel_phone_number(phone)

        is_foreign = self._is_pa_foreign_customer()

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            client_data = dict(
                tipoClienteFE='04' if is_foreign else self.partner_id.fel_pa_recipient_type,
                pais=self.partner_id.country_id.code if self.partner_id.country_id else 'PA',
                razonSocial=self.partner_id.name,
                correoElectronico1=''
            )

            # FIX: Foreign customers (tipoClienteFE='04') must NOT include
            # numeroRUC nor digitoVerificadorRUC in the payload. Even if stale
            # data remains in the DB from a previous contributor classification,
            # we force those fields to be absent for the PAC.
            if not is_foreign and self.partner_id.vat:
                client_data['numeroRUC'] = self.partner_id.vat

            if self.fel_pa_document_type_id.document_type not in ['03'] and not is_foreign:
                client_data['tipoContribuyente'] = int(self.partner_id.fel_pa_taxpayer_type)

            emails = (self.partner_id.email or "").split(',')
            emails = [email.strip() for email in emails if email.strip()]

            if len(emails) > 0:
                client_data['correoElectronico1'] = emails[0]
            if len(emails) > 1:
                client_data['correoElectronico2'] = emails[1]
            if len(emails) > 2:
                client_data['correoElectronico3'] = emails[2]

            if not is_foreign:
                # Domestic / government clients: validate and include DV
                if self.partner_id.fel_pa_recipient_type in ['01', '03']:
                    if not self.partner_id.vat:
                        raise UserError(_("El cliente debe tener un RUC para emitir la factura."))
                    if not self.partner_id.fel_pa_dv:
                        raise UserError(_(
                            "El RUC del cliente '%s' no tiene un Dígito Verificador (DV). "
                            "Por favor, valide el RUC en el formulario del contacto."
                        ) % self.partner_id.vat)
                    client_data['digitoVerificadorRUC'] = self.partner_id.fel_pa_dv
                else:
                    client_data['digitoVerificadorRUC'] = self.partner_id.fel_pa_dv or '00'

            client_data['direccion'] = ''
            if self.partner_id.street:
                client_data['direccion'] = self.partner_id.street + (
                    (', ' + self.partner_id.street2) if self.partner_id.street2 else ''
                )
            elif self.partner_id.street2:
                client_data['direccion'] = self.partner_id.street2

            if self.partner_id.fel_pa_county_id:
                client_data['codigoUbicacion'] = self.partner_id.fel_pa_county_id.fel_pa_code
                client_data['corregimiento'] = self.partner_id.fel_pa_county_id.name
            elif not is_foreign and self.partner_id.fel_pa_recipient_type in ['01', '03']:
                raise UserError(_("The client must have a location code to issue the invoice."))

            if self.partner_id.state_id:
                client_data['provincia'] = self.partner_id.state_id.name
            elif not is_foreign and self.partner_id.fel_pa_recipient_type in ['01', '03']:
                raise UserError(_("The client must have a state to issue the invoice."))

            if self.partner_id.city_id:
                client_data['distrito'] = self.partner_id.city_id.name
            elif not is_foreign and self.partner_id.fel_pa_recipient_type in ['01', '03']:
                raise UserError(_("The client must have a city to issue the invoice."))

            if fel_phone:
                client_data['telefono1'] = fel_phone

            if is_foreign:
                # Foreign-specific identification fields
                if self.partner_id.l10n_latam_identification_type_id.id == self.env.ref('l10n_latam_base.it_pass').id:
                    client_data['tipoIdentificacion'] = '01'
                    client_data['paisExtranjero'] = self.partner_id.country_id.name
                elif self.partner_id.l10n_latam_identification_type_id.id == self.env.ref('l10n_latam_base.it_fid').id:
                    client_data['tipoIdentificacion'] = '02'
                else:
                    client_data['tipoIdentificacion'] = '99'
                client_data['nroIdentificacionExtranjero'] = self.partner_id.vat

        elif self.company_id.fel_pa_pac == 'digifact':

            tax_id_additional_info = [
                {"Name": "TipoReceptor", "Data": None, "Value": '04' if is_foreign else (self.partner_id.fel_pa_recipient_type or '02')},
            ]
            if not is_foreign:
                tax_id_additional_info.append(
                    {"Name": "CodUbi", "Data": None, "Value": self.partner_id.fel_pa_county_id.fel_pa_code if self.partner_id.fel_pa_county_id else '1-1-1'}
                )

            client_data = dict(
                # FIX: Foreign customers must NOT send the RUC as TaxID.
                # Use a neutral placeholder so the PAC does not reject the document
                # due to stale RUC data that may remain from a prior classification.
                TaxID='' if is_foreign else (self.partner_id.vat or '00-00-00'),
                TaxIDAdditionalInfo=tax_id_additional_info,
                Name=self.partner_id.name,
                Contact=None,
                AdditionlInfo=[{"Name": "PaisReceptorFE", "Data": None, "Value": self.partner_id.country_id.code if self.partner_id.country_id else 'PA'}],
                AddressInfo={
                    "Address": self.partner_id.street or ('' if is_foreign else 'PANAMA'),
                    "City": self.partner_id.city or ('' if is_foreign else 'PANAMA'),
                    "District": self.partner_id.city_id.name if self.partner_id.city_id else ('' if is_foreign else "PANAMA"),
                    "State": self.partner_id.state_id.name if self.partner_id.state_id else ('' if is_foreign else 'PANAMA'),
                    "Country": self.partner_id.country_id.code if self.partner_id.country_id else 'PA',
                }
            )

            if self.fel_pa_document_type_id.document_type not in ['03']:
                # FIX: Foreign customers must NOT include TaxIDType nor
                # DigitoVerificador — those fields are exclusive to domestic RUCs.
                if not is_foreign:
                    client_data['TaxIDType'] = self.partner_id.fel_pa_taxpayer_type
                    client_data['TaxIDAdditionalInfo'].append(
                        {"Name": "DigitoVerificador", "Data": None, "Value": self.partner_id.fel_pa_dv or '00'}
                    )

            contact_data = dict()
            if fel_phone:
                contact_data['PhoneList'] = {"Phone": [fel_phone]}
            if self.partner_id.email:
                contact_data['EmailList'] = {"Email": [self.partner_id.email]}

            if contact_data:
                client_data['Contact'] = contact_data

        return client_data
    
    def _get_fel_pa_tax(self, val):
        tax_rates = {7.0: '01', 10.0: '02', 15.0: '03'}
        return tax_rates.get(val, '00')
    
    def _fel_pa_prepare_items_data(self):
        """
        Prepares the items in the invoice (products or services).
        """
        decimal_currency = '.{}f'.format(self.currency_id.decimal_places)

        items = []
        for line in self.invoice_line_ids.filtered(lambda x: x.display_type == 'product' and x.price_unit > 0 and x.quantity > 0):
            if line.product_id and line.product_id.fel_pa_exclude_from_invoice:
                continue
            discount = ((line.discount * (line.quantity * line.price_unit))/100)
            item_price = (line.quantity * line.price_unit) - discount
            tax_amount = format(line.price_subtotal * line.tax_ids.amount / 100, decimal_currency)

            if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
                item_dict = dict(
                    cantidad=format(line.quantity, '.2f'),
                    precioUnitario=format(line.price_unit, '.6f'),
                    precioUnitarioDescuento=format(discount / line.quantity, '.6f') if discount else "",
                    precioItem=format(item_price, '.2f'),
                    precioAcarreo="",
                    precioSeguro="",
                    valorTotal=format(line.price_total, '.2f'),
                    codigoGTIN="",
                    cantGTINCom="",
                    codigoGTINInv="",
                    cantGTINComInv="",
                    tasaITBMS=self._get_fel_pa_tax(line.tax_ids.amount) or "",
                    valorITBMS=tax_amount,
                )

                if line.product_id and self.company_id.fel_pa_invoice_line_name == 'product_code':
                    item_dict['descripcion'] = line.product_id.name
                else:
                    item_dict['descripcion'] = line.name

                if line.product_id and line.product_id.default_code:
                    item_dict['codigo'] = line.product_id.default_code

                if self.company_id.fel_pa_default_product_unspsc_category_id:
                    item_dict['codigoCPBSAbrev'] = self.company_id.fel_pa_default_product_unspsc_category_id.fel_pa_code[:2]
                    item_dict['codigoCPBS'] = self.company_id.fel_pa_default_product_unspsc_category_id.fel_pa_code

                if line.product_id and line.product_id.fel_pa_unspsc_category_id:
                    item_dict['codigoCPBSAbrev'] = line.product_id.fel_pa_unspsc_category_id.fel_pa_code[:2]
                    item_dict['codigoCPBS'] = line.product_id.fel_pa_unspsc_category_id.fel_pa_code
                
                if line.product_id and line.product_id.fel_pa_info_item:
                    item_dict['infoItem'] = line.product_id.fel_pa_info_item

                if line.product_id and line.product_id.fel_pa_product_type == 'medicine' and line.move_line_ids:
                    item_dict['medicina'] = self._fel_pa_prepare_medicine_data(line)

                if line.product_id and line.product_id.fel_pa_product_type == 'vehicle':
                    item_dict['vehiculo'] = self._fel_pa_prepare_vehicle_data(line)

            elif self.company_id.fel_pa_pac == 'digifact':
                
                codes = []

                if line.product_id and line.product_id.default_code:
                    codes.append(dict(Name="CodigoProd", Data=None, Value=line.product_id.default_code))

                if line.product_id and line.product_id.fel_pa_unspsc_category_id:
                    codes.append(dict(Name="CodCPBS", Data=None, Value=line.product_id.fel_pa_unspsc_category_id.fel_pa_code[:2]))
                    codes.append(dict(Name="CodCPBScmp", Data=None, Value=line.product_id.fel_pa_unspsc_category_id.fel_pa_code))

                item_dict = dict(
                    Codes=codes,
                    Description=line.product_id.name if (line.product_id and self.company_id.fel_pa_invoice_line_name == 'product_code') else line.name,
                    Qty=format(line.quantity, '.2f'),
                    UnitOfMeasure="und",
                    Price=format((line.price_subtotal / line.quantity) + discount, '.2f'),
                    Discounts={'Discount': [{'Amount': discount}]} if discount else None,
                    Taxes=dict(
                        Tax=[dict(
                            Code=self._get_fel_pa_tax(line.tax_ids.amount) or "",
                            Description="ITBMS",
                            Amount=tax_amount
                        )]
                    ),
                    Totals=dict(
                        TotalBDiscount=format(item_price, '.2f'),
                        TotalWDiscount=format(line.price_subtotal, '.2f'),
                        TotalBTaxes=format(line.price_subtotal, '.2f'),
                        TotalWTaxes=format(line.price_total, '.2f'),
                        SpecificTotal=format(line.price_total, '.2f'),
                        TotalItem=format(line.price_total, '.2f')
                    )
                )

            items.append(item_dict)
    
        if self.company_id.fel_pa_pac == 'efacturapty':
            return dict(Item=items)
        else:
            return dict(item=items) if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi'] else items
    
    def _fel_pa_prepare_vehicle_data(self, line):
        """
        Prepares the vehicle data for the invoice.
        """

        return dict(
            modalidadOperacionVenta=self.partner_id.fel_pa_recipient_type,
            chasis=line.product_id.fel_pa_chassis or '',
            codigoColor=line.product_id.fel_pa_color_code or '',
            colorNombre=line.product_id.fel_pa_color_name or '',
            potenciaMotor=line.product_id.fel_pa_engine_power or '',
            capacidadMotor=line.product_id.fel_pa_engine_capacity or '',
            pesoNeto=line.product_id.fel_pa_net_weight or '',
            pesoBruto=line.product_id.fel_pa_gross_weight or '',
            tipoCombustible=line.product_id.fel_pa_fuel_type or '',
            tipoCombustibleNoDef=line.product_id.fel_pa_fuel_type_nodef or '',
            numeroMotor=line.product_id.fel_pa_engine_number or '',
            capacidadTraccion=line.product_id.fel_pa_traction_capacity or '',
            distanciaEjes=line.product_id.fel_pa_axle_distance or '',
            anoModelo=line.product_id.fel_pa_model_year or '',
            anoFabricacion=line.product_id.fel_pa_manufacture_year or '',
            tipoPintura=line.product_id.fel_pa_paint_type or '',
            tipoPinturaNodef=line.product_id.fel_pa_paint_nodef or '',
            tipoVehiculo=line.product_id.fel_pa_vehicle_type or '',
            usoVehiculo=line.product_id.fel_pa_vehicle_usage or '',
            condicionVehiculo=line.product_id.fel_pa_vehicle_condition or '',
            capacidadPasajeros=line.product_id.fel_pa_passenger_capacity or '',
        )
    
    def _fel_pa_prepare_medicine_data(self, line):
        """
        Prepares the medicine data for the invoice.
        """

        medicine_data = []
        lot_quantities = line.lots_grouped_by_quantity()
        for lot_name, qty_done in lot_quantities.items():
            lot_data = dict(
                nroLote=lot_name,
                cantProductosLote=qty_done,
            )
            medicine_data.append(lot_data)
        return medicine_data
    
    def _fel_pa_prepare_totals_data(self):
        """
        Prepares the totals and subtotals of the invoice.
        """

        tax_totals_json = self.tax_totals
        group_taxs = [group for subtotal in tax_totals_json.get("groups_by_subtotal", {}).values() for group in subtotal]

        amount_untaxed = sum(group_tax['tax_group_base_amount'] for group_tax in group_taxs)
        total_itbms = sum(group_tax["tax_group_amount"] for group_tax in group_taxs)

        totalDescuento, listaDescBonificacion = self._fel_pa_prepare_desc_bonification_data()

        ignored_lines = self.invoice_line_ids.filtered(
                lambda x: x.display_type == "product" and x.price_total > 0 and x.product_id and x.product_id.fel_pa_exclude_from_invoice)
        ignored_amount = sum(ignored_lines.mapped('price_total'))

        nroItems = len(self.invoice_line_ids.filtered(
            lambda x: x.display_type == "product" and x.price_unit > 0 and x.quantity > 0
        )) - len(ignored_lines)

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            listaFormaPago = self._fel_pa_prepare_payment_methods_data(ignored_amount)

            result = {
                "totalPrecioNeto": format(amount_untaxed, '.2f'),
                "totalITBMS": format(total_itbms, '.2f'),
                "totalMontoGravado": format(total_itbms, '.2f'),
                "totalAcarreoCobrado": "",
                "valorSeguroCobrado": "",
                "totalFactura": format(self.amount_total - ignored_amount, '.2f'),
                "totalValorRecibido": format(self.amount_total - ignored_amount, '.2f'),
                "vuelto": "0.00",
                "tiempoPago": "1",
                "nroItems": nroItems,
                "totalTodosItems": format(self.amount_total - ignored_amount, '.2f'),
                "listaFormaPago": listaFormaPago
            }

            if totalDescuento and listaDescBonificacion:
                result["totalDescuento"] = format(totalDescuento, '.2f')
                result["listaDescBonificacion"] = listaDescBonificacion
                result["totalTodosItems"] = format(self.amount_total - ignored_amount + totalDescuento, '.2f')
            else:
                result["totalDescuento"] = "0.00"
        
        elif self.company_id.fel_pa_pac == 'digifact':

            result = dict(
                QtyItems=nroItems,
                GrandTotal=dict(
                    TotalBTaxes=format(amount_untaxed, '.2f'),
                    TotalWTaxes=format(total_itbms, '.2f'),
                    InvoiceTotal=format(self.amount_total - ignored_amount, '.2f'),
                )
            )

            if totalDescuento and listaDescBonificacion:
                result["TotalDiscounts"] = format(totalDescuento, '.2f')
                result["TotalDiscounts"] = {"Discount": listaDescBonificacion}
                result["GrandTotal"]["TotalBDiscounts"] = format(self.amount_total - ignored_amount + totalDescuento, '.2f')
                result["GrandTotal"]["TotalWDiscounts"] = format(self.amount_total - ignored_amount - totalDescuento, '.2f')

        return result
    
    def _fel_pa_prepare_desc_bonification_data(self):
        """
        Prepares the discount bonifications used in the invoice.
        """
        filtered_lines = self.invoice_line_ids.filtered(lambda x: x.display_type == "product" and x.price_total < 0)

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
        
            bonification_data = [
                dict(
                    descDescuento=re.sub(r'[^A-Za-z0-9 ]+', '', line.name),
                    montoDescuento=format(abs(round(line.quantity * line.price_unit)), '.2f')
                )
                for line in filtered_lines
            ]
            
            montoDescuento = sum(float(item['montoDescuento']) for item in bonification_data)

        elif self.company_id.fel_pa_pac == 'digifact':
                
                bonification_data = [
                    dict(
                        Description=re.sub(r'[^A-Za-z0-9 ]+', '', line.name),
                        Amount=format(abs(round(line.quantity * line.price_unit)), '.2f')
                    )
                    for line in filtered_lines
                ]
                
                montoDescuento = sum(float(item['Amount']) for item in bonification_data)

        return montoDescuento, bonification_data if self.company_id.fel_pa_pac == 'digifact' else dict(descuentoBonificacion=bonification_data) 
    
    def _fel_pa_prepare_payment_methods_data(self, ignored_amount):
        """
        Prepares the payment methods used in the invoice.
        """

        payment_methods = []

        if self.company_id.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            payment = dict(
                formaPagoFact=self.fel_pa_payment_method_id.fel_pa_payment_method if self.fel_pa_payment_method_id and self.fel_pa_payment_method_id.fel_pa_payment_method else "01",
                descFormaPago=self.fel_pa_payment_method_id.fel_pa_other_payment_description if self.fel_pa_payment_method_id and self.fel_pa_payment_method_id.fel_pa_payment_method == '99' else "",
                valorCuotaPagada=format(self.amount_total - ignored_amount, '.2f'),
            )

            payment_methods.append(payment)

            return dict(FormaPago=payment_methods) if self.company_id.fel_pa_pac == 'efacturapty' else dict(formaPago=payment_methods)
        elif self.company_id.fel_pa_pac == 'digifact':

            extra_payment = 0
            for reference in self.fel_pa_document_references_ids.filtered(lambda x: x.fel_pa_cufe):
                extra_payment += reference.amount_total
                
            payment = dict(
                Type=self.fel_pa_payment_method_id.fel_pa_payment_method if self.fel_pa_payment_method_id and self.fel_pa_payment_method_id.fel_pa_payment_method else "01",
                Amount=format(self.amount_total - ignored_amount + extra_payment, '.2f'),
            )

            return [payment]
    
    def fel_pa_cancel_wizard(self):
        """Opens the wizard to cancel the invoice."""
        action = self.env.ref('multipac_felpa.action_document_cancel_wizard').read()[0]
        action['context'] = {
            'motive': self.company_id.fel_pa_default_cancel_motive if self.company_id.fel_pa_default_cancel_motive else _('Cancellation by the user.'),
        }
        return action
    
    def button_cancel(self):
        """Cancels the invoice."""
        for move in self:
            if move.is_invoice():
                if not move.journal_id.fel_pa_active:
                    return super(AccountMove, self).button_cancel()

                if self.fel_pa_state == 'accepted':
                    self.cancel_fel_pa_move()
        return super(AccountMove, self).button_cancel()
    
    def cancel_fel_pa_move(self, extra_payload=None):
        """
        Cancels the invoice in the FEL.
        """
        payload = self._create_fel_pa_query_payload(type='cancel', extra_payload=extra_payload)

        result_fel, msg = self.env['fel_pa.tools.api_request'].create({
            'name': 'AnulacionDocumento: ' + str(self.id),
            'action': 'AnulacionDocumento',
            'payload': payload,
            'fel_pa_pac': self.company_id.fel_pa_pac,
            'url': self.company_id.fel_pa_pac_url,
            'company_id': self.company_id.id,
        }).make_online_request(raise_exception=False)

        if not result_fel:
            raise UserError(_("The invoice could not be canceled. Error: %s") % msg)
        else:
            if result_fel[0] == 'procesado':
                self.fel_pa_state = 'cancelled'
                self.message_post(body=_("The invoice has been canceled successfully by the PAC. PAC Message: %s") % result_fel[1])
            else:
                raise UserError(_("The invoice could not be canceled. Error: %s") % msg)
            
    def fel_pa_cancel(self, origin='accounting', motive=''):
        """Cancels the invoice in the FEL system."""
        for move in self:
            move_line_ids = move.sudo().mapped('line_ids')
            if move.is_invoice() and self.fel_pa_state == 'accepted':
                move.cancel_fel_pa_move(extra_payload=motive)

                pos_order = False
                
                if move.invoice_origin and origin == 'accounting':
                    is_pos_fel_installed = self.env['ir.module.module'].search([('state', '=', 'installed'), ('name', '=', 'pos_multipac_felpa')], limit=1)
                    if is_pos_fel_installed:
                        pos_order = self.env['pos.order'].sudo().search(
                            [('name','=',move.invoice_origin)], limit=1
                        )
                        if pos_order:
                            pos_order.fel_pa_cancel(cancel_invoice=False)

                reconcile_ids = []
                if move_line_ids:
                    reconcile_ids = move_line_ids.sudo().mapped('id')
                reconcile_lines = self.env['account.partial.reconcile'].sudo().search(
                    ['|', ('credit_move_id', 'in', reconcile_ids), ('debit_move_id', 'in', reconcile_ids)])
                
                payments = False
                if reconcile_lines:
                    payments = self.env['account.payment'].search(['|', ('invoice_line_ids.id', 'in', reconcile_lines.mapped(
                        'credit_move_id').ids), ('invoice_line_ids.id', 'in', reconcile_lines.mapped('debit_move_id').ids)])
                    reconcile_lines.sudo().unlink()

                if payments:
                    payment_ids = payments
                    if payment_ids.sudo().mapped('move_id').mapped('line_ids'):
                        payment_lines = payment_ids.sudo().mapped('move_id').mapped('line_ids')
                        reconcile_ids = payment_lines.sudo().mapped('id')

                        reconcile_lines = self.env['account.partial.reconcile'].sudo().search(
                            ['|', ('credit_move_id', 'in', reconcile_ids), ('debit_move_id', 'in', reconcile_ids)])
                        
                        if reconcile_lines:
                            reconcile_lines.sudo().unlink()
                        move.mapped('line_ids.analytic_line_ids').sudo().unlink()

                if payments:
                    payment_ids = payments
                    payment_ids.sudo().mapped('move_id').write(
                        {'state': 'draft', 'name': '/'})

                    payment_ids.sudo().mapped('move_id').mapped(
                        'line_ids').sudo().write({'parent_state': 'draft'})
                    payment_ids.sudo().mapped('move_id').mapped('line_ids').sudo().unlink()
                    payment_ids.sudo().write({'state': 'cancel'})

                move_line_ids.sudo().write({'parent_state': 'draft'})
                move.sudo().write({'state': 'draft'})
                self.sudo().write({'state': 'cancel'})
    
    # Template Methods for the FEL
    def _fel_pa_invoice_name(self):
        """
        Returns the name of the invoice.
        """
        document_types = {
            '01': _("Internal bill"),
            '02': _("Import bill"),
            '03': _("Export bill"),
            '04': _("Credit note referring to a E-bill"),
            '05': _("Debit note referring to a E-bill"),
            '06': _("Generic credit note"),
            '07': _("Generic debit note"),
            '08': _("Free Zone bill"),
            '09': _("Reimbursement"),
        }

        return document_types.get(self.fel_pa_document_type_id.document_type, _("Internal bill"))
    
    def _get_fel_pa_invoice_date(self):
        """Get the FEL invoice date."""
        self.ensure_one()
        lang = self.env.user.lang
        lang_obj = self.env['res.lang']
        ids = lang_obj.search([("code", "=", lang or 'en_US')])
        if self.invoice_date:
            timestamp = datetime.strptime(str(self.invoice_date), tools.DEFAULT_SERVER_DATE_FORMAT)
            ts = fields.Datetime.context_timestamp(self, timestamp)
            n_date = ts.strftime(ids.date_format)
            if self:
                return n_date
        return False
    
    def _get_fel_pa_invoice_due_date(self):
        """Get the FEL invoice due date."""
        self.ensure_one()
        lang = self.env.user.lang
        lang_obj = self.env['res.lang']
        ids = lang_obj.search([("code", "=", lang or 'en_US')])
        if self.invoice_date_due:
            timestamp = datetime.strptime(str(self.invoice_date_due), tools.DEFAULT_SERVER_DATE_FORMAT)
            ts = fields.Datetime.context_timestamp(self, timestamp)
            n_date = ts.strftime(ids.date_format)
            if self:
                return n_date
        return False
    
    def _get_fel_pa_street(self, partner):
        """Get the FEL street."""
        self.ensure_one()
        res = {}
        address = ''
        if partner.street:
            address = "%s" % (partner.street)
        if partner.street2:
            address += ", %s" % (partner.street2)
        if address:
            return address
        return False
    
    def _get_fel_pa_full_address_details(self, partner):
        """Get the FEL address details."""
        self.ensure_one()
        res = {}
        address = ''
        if partner.street:
            address = "%s" % (partner.street)
        if partner.street2:
            address += ", %s" % (partner.street2)
        if partner.city:
            address = "%s" % (partner.city)
        if partner.state_id.name:
            address += ", %s" % (partner.state_id.name)
        if partner.fel_pa_county_id:
            address += ", %s" % (partner.fel_pa_county_id.name)
        if partner.city_id:
            address += ", %s" % (partner.city_id.name)
        if partner.zip:
            address += ", %s" % (partner.zip)
        if partner.country_id.name:
            address += ", %s" % (partner.country_id.name)
        if address:
            return address
        return False
    
    def _get_fel_pa_address_details(self, partner):
        """Get the FEL address details."""
        self.ensure_one()
        res = {}
        address = ''
        if partner.city:
            address = "%s" % (partner.city)
        if partner.state_id.name:
            address += ", %s" % (partner.state_id.name)
        if partner.fel_pa_county_id:
            address += ", %s" % (partner.fel_pa_county_id.name)
        if partner.city_id:
            address += ", %s" % (partner.city_id.name)
        if partner.zip:
            address += ", %s" % (partner.zip)
        if partner.country_id.name:
            address += ", %s" % (partner.country_id.name)
        if address:
            return address
        return False
    
    def _get_fel_pa_origin_date(self, origin):
        """Get the FEL origin date."""
        self.ensure_one()
        try:
            if self.move_type in ('in_invoice', 'in_refund'):
                sale_obj = self.env['purchase.order']
            else:
                sale_obj = self.env['sale.order']
            lang = self.env.user.lang
            lang_obj = self.env['res.lang']
            ids = lang_obj.search([("code", "=", lang or 'en_US')])
            sale = sale_obj.search([('name', '=', origin)])
            if sale:
                timestamp = datetime.strptime(str(sale.date_order), tools.DEFAULT_SERVER_DATETIME_FORMAT)
                ts = fields.Datetime.context_timestamp(self, timestamp)
                n_date = ts.strftime(ids.date_format)
                if sale:
                    return n_date
            sale_obj = self.env['pos.order']
            sale = sale_obj.search([('name', '=', origin)])
            if sale:
                timestamp = datetime.strptime(str(sale.date_order), tools.DEFAULT_SERVER_DATETIME_FORMAT)
                ts = fields.Datetime.context_timestamp(self, timestamp)
                n_date = ts.strftime(ids.date_format)
                if sale:
                    return n_date
        except:
            return False
        return False
    
    def _get_fel_pa_partner_vat(self, partner):
        """Get the FEL partner VAT."""
        self.ensure_one()
        vat_label = partner.l10n_latam_identification_type_id.name
        vat = partner.vat
        dv = partner.fel_pa_dv
        return vat_label, vat, dv
    
    def _get_fel_pa_tax_amount(self, amount, payment=None):
        """Get the FEL tax amount."""
        self.ensure_one()
        res = {}
        currency = self.currency_id or self.company_id.currency_id
        res = formatLang(self.env, amount, currency_obj=currency)
        if payment != None:
            if self.move_type in ('out_invoice', 'in_refund'):
                amount = sum([p.amount for p in payment.matched_debit_ids if p.debit_move_id in self.move_id.line_ids])
                amount_currency = sum([p.amount_currency for p in payment.matched_debit_ids if p.debit_move_id in self.move_id.line_ids])
            elif self.move_type in ('in_invoice', 'out_refund'):
                amount = sum([p.amount for p in payment.matched_credit_ids if p.credit_move_id in self.move_id.line_ids])
                amount_currency = sum([p.amount_currency for p in payment.matched_credit_ids if p.credit_move_id in self.move_id.line_ids])
            if payment.currency_id and payment.currency_id == self.currency_id:
                amount_to_show = amount_currency
            else:
                amount_to_show = payment.company_id.currency_id.with_context(date=payment.date).compute(amount, self.currency_id)
            if float_is_zero(amount_to_show, precision_rounding=self.currency_id.rounding):
                return res
            res = formatLang(self.env, amount_to_show, currency_obj=currency)
        return res
    

    fel_pa_report_template_id1 = fields.Many2one('ir.actions.report', string="Invoice Template 1", compute='_default_fel_pa_report_template1', domain=[('model', '=', 'account.move')])
    fel_pa_report_template_id = fields.Many2one('ir.actions.report', string="Invoice Template", domain=[('model', '=', 'account.move')])

    @api.onchange('partner_id', 'company_id')
    def _onchange_fel_partner_id(self):
        """Onchange the FEL partner ID."""
        result = super(AccountMove, self)._onchange_partner_id()
        if self.partner_id and self.partner_id.fel_pa_report_template_id:
            self.fel_pa_report_template_id = self.partner_id.fel_pa_report_template_id.id or False
        return result

    @api.model
    def _default_fel_pa_report_template(self):
        """Get the default report template."""
        report_obj = self.env['ir.actions.report']
        report_id = report_obj.search([('model', '=', 'account.move'), ('report_name', '=', 'multipac_felpa.report_invoice_template_custom')])
        if report_id:
            report_id = report_id[0]
        else:
            report_id = report_obj.search([('model', '=', 'account.move')])[0]
        return report_id

    @api.depends('partner_id')
    def _default_fel_pa_report_template1(self):
        """Get the default FEL report template."""
        for rec in self:
            report_obj = rec.env['ir.actions.report']
            report_id = report_obj.search([('model', '=', 'account.move'), ('report_name', '=', 'multipac_felpa.report_invoice_template_custom')], limit=1)
            if not report_id:
                report_id = report_obj.search([('model', '=', 'account.move')], limit=1)
            if rec.fel_pa_report_template_id and report_id and rec.fel_pa_report_template_id.id < report_id.id:
                rec.fel_pa_report_template_id = report_id
            rec.fel_pa_report_template_id1 = report_id

    def invoice_print(self):
        """ Print the invoice and mark it as sent, so that we can see more
            easily the next step of the workflow
        """
        self.ensure_one()
        self.sent = True
        res = super(AccountMove, self).invoice_print()
        if self.fel_pa_report_template_id or self.partner_id and self.partner_id.fel_pa_report_template_id or self.company_id and self.company_id.fel_pa_report_template_id:
            report_id = self.fel_pa_report_template_id and self.fel_pa_report_template_id or self.partner_id and self.partner_id.fel_pa_report_template_id or self.company_id and self.company_id.fel_pa_report_template_id
            if report_id:
                report = report_id.report_action(self)
                return report
            else:
                return res
        return res
    
    def _get_name_invoice_report(self):
        self.ensure_one()
        if self.fel_pa_state == 'accepted' and self.fel_pa_cufe:
            if self.company_id.fel_pa_use_as_default_template:
                return 'multipac_felpa.fel_pa_report_invoice'
            else:
                return 'multipac_felpa.fel_pa_report_invoice_document'
        return super()._get_name_invoice_report()


def __convertNumber(n):
    output = ''

    if(n == '100'):
        output = "CIEN"
    elif(n[0] != '0'):
        output = CENTENAS[int(n[0])-1]

    k = int(n[1:])
    if(k <= 20):
        output += UNIDADES[k]
    else:
        if((k > 30) & (n[2] != '0')):
            output += '%sY %s' % (DECENAS[int(n[1])-2], UNIDADES[int(n[2])])
        else:
            output += '%s%s' % (DECENAS[int(n[1])-2], UNIDADES[int(n[2])])

    return output

def number2text(number_in, currency_name):
    converted = ''
    if type(number_in) != 'str':
        number = str(number_in)
    else:
        number = number_in

    number_str = number
    number_str = number_str.replace(',', '')
    try:
        number_int, number_dec = number_str.split(".")
    except ValueError:
        number_int = number_str
        number_dec = ""

    number_str = number_int.zfill(9)
    millones = number_str[:3]
    miles = number_str[3:6]
    cientos = number_str[6:]

    if(millones):
        if(millones == '001'):
            converted += 'UN MILLON '
        elif(int(millones) > 0):
            converted += '%sMILLONES ' % __convertNumber(millones)

    if(miles):
        if(miles == '001'):
            converted += 'MIL '
        elif(int(miles) > 0):
            converted += '%sMIL ' % __convertNumber(miles)
    if(cientos):
        if(cientos == '001'):
            converted += 'UN '
        elif(int(cientos) > 0):
            converted += '%s ' % __convertNumber(cientos)

    if number_dec == "":
        number_dec = "00"
    if (len(number_dec) < 2):
        number_dec += '0'

    converted += currency_name
    converted += ' CON ' + number_dec + "/100."
    return converted.title()

UNIDADES = (
    '',
    'UNO ',
    'DOS ',
    'TRES ',
    'CUATRO ',
    'CINCO ',
    'SEIS ',
    'SIETE ',
    'OCHO ',
    'NUEVE ',
    'DIEZ ',
    'ONCE ',
    'DOCE ',
    'TRECE ',
    'CATORCE ',
    'QUINCE ',
    'DIECISEIS ',
    'DIECISIETE ',
    'DIECIOCHO ',
    'DIECINUEVE ',
    'VEINTE '
)
DECENAS = (
    'VEINTI',
    'TREINTA ',
    'CUARENTA ',
    'CINCUENTA ',
    'SESENTA ',
    'SETENTA ',
    'OCHENTA ',
    'NOVENTA ',
    'CIEN '
)
CENTENAS = (
    'CIENTO ',
    'DOSCIENTOS ',
    'TRESCIENTOS ',
    'CUATROCIENTOS ',
    'QUINIENTOS ',
    'SEISCIENTOS ',
    'SETECIENTOS ',
    'OCHOCIENTOS ',
    'NOVECIENTOS '
)
