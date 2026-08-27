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

from odoo import _, api, fields, models, _
from odoo.exceptions import UserError
import io
import os
import base64
import tempfile
import logging
from contextlib import closing
from PyPDF2 import PdfFileWriter, PdfFileReader
from PIL import Image 
from odoo.tools.misc import find_in_path
from collections import OrderedDict
from odoo.tools import config

_logger = logging.getLogger(__name__)


def _get_wkhtmltopdf_bin():
    return find_in_path('wkhtmltopdf')


class ReportAction(models.Model):
    _inherit = "ir.actions.report"

    
    def merge_extra_content_pdf(self, res_ids, pdf_content_stream):
        if not res_ids:
            return pdf_content_stream

        content_obj = self.env['fel_pa.tools.report_extra_content']
        res_id = self.env[self.model].browse(res_ids)
        
        # Only append extra content for sales invoices of specific companies
        if self.model != 'account.move' or res_id.move_type != 'out_invoice' or res_id.company_id.id not in [7, 11]:
            return pdf_content_stream

        extra_content_id = content_obj.search([('company_id', '=', res_id.company_id.id)])
        custom_documents = []
        if extra_content_id and extra_content_id.append_extra_content:
            raw_main = pdf_content_stream.read()
            pdf_content_stream.seek(0)
            if b'CONDICIONES GENERALES' in raw_main or b'CONDICIONES LEGALES' in raw_main or b'CONDICIONES DE VENTA' in raw_main:
                return pdf_content_stream
            main_pdf_fd, main_pdf_path = tempfile.mkstemp(suffix='.pdf', prefix='report.tmp.custom.')
            custom_documents.append(main_pdf_path)
            with open(main_pdf_fd, 'wb') as pcd:
                pcd.write(raw_main)
            pdf_custom_fd, pdf_custom_path = tempfile.mkstemp(suffix='.pdf', prefix='report.tmp.custom.')
            custom_documents.append(pdf_custom_path)
            with open(pdf_custom_fd, 'wb') as pcd:
                pcd.write(base64.decodebytes(extra_content_id.append_extra_content))

        if custom_documents:
            writer = PdfFileWriter()
            streams = []
            merged_file_fd, merged_file_path = tempfile.mkstemp(suffix='.pdf', prefix='report.merged.tmp.')
            try:
                for document in custom_documents:
                    pdfreport = open(document, 'rb')
                    streams.append(pdfreport)
                    reader = PdfFileReader(pdfreport)
                    for page in range(0, reader.getNumPages()):
                        writer.addPage(reader.getPage(page))

                with closing(os.fdopen(merged_file_fd, 'wb')) as merged_file:
                    writer.write(merged_file)
            finally:
                for stream in streams:
                    try:
                        stream.close()
                    except Exception:
                        pass
            custom_documents.append(merged_file_path)

            with open(merged_file_path, 'rb') as pdf_document:
                pdf_content_stream = pdf_document.read()
            pdf_content_stream = io.BytesIO(pdf_content_stream)

            for temporary_file in custom_documents:
                try:
                    os.unlink(temporary_file)
                except (OSError, IOError):
                    _logger.error(
                        'Error when trying to remove file %s' % temporary_file)

        return pdf_content_stream

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):

        if not data:
            data = {}
        data.setdefault('report_type', 'pdf')

        report_sudo = self._get_report(report_ref)
        collected_streams = OrderedDict()

        if res_ids:
            records = self.env[report_sudo.model].browse(res_ids)
            for record in records:
                stream = None
                attachment = None
                if report_sudo.attachment:
                    attachment = report_sudo.retrieve_attachment(record)

                    if attachment and report_sudo.attachment_use:
                        stream = io.BytesIO(attachment.raw)
                        if attachment.mimetype.startswith('image'):
                            img = Image.open(stream)
                            new_stream = io.BytesIO()
                            img.convert("RGB").save(new_stream, format="pdf")
                            stream.close()
                            stream = new_stream

                collected_streams[record.id] = {
                    'stream': stream,
                    'attachment': attachment,
                }

        res_ids_wo_stream = [res_id for res_id, stream_data in collected_streams.items() if not stream_data['stream']]
        is_whtmltopdf_needed = not res_ids or res_ids_wo_stream

        if is_whtmltopdf_needed:

            if self.get_wkhtmltopdf_state() == 'install':
                raise UserError(_("Unable to find Wkhtmltopdf on this system. The PDF can not be created."))
            
            additional_context = {'debug': False}
            if not config['test_enable']:
                additional_context['commit_assetsbundle'] = True

            html = self.with_context(**additional_context)._render_qweb_html(report_ref, res_ids_wo_stream, data=data)[0]

            bodies, html_ids, header, footer, specific_paperformat_args = self.with_context(**additional_context)._prepare_html(html, report_model=report_sudo.model)

            if report_sudo.attachment and set(res_ids_wo_stream) != set(html_ids):
                raise UserError(_(
                    "The report's template %r is wrong, please contact your administrator. \n\n"
                    "Can not separate file to save as attachment because the report's template does not contains the"
                    " attributes 'data-oe-model' and 'data-oe-id' on the div with 'article' classname.",
                    self.name,
                ))
            pdf_content = self._run_wkhtmltopdf(
                bodies,
                report_ref=report_ref,
                header=header,
                footer=footer,
                landscape=self._context.get('landscape'),
                specific_paperformat_args=specific_paperformat_args,
                set_viewport_size=self._context.get('set_viewport_size'),
            )
            pdf_content_stream = io.BytesIO(pdf_content)

            if not res_ids:
                return {
                    False: {
                        'stream': pdf_content_stream,
                        'attachment': None,
                    }
                }
            content_obj = self.env['fel_pa.tools.report_extra_content']
            model_id = self.env['ir.model'].sudo().search([('model', '=', report_sudo.model)])
            custom_documents = []
            if not report_sudo.attachment:
                if res_ids:
                    main_pdf_fd, main_pdf_path = tempfile.mkstemp(suffix='.pdf', prefix='report.tmp.custom.')
                    custom_documents.append(main_pdf_path)
                    with open(main_pdf_fd, 'wb') as pcd:
                        pcd.write(pdf_content_stream.read())

                    for res in self.env[report_sudo.model].browse(res_ids):
                        extra_content_id = None
                        if report_sudo.model == 'account.move' and res.move_type == 'out_invoice' and res.company_id.id in [7, 11]:
                            extra_content_id = content_obj.search([('company_id', '=', res.company_id.id)])
                        if extra_content_id and extra_content_id.append_extra_content:
                            pdf_custom_fd, pdf_custom_path = tempfile.mkstemp(suffix='.pdf', prefix='report.tmp.custom.')
                            custom_documents.append(pdf_custom_path)
                            with open(pdf_custom_fd, 'wb') as pcd:
                                pcd.write(base64.decodebytes(extra_content_id.append_extra_content))
                    if custom_documents:
                        writer = PdfFileWriter()
                        st = []
                        merged_file_fd, merged_file_path = tempfile.mkstemp(
                            suffix='.pdf', prefix='report.merged.tmp.')
                        try:
                            for document in custom_documents:
                                pdfreport = open(document, 'rb')
                                st.append(pdfreport)
                                reader = PdfFileReader(pdfreport)
                                for page in range(0, reader.getNumPages()):
                                    writer.addPage(reader.getPage(page))

                            with closing(os.fdopen(merged_file_fd, 'wb')) as merged_file:
                                writer.write(merged_file)
                        finally:
                            for stt in st:
                                try:
                                    stt.close()
                                except Exception:
                                    pass
                        custom_documents.append(merged_file_path)
                        with open(merged_file_path, 'rb') as pdf_document:
                            pdf_content_stream = io.BytesIO(
                                pdf_document.read())
                collected_streams[res_ids_wo_stream[0]]['stream'] = pdf_content_stream
                return collected_streams

            if len(res_ids_wo_stream) == 1:
                pdf_content_stream = report_sudo.merge_extra_content_pdf(res_ids[0], pdf_content_stream)
                collected_streams[res_ids_wo_stream[0]]['stream'] = pdf_content_stream
                return collected_streams

            html_ids_wo_none = [x for x in html_ids if x]
            if len(res_ids_wo_stream) > 1 and set(res_ids_wo_stream) == set(html_ids_wo_none):
                reader = PdfFileReader(pdf_content_stream)
                root = reader.trailer['/Root']
                has_valid_outlines = '/Outlines' in root and '/First' in root['/Outlines']
                if not has_valid_outlines:
                    return {False: {
                        'report_action': self,
                        'stream': pdf_content_stream,
                        'attachment': None,
                    }}
                outlines_pages = []
                node = root['/Outlines']['/First']
                while True:
                    outlines_pages.append(root['/Dests'][node['/Dest']][0])
                    if '/Next' not in node:
                        break
                    node = node['/Next']
                outlines_pages = sorted(set(outlines_pages))
                has_same_number_of_outlines = len(outlines_pages) == len(res_ids)

                has_top_level_heading = outlines_pages[0] == 0
                if has_same_number_of_outlines and has_top_level_heading:
                    for i, num in enumerate(outlines_pages):
                        to = outlines_pages[i + 1] if i + 1 < len(outlines_pages) else reader.numPages
                        attachment_writer = PdfFileWriter()
                        for j in range(num, to):
                            attachment_writer.addPage(reader.getPage(j))

                            if model_id and res_ids[i]:
                                res_id = self.env[report_sudo.model].browse(res_ids[i])
                                extra_content_id = None
                                if report_sudo.model == 'account.move' and res_id.move_type == 'out_invoice' and res_id.company_id.id in [7, 11]:
                                    extra_content_id = content_obj.search([('company_id', '=', res_id.company_id.id)])
                                custom_documents = []
                                if extra_content_id and extra_content_id.append_extra_content:
                                    st = []
                                    pdf_custom_fd, pdf_custom_path = tempfile.mkstemp(suffix='.pdf', prefix='report.tmp.custom.')
                                    custom_documents.append(pdf_custom_path)
                                    with open(pdf_custom_fd, 'wb') as pcd:
                                        pcd.write(base64.decodebytes(extra_content_id.append_extra_content))

                                    ext_pdfreport = open(pdf_custom_path, 'rb')
                                    st.append(ext_pdfreport)
                                    ext_reader = PdfFileReader(ext_pdfreport)
                                    for page in range(0, ext_reader.getNumPages()):
                                        attachment_writer.addPage(ext_reader.getPage(page))

                        stream = io.BytesIO()
                        attachment_writer.write(stream)
                        collected_streams[res_ids[i]]['stream'] = stream

                    return collected_streams

            collected_streams[False] = {'stream': pdf_content_stream, 'attachment': None}

        for res_id, stream_data in collected_streams.items():
            if res_id and stream_data.get('stream') and not is_whtmltopdf_needed:
                stream_data['stream'] = report_sudo.merge_extra_content_pdf(res_id, stream_data['stream'])

        return collected_streams