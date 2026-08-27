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

from odoo import fields, models, _, api
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
from odoo.exceptions import ValidationError
import zeep
from zeep.exceptions import Fault
import os
import subprocess
import re
import json
import datetime
import requests
import ast
import logging
logger = logging.getLogger(__name__)

class FelPAAPIRequest(models.Model):
    _name = "fel_pa.tools.api_request"
    _description = "API Request"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    name = fields.Char(string="Name",  required=True, readonly=True)

    response_text = fields.Text(string="Response Text", readonly=True)
    response_message = fields.Text(string="Response Message", readonly=True)
    response_code = fields.Integer(string="Response Code", readonly=True)
    response_result = fields.Text(string="Response Result", readonly=True)

    action = fields.Char(string="Action", readonly=True)
    payload = fields.Char(string="Payload", readonly=True)

    fel_pa_pac = fields.Selection([('the_factory_hka', 'THE FACTORY HKA'),('ebi', 'EBI'),('digifact','Digifact'),('efacturapty','eFacturapty')], string="PAC", readonly=True)
    url = fields.Char(string="URL", readonly=True)

    state = fields.Selection([('draft', 'Draft'), ('in_queue', 'In Queue'), ('sent', 'Sent'), ('done', 'Done'), ('error', 'Error')], string="State", default='draft', tracking=True, readonly=True)
    offline_state = fields.Selection([('in_queue', 'In Queue'), ('done', 'Done'), ('error', 'Error')], string="Offline State", tracking=True, readonly=True)
    offline_number = fields.Char(string="Offline Number", readonly=True)

    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)

    def make_online_request(self, raise_exception=False):
        """Make an online request to the PAC."""
        self.ensure_one()
        self.state = 'in_queue'
        result = False

        logger.info(f"Action: {self.action}")
        logger.info(f"Payload: {self.payload}")
        logger.info(f"URL: {self.url}")
        
        if self.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            client = zeep.Client(wsdl=self.url)
            
            payload_dict = eval(self.payload)
            action_method = getattr(client.service, self.action, None)
            if not action_method:
                msg = _(f"El método SOAP '{self.action}' no existe en el servicio.")
                logger.error(msg)
                self.state = 'error'
                if raise_exception:
                    raise ValidationError(msg)
                return False, msg
            
            response = action_method(**payload_dict)
            self.state = 'sent'
            
            response_json = zeep.helpers.serialize_object(response)
            
            code = response_json.get('codigo', '500')
            msg = response_json.get('mensaje', 'Error desconocido')
            self.response_text = response_json
            self.response_message = msg
            self.response_code = code
            
            if code == '200':
                self.state = 'done'
                
                if self.action == 'ConsultarRucDV':
                    info_ruc = response_json.get('infoRuc', {})
                    result = (
                        info_ruc.get('ruc', ''),
                        info_ruc.get('razonSocial', ''),
                        info_ruc.get('dv', '').zfill(2),
                        info_ruc.get('afiliadoFE', ''),
                        info_ruc.get('tipoRuc', '')
                    )
                
                if self.action == 'Enviar':
                    result = (
                        response_json.get('cufe', ''),
                        response_json.get('qr', ''),
                        response_json.get('fechaRecepcionDGI', ''),
                        response_json.get('nroProtocoloAutorizacion', ''),
                    )

                if self.action in ['DescargaPDF','DescargaXML']:
                    result = (
                        response_json.get('documento', ''),
                    )
                
                if self.action == 'FoliosRestantes':
                    result = (
                        response_json.get('licencia', 'N/A'),
                        response_json.get('fechaLicencia', 'N/A'),
                        response_json.get('ciclo', 'N/A'),
                        response_json.get('fechaCiclo', 'N/A'),
                        response_json.get('foliosTotalesCiclo', 'N/A'),
                        response_json.get('foliosUtilizadosCiclo', 'N/A'),
                        response_json.get('foliosDisponibleCiclo', 'N/A'),
                        response_json.get('foliosTotales', 'N/A'),
                        response_json.get('foliosTotalesDisponibles', 'N/A'),
                        response_json.get('resultado', 'N/A')
                    )

                if self.action == 'EstadoDocumento':
                    result = (
                        response_json.get('cufe', 'N/A'),
                        response_json.get('fechaEmisionDocumento', 'N/A'),
                        response_json.get('fechaRecepcionDocumento', 'N/A'),
                        response_json.get('estatusDocumento', 'N/A'),
                        response_json.get('mensajeDocumento', 'N/A'),
                        response_json.get('resultado', 'N/A')
                    )

                if self.action == 'EnvioCorreo':
                    result = (
                        response_json.get('resultado', 'N/A'),
                        response_json.get('mensaje', 'N/A')
                    )

                if self.action == 'RastreoCorreo':
                    tracking_list = response_json.get('listaRastreo', {}).get('listTracking', [])
                    result = [
                        {
                            'correo': item.get('correo', 'N/A'),
                            'creado_en': item.get('creado_en', 'N/A'),
                            'estado': item.get('estado', 'N/A'),
                            'messageId': item.get('messageId', 'N/A')
                        }
                        for item in tracking_list
                    ]
                
                if self.action == 'AnulacionDocumento':
                    result = (
                        response_json.get('resultado', 'N/A'),
                        response_json.get('mensaje', 'N/A')
                    )

                self.response_result = ', '.join(json.dumps(r) for r in result)
                return result, msg
            else:
                logger.error(_(f"Error code '{code}' returned from the PAC. Message: '{msg}'"))
                self.state = 'error'
                if raise_exception:
                    raise ValidationError(_(f"Error code '{code}' returned from the PAC. Message: '{msg}'"))
                return False, msg
            
        elif self.fel_pa_pac == 'digifact':

            payload = eval(self.payload)
            
            # Default header
            headers = {
                "Content-Type": "application/json",
            }

            if self.action != 'GenerarToken':
                # Generate token if expired
                if datetime.datetime.now() > self.company_id.fel_pa_pac_company_token_expiry:
                    token = self.company_id.fel_pa_generate_company_token()
                else:
                    token = self.company_id.fel_pa_pac_company_token

                if token:
                    headers["Authorization"] = token

            # Setup data based on action
            data = {}
            if self.action in ['FoliosRestantes', 'EnvioCorreo', 'RastreoCorreo']:
                raise ValidationError(_("Action not supported by Digifact."))
            elif self.action == 'Enviar':
                data = {
                    "TAXID": self.company_id.vat,
                    "FORMAT": 'XML|HTML|PDF',
                    "USERNAME": self.company_id.fel_pa_pac_company_username,
                }
                method = requests.post
            elif self.action == 'GenerarToken':
                data = json.dumps({
                    "Username": payload.get('Username', ''),
                    "Password": payload.get('Password', ''),
                })
                method = requests.post
            elif self.action == 'ConsultarRucDV':
                data = {
                    "RUC": payload.get('RUC', ''),
                    "TIPO": payload.get('TIPO', ''),
                }
                method = requests.get
            elif self.action in ['DescargaPDF', 'DescargaXML']:
                data = {
                    "CUFE": payload.get('CUFE', ''),
                    "RUC": self.company_id.vat,
                    "FORMAT": payload.get('FORMAT', 'PDF'),
                    "USERNAME": self.company_id.fel_pa_pac_company_username,
                }
                method = requests.get
            elif self.action == 'EstadoDocumento':
                data2 = 'STAXID|' + self.company_id.vat + '|NUMFACT|' + payload.get('NUMBER', '') + '|TIPODOC|' + payload.get('TIPODOC', '')
                data = {
                    "TRANSACTION": "SHARED_INFO_EFACE",
                    "RUC": self.company_id.vat,
                    "DATA1": "SHARED_GETDTEINFO_BYNUMDOC",
                    "DATA2": data2,
                    "USERNAME": self.company_id.fel_pa_pac_company_username,
                }
                method = requests.get

            try:
                # Make the request
                if method == requests.get:
                    response = method(self.url, params=data, headers=headers)
                else:
                    if self.action == 'GenerarToken':
                        response = method(self.url, headers=headers, data=data)
                    else:
                        response = method(self.url, params=data, headers=headers, data=json.dumps(payload))

                self.state = 'sent'

                response_json = response.json()
                if response.status_code == 200:
                    msg = ''
                    self.state = 'done'
                    
                    # Parsing based on the action
                    if self.action == 'Enviar':
                        msg = response_json.get('message', '')
                        if response_json.get('code', '') == 1:
                            result = (
                                response_json.get('authNumber', ''),
                                response_json.get('url', ''),
                                response_json.get('issuedTimeStamp', ''),
                                response_json.get('additionalInfo', {}).get('ProtocoloAutorizacion', ''),
                            )
                        else:
                            self.state = 'error'
                            msg += ' ' + response_json.get('description', '') + ' ' + str(response_json.get('infoDetails', ''))
                    elif self.action == 'GenerarToken':
                        result = (
                            response_json.get('Token', ''),
                            response_json.get('expira_en', ''),
                        )
                    elif self.action == 'ConsultarRucDV':
                        result = (
                            response_json.get('Ruc', ''),
                            response_json.get('Nombre', ''),
                            response_json.get('DV', '').zfill(2),
                            response_json.get('Tipo', ''),
                            response_json.get('TipoRuc', ''),
                        )
                    elif self.action == 'DescargaPDF':
                        response_data = response_json.get('RESPONSE', [])
                        if isinstance(response_data, list) and response_data:
                            result = (response_data[0].get('ResponseData3', ''),)
                    elif self.action == 'DescargaXML':
                        response_data = response_json.get('RESPONSE', [])
                        if isinstance(response_data, list) and response_data:
                            result = (response_data[0].get('ResponseData1', ''),)
                    elif self.action == 'EstadoDocumento':
                        response_data = response_json.get('RESPONSE', [])
                        result = (
                            response_data[0].get('CUFE', ''),
                            response_data[0].get('FECHA_DE_EMISION', ''),
                            response_data[0].get('FECHA_DE_CERTIFICACION', ''),
                            response_data[0].get('ESTADO_DGI', ''),
                            '',
                            '',
                        )
                    if result:
                        return result, msg
                    else:
                        if raise_exception:
                            raise ValidationError(f"Error code '{response_json.get('code', '')}' returned from PAC. Message: '{msg}'")
                        return False, msg

                else:
                    # Error handling
                    error_msg = response.json().get('message', 'Unknown error')
                    self.state = 'error'
                    if raise_exception:
                        raise ValidationError(f"Error code '{response.status_code}' returned from PAC. Message: '{error_msg}'")
                    return False, error_msg

            except Exception as e:
                self.state = 'error'
                if raise_exception:
                    raise ValidationError(f"Error returned from PAC. Message: '{e}'")
                return False, str(e)
            

    @api.model
    def make_offline_request(self, raise_exception=False):
        """Make an offline request to the PAC."""
        self.ensure_one()
        self.state = 'in_queue'
        self.offline_state = 'in_queue'
        result = False

        if self.action != 'Enviar':
            raise ValidationError(_("Offline request is only available for sending documents."))
        
        if self.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:

            if not self.company_id.fel_pa_offline_utility_path:
                raise ValidationError(_("Offline utility path is not set."))
            
            if not self.company_id.fel_pa_offline_pending_path:
                raise ValidationError(_("Pending path is not set."))
            
            payload_dict = ast.literal_eval(self.payload)

            self.state = 'sent'

            document = payload_dict.get('documento', {})
            transaction_data = document.get('datosTransaccion')

            L01 = (
                f"L01|"
                f"{transaction_data.get('tipoEmision')}|"
                f"{transaction_data.get('tipoDocumento')}|"
                f"{transaction_data.get('numeroDocumentoFiscal')}|"
                f"{transaction_data.get('puntoFacturacionFiscal')}|"
                f"{document.get('codigoSucursalEmisor')}|"
                f"{transaction_data.get('fechaEmision')}|"
                f"{transaction_data.get('naturalezaOperacion')}|"
                f"{transaction_data.get('tipoOperacion')}|"
                f"{transaction_data.get('destinoOperacion')}|"
                f"{transaction_data.get('formatoCAFE')}|"
                f"{transaction_data.get('entregaCAFE')}|"
                f"{transaction_data.get('envioContenedor')}|"
                f"{transaction_data.get('procesoGeneracion')}|"
                f"{transaction_data.get('informacionInteres', '').replace('|', ' / ')}|"
                f"{transaction_data.get('tipoVenta')}||"
                f"{transaction_data.get('fechaInicioContingencia', '')}|"
                f"{transaction_data.get('motivoContingencia', '')}|"
                f"{document.get('tipoSucursal', '')}|"
            )

            customer = transaction_data.get('cliente')

            L02 = (
                f"\nL02|"
                f"{customer.get('tipoClienteFE', '')}|"
                f"{customer.get('tipoContribuyente', '')}|"
                f"{'00-00-00'}|"
                f"{'00'}|"
                f"{customer.get('razonSocial', '')}|"
                f"{customer.get('direccion', '')}|"
                f"{customer.get('codigoUbicacion', '')}|"
                f"{customer.get('corregimiento', '')}|"
                f"{customer.get('distrito', '')}|"
                f"{customer.get('provincia', '')}|"
                f"{customer.get('telefono1') or '000-0000'}|||"
                f"{customer.get('correoElectronico1', '')}|"
                f"{customer.get('correoElectronico2', '')}|"
                f"{customer.get('correoElectronico3', '')}|"
                f"{customer.get('pais', '')}|"
                f"{customer.get('paisExtranjero', '')}|"
                f"{customer.get('tipoIdentificacion', '')}|"
                f"{customer.get('nroIdentificacionExtranjero', '')}|"
                f"{customer.get('paisExtranjero', '')}|"
            )

            fiscal_references = document.get('listaDocsFiscalReferenciados', '')

            L04 = ''
            if fiscal_references:
                L04 = (
                    f"\nL04|"
                    f"{fiscal_references.get('fechaEmisionDocFiscalReferenciado', '')}|"
                    f"{fiscal_references.get('cufeFEReferenciada', '')}|||"
                )

            L06 = ""
            for item in document.get('listaItems', {}).get('item', []):
                L06 += (
                    f"\nL06|"
                    f"{item.get('codigoProducto') or '1'}|"
                    f"{item.get('descripcion', '')}|"
                    f"{item.get('cantidad', '')}|"
                    f"{item.get('precioUnitario', '')}|"
                    f"{item.get('precioUnitarioDescuento', '')}|"
                    f"{item.get('precioItem', '')}|||"
                    f"{item.get('tasaITBMS', '')}|"
                    f"{item.get('valorITBMS', '')}|||||"
                    f"{item.get('valorTotal', '')}|"
                    f"{'und'}||||"
                    f"{item.get('codigoCPBSAbrev', '')}|"
                    f"{item.get('codigoCPBS', '')}|"
                    f"|||||||"
                )
            
            subtotals = document.get('totalesSubTotales')

            L07 = (
                f"\nL07|"
                f"{subtotals.get('totalPrecioNeto', '')}|"
                f"{subtotals.get('totalITBMS', '')}||"
                f"{subtotals.get('totalMontoGravado', '')}|"
                f"{subtotals.get('totalTodosItems', '')}|"
                f"{subtotals.get('totalDescuento', '')}|||"
                f"{subtotals.get('totalFactura', '')}|"
                f"{subtotals.get('totalValorRecibido', '')}|"
                f"{subtotals.get('vuelto', '')}|1|"
                f"{subtotals.get('nroItems', '')}|||"
            )

            L08 = ""
            for payment in subtotals['listaFormaPago']['formaPago']:
                L08 += (
                    f"\nL08|"
                    f"{payment.get('formaPagoFact', '')}|"
                    f"{payment.get('valorCuotaPagada', '')}|"
                    f"{payment.get('descFormaPago', '')}|"
                )

            doc_path = self.company_id.fel_pa_offline_pending_path

            if not os.path.exists(doc_path):
                os.makedirs(doc_path)

            self.offline_number = transaction_data.get('numeroDocumentoFiscal')

            write_path = f"{doc_path}/{transaction_data.get('numeroDocumentoFiscal')}.txt"
            with open(write_path, "w", encoding="utf-8") as f:
                f.write(L01)
                f.write(L02)
                if L04:
                    f.write(L04)
                f.write(L06)
                f.write(L07)
                f.write(L08)

            java_command = ["java", "-XX:CompressedClassSpaceSize=512m", "-Xmx1024m",
                            "-jar", "Pa_UsoServicios.jar", "ProcesarTxtOffLineGen", transaction_data.get('numeroDocumentoFiscal')]
            try:
                output = subprocess.check_output(java_command, cwd=self.company_id.fel_pa_offline_utility_path, stderr=subprocess.STDOUT, text=True)

                self.response_text = output

                error_match = re.search(r"ERROR: (.+)", output)
                if error_match:
                    error_message = error_match.group(1)
                    self.remove_file(write_path)
                    self.response_code = 202
                    return False, error_message
                
                result = (
                    re.search(r"Cufe: (.+)", output).group(1),
                    re.search(r"Qr: (.+)", output).group(1),
                )
                self.response_result = ', '.join(json.dumps(r) for r in result)

                self.response_message = re.search(r"Archivo: (.+)", output).group(1)

                response = re.search(r"Respuesta: (.+)", output).group(1)
                self.response_code = 200
                return result, response
            
            except subprocess.CalledProcessError as e:
                logger.error(f"JAR execution failed. Output: {e.output}")
                self.state = 'error'               
                if raise_exception:
                    raise ValidationError(_(f"JAR execution failed. Output: '{e.output}'"))
                return False, e.output
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                self.state = 'error'               
                if raise_exception:
                    raise ValidationError(_(f"Unexpected error: '{str(e)}'"))
                return False, str(e)
    
    @api.model
    def send_pac_offline_request(self):
        """Send offline request to the PAC."""

        requests = self.env['fel_pa.tools.api_request'].search([('offline_state', 'in', ['in_queue','error']),('offline_number', '!=', False)])

        for request in requests:
            if request.fel_pa_pac in ['the_factory_hka', 'ebi', 'efacturapty']:
                
                if not request.company_id.fel_pa_offline_utility_path:
                    raise ValidationError(_("Offline utility path is not set."))

                java_command = ["java", "-XX:CompressedClassSpaceSize=512m", "-Xmx1024m",
                                "-jar", "Pa_UsoServicios.jar", "SubirJsonOffLineGen", request.offline_number]
                
                try:
                    output = subprocess.check_output(java_command, cwd=request.company_id.fel_pa_offline_utility_path, stderr=subprocess.STDOUT, text=True)
                    request.message_post(body=f"Offline Upload Request: {output}")
                    msg = re.search(r"Archivo: (.+)", output)
                    request.message_post(body=f"Message Offline Upload Request: {msg.group(1)}")

                    response = re.search(r"Respuesta: (.+)", output).group(1)
                    response_json = json.loads(response)

                    if isinstance(response_json, list) and 'dCodRes' in response_json[0]:
                        d_cod_res = response_json[0]['dCodRes']
                        d_msg_res = response_json[0]['dMsgRes']
                        
                        if d_cod_res == "202":
                            request.message_post(body=f"Error en la lectura del XML. Código: {d_cod_res}, Mensaje: {d_msg_res}")
                            request.offline_state = 'error'
                        else:
                            request.offline_state = 'done'
                            request.state = 'done'
                            request.message_post(body=f"Uploaded to PAC Complete. Response: {response}")
                    else:
                        request.offline_state = 'error'
                                    
                except subprocess.CalledProcessError as e:
                    logger.error(f"JAR execution failed. Output: {e.output}")
                    self.offline_state = 'error'
                    request.message_post(body=f"Error Uploading to PAC. Error: {e.output}")
                except Exception as e:
                    logger.error(f"Unexpected error: {str(e)}")
                    self.offline_state = 'error'
                    request.message_post(body=f"Error Uploading to PAC. Error: {str(e)}")

    @api.model
    def remove_file(self, file_path):
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.info(f"error deleting file")
        else:
            logger.info(f"The file does not exist.")

