# -*- coding: UTF-8 -*-
from email.policy import default

from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
from odoo.addons import decimal_precision as dp
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    _VE_ONLY_IDENTITY_FIELDS = (
        'people_type_individual',
        'nationality',
        'identification_id',
    )

    is_ve_company = fields.Boolean(
        compute='_compute_is_ve_company_env',
        string='Empresa VE',
        default=lambda self: self.env.company.is_ve_company
    )

    @api.depends_context('company')
    def _compute_is_ve_company_env(self):
        is_ve = getattr(self.env.company, 'is_ve_company', False)
        for record in self:
            record.is_ve_company = is_ve

    is_venezuela = fields.Boolean(
        string='Es Venezuela',
        compute='_compute_is_venezuela',
        store=True,
        help='Indica si el país del contacto es Venezuela'
    )

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)

        if view_type == 'form':
            company_country_code = (self.env.company.country_id.code or '').upper()
            if company_country_code == 'VE':
                label = 'RIF'
                placeholder = 'Ej.: J-01234567-8'
                for node in arch.xpath("//label[@for='vat']"):
                    node.attrib['string'] = label
                for node in arch.xpath("//field[@name='vat']"):
                    node.attrib['string'] = label
                    node.attrib['placeholder'] = placeholder
                for node in arch.xpath(
                    "//*[contains(concat(' ', normalize-space(@class), ' '), ' o_vat_label ')]"
                ):
                    node.text = label

        return arch, view

    @api.model
    def default_get(self, fields_list):
        """Override default_get para establecer el país de la compañía actual como default"""
        res = super(ResPartner, self).default_get(fields_list)
        
        # Siempre usar el país de la compañía actual si está disponible
        if 'country_id' in fields_list:
            if self.env.company.country_id:
                # Sobrescribir con el país de la compañía actual
                res['country_id'] = self.env.company.country_id.id
            elif 'country_id' not in res:
                # Solo si no hay país de compañía Y no hay default previo, usar Venezuela como fallback
                res['country_id'] = 238  # Venezuela
        
        return res

    @api.depends('country_id')
    def _compute_is_venezuela(self):
        for partner in self:
            partner.is_venezuela = partner.country_id and partner.country_id.code == 'VE'

    def _get_ve_only_identity_clear_vals(self):
        return {field_name: False for field_name in self._VE_ONLY_IDENTITY_FIELDS}

    @api.onchange('country_id')
    def _onchange_country_id_clear_ve_only_identity_fields(self):
        for partner in self:
            if partner.country_id and partner.country_id.code == 'VE':
                continue
            partner.update(partner._get_ve_only_identity_clear_vals())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'rif' in vals and not vals.get('vat'):
                vals['vat'] = vals['rif']

        partners = super().create(vals_list)

        # Asegura que las validaciones VE se apliquen también en create.
        partners._check_ve_rif_vat_allowed_values()

        partners_to_clear = partners.filtered(lambda p: not p.country_id or p.country_id.code != 'VE')
        if partners_to_clear:
            super(ResPartner, partners_to_clear.with_context(skip_ve_only_cleanup=True)).write(
                partners_to_clear._get_ve_only_identity_clear_vals()
            )
        return partners

    def write(self, vals):
        if 'rif' in vals and not vals.get('vat'):
            vals['vat'] = vals['rif']

        if self.env.context.get('skip_ve_only_cleanup'):
            return super().write(vals)

        res = super().write(vals)

        # Asegura que las validaciones VE se apliquen en write, pero evitando
        # dispararlas en writes internos (p.ej. inverses) que no tocan los
        # campos relevantes para el documento.
        if {'vat', 'country_id', 'company_type', 'people_type_company'} & set(vals.keys()):
            self._check_ve_rif_vat_allowed_values()

        partners_to_clear = self.filtered(lambda p: not p.country_id or p.country_id.code != 'VE')
        if partners_to_clear:
            super(ResPartner, partners_to_clear.with_context(skip_ve_only_cleanup=True)).write(
                partners_to_clear._get_ve_only_identity_clear_vals()
            )
        return res
    
    nationality = fields.Selection([
        ('V', 'Venezolano'),
        ('E', 'Extranjero'),
        ('P', 'Pasaporte')], string="Tipo Documento", default='V')
    identification_id = fields.Char(string='Documento de Identidad', tracking=True)
    value_parent = fields.Boolean(string='Valor parent_id', compute='compute_value_parent_id')
    people_type_individual = fields.Selection([
        ('pnre', 'PNRE Persona Natural Residente'),
        ('pnnr', 'PNNR Persona Natural No Residente')
    ], string='Tipo de Persona individual', default='pnre')
    people_type_company = fields.Selection([
        ('pjdo', 'PJDO Persona Jurídica Domiciliada'),
        ('pjnd', 'PJND Persona Jurídica No Domiciliada')], string='Tipo de Persona compañía', default='pjdo')
    rif = fields.Char(
        string='RIF',
        compute='_compute_rif',
        inverse='_inverse_rif',
        readonly=False,
        store=False,
    )

    @api.depends('vat')
    def _compute_rif(self):
        for record in self:
            record.rif = record.vat

    def _inverse_rif(self):
        for record in self:
            record.vat = record.rif

    @staticmethod
    def _ve_normalize_document(value: str) -> str:
        if not value:
            return ''
        # Conservador: quita separadores comunes y deja letras/dígitos.
        return re.sub(r'[^0-9A-Za-z]', '', value).upper().strip()

    @classmethod
    def _is_valid_ve_rif(cls, value: str) -> bool:
        # Formato activo (sin guiones): 1 letra VEJGC + 9 dígitos.
        value = cls._ve_normalize_document(value)
        return bool(re.fullmatch(r'[VEJGC][0-9]{9}', value))

    @classmethod
    def _is_valid_ve_cedula(cls, value: str) -> bool:
        # Formato: 1 letra V/E/P + 6-15 dígitos.
        value = cls._ve_normalize_document(value)
        return bool(re.fullmatch(r'[VEP][0-9]{6,15}', value))

    @api.constrains('vat', 'country_id', 'company_type', 'people_type_company')
    def _check_ve_rif_vat_allowed_values(self):
        """Validaciones específicas de Venezuela.

        - Empresas PJDO (domiciliadas): RIF requerido y con formato permitido.
        - Personas: si se ingresa VAT, valida formato de cédula/pasaporte.
        """
        for partner in self:
            if not partner.country_id or partner.country_id.code != 'VE':
                continue

            # Bypass validation for child contacts (e.g., delivery addresses)
            # This prevents errors when a child inherits a company VAT (J/G) but is treated as a person.
            if partner.parent_id:
                continue

            vat = (partner.vat or '').strip()

#            if partner.company_type == 'company' and partner.people_type_company == 'pjdo':
#                if not vat:
#                    raise ValidationError('El RIF es requerido para compañías (PJDO) en Venezuela.')
#                if not self._is_valid_ve_rif(vat):
#                    raise ValidationError(
#                        'Formato de RIF inválido. Formato permitido (sin guiones): '
#                        'V/E/J/G/C + 9 dígitos. Ejemplo: J012345678'
#                    )

            if partner.company_type == 'person' and vat:
                if not self._is_valid_ve_cedula(vat):
                    raise ValidationError(
                        'Formato de documento inválido para Venezuela. Formato permitido: '
                        'V/E/P + 6 a 15 dígitos. Ejemplo: V12345678'
                    )

    wh_iva_agent = fields.Boolean(
        '¿Es Agente de Retención (IVA)?',
        help="Indique si el socio es un agente de retención de IVA", default=True)

    wh_iva_rate = fields.Float(
        string='% Retención de IVA',
        help="Se coloca el porcentaje de la Tasa de retención de IVA", default=75.0)

    vat_subjected = fields.Boolean('Declaración legal de IVA',
    help="Marque esta casilla si el socio está sujeto al IVA. Se utilizará para la declaración legal del IVA.", default=True)

    purchase_journal_id = fields.Many2one('account.journal','Diario de Compra para IVA', company_dependent=True,
                                        domain="[('is_iva_journal','=', True), ('company_id', '=', current_company_id)]")
    purchase_sales_id = fields.Many2one('account.journal', 'Diario de Venta para IVA', company_dependent=True,
                                        domain="[('is_iva_journal','=', True), ('company_id', '=', current_company_id)]")

    ## ISLR #######################
    islr_withholding_agent = fields.Boolean(
        '¿Agente de retención de ingresos?', default=True,
        help="Verifique si el partner es un agente de retención de ingresos")
    spn = fields.Boolean(
        '¿Es una sociedad de personas físicas?',
        help='Indica si se refiere a una sociedad de personas físicas.')
    islr_exempt = fields.Boolean(
        '¿Está exento de retención de ingresos?',
        help='Si el individuo está exento de retención de ingresos')
    purchase_islr_journal_id = fields.Many2one('account.journal', 'Diario de Compra para ISLR', company_dependent=True,
                                        domain="[('is_islr_journal','=', True), ('company_id', '=', current_company_id)]")
    sale_islr_journal_id = fields.Many2one('account.journal', 'Diario de Venta para ISLR', company_dependent=True,
                                        domain="[('is_islr_journal','=', True), ('company_id', '=', current_company_id)]")

    same_vat_partner_id = fields.Many2one('res.partner', string='Contacto con el mismo RIF',
                                          compute='_compute_same_rif_partner_id', store=False)

    contribuyente_seniat = fields.Selection([
        ('ordinario', 'Ordinario'),
        ('especial', 'Especial'),
        ('formal', 'Formal'),
        ('gobernamental', 'Gubernamental')], string="Contribuyente", default='ordinario')

    '''
    @api.model_create_multi
    def create(self, vals):
        company_type = vals[0].get('company_type')
        vat = vals[0].get('vat')
        letters = ''
        numbers = ''

        if vat:
            letters = ''.join(filter(str.isalpha, vat))
            numbers = ''.join(filter(str.isdigit, vat))
            if company_type:
                if company_type == 'person':

                    vals[0]['people_type_company'] = ''

                    # validar formato de cedula ingresado
                    if not self.validar_cedula(vat):
                        raise UserError(
                            'Formato de cedula incorrecto. Ej: V012345678, E012345678 o P012345678. Por favor verifique el siguiente formato V12345678 y que contenga entre 7 y 16 digitos.')

                    # validar si ya existe la cédula
                    ci_count = self.env['res.partner'].search([('rif', '=', vat)])
                    person_partners = ci_count.filtered(lambda p: p.company_type == 'person')
                    ci_count = len(person_partners)

                    if ci_count > 0:
                        raise UserError('El cliente ya se encuentra registrado con la cédula: ' + vat)

                if company_type == 'company':
                    vals[0]['people_type_individual'] = ''

                    if not self.validar_rif(vat):
                        raise UserError(
                            'Formato de rif incorrecto. Ej: V012345678, E012345678, J012345678 o G012345678. Por favor verifique el formato y que contenga 10 dígitos.')

                    # validar si existe el rif
                    rif_count = self.env['res.partner'].search([('rif', '=', vat)])
                    person_partners = rif_count.filtered(lambda p: p.company_type == 'company')
                    rif_count = len(person_partners)

                    if rif_count > 0:
                        raise UserError('El cliente ya se encuentra registrado con el rif: ' + vat)

                    vals[0]['rif'] = vals[0]['vat']
                    vals[0]['vat'] = ''

        if vals[0].get('identification_id') and vals[0].get('nationality'):
            valor = vals[0].get('identification_id')
            nationality = vals[0].get('nationality')
            type = vals[0].get('company_type')
            self.validation_document_ident(valor, nationality, type)
        elif letters and numbers:
            if vals[0]['vat'] != '':
                if not self.validate_ci_duplicate(letters, True):
                    raise UserError('El cliente o proveedor ya se encuentra registrado con el Documento: %s'
                                    % (letters))
                else:
                    vals[0]['identification_id'] = numbers
                    vals[0]['nationality'] = letters

        if vals[0].get('identification_id'):
            if not self.validate_ci_duplicate(vals[0].get('identification_id', False), True):
                raise UserError('El cliente o proveedor ya se encuentra registrado con el Documento: %s'
                                % (vals[0].get('identification_id', False)))

        res = super(ResPartner, self).create(vals)

        return res
    '''
    '''
    def write(self, vals):
        #res = super(ResPartner, self).write(vals)
        #return res

        company_type = vals.get('company_type')
        vat = vals.get('vat')
        letters = ''
        numbers = ''

        if vat:
            letters = ''.join(filter(str.isalpha, vat))
            numbers = ''.join(filter(str.isdigit, vat))
            if company_type:
                if company_type == 'person':
                    vals['people_type_company'] = ''

                    # validar formato de cedula ingresado
                    if not self.validar_cedula(vat):
                        raise UserError(
                            'Formato de cedula incorrecto. Ej: V012345678, E012345678 o P012345678. Por favor verifique el siguiente formato V12345678 y que contenga entre 7 y 16 digitos.')

                    # validar si ya existe la cédula
                    ci_count = self.env['res.partner'].search([('rif', '=', vat)])
                    person_partners = ci_count.filtered(lambda p: p.company_type == 'person')
                    ci_count = len(person_partners)

                    if ci_count > 0:
                        raise UserError('El cliente ya se encuentra registrado con la cédula: ' + vat)
                    else:
                        letters = ''.join(filter(str.isalpha, vat))
                        numbers = ''.join(filter(str.isdigit, vat))

                        vals[0]['identification_id'] = numbers
                        vals[0]['nationality'] = letters

                if company_type == 'company':
                    vals['people_type_individual'] = ''

                    if not self.validar_rif(vat):
                        raise UserError(
                            'Formato de rif incorrecto. Ej: V012345678, E012345678, J012345678 o G012345678. Por favor verifique el formato y que contenga 10 dígitos.')

                    # validar si existe el rif
                    rif_count = self.env['res.partner'].search([('rif', '=', vat)])
                    person_partners = rif_count.filtered(lambda p: p.company_type == 'company')
                    rif_count = len(person_partners)

                    if rif_count > 0:
                        raise UserError('El cliente ya se encuentra registrado con el rif: ' + vat)

                    vals['rif'] = vals['vat']
                    vals['vat'] = ''

        if vals.get('identification_id') and vals.get('nationality'):
            valor = vals.get('identification_id')
            nationality = vals.get('nationality')
            type = vals.get('company_type')
            self.validation_document_ident(valor, nationality, type)
        elif letters and numbers:
            if vals['vat'] != '':
                if not self.validate_ci_duplicate(letters, True):
                    raise UserError('El cliente o proveedor ya se encuentra registrado con el Documento: %s'
                                    % (letters))
                else:
                    vals[0]['identification_id'] = numbers
                    vals[0]['nationality'] = letters

        if vals.get('identification_id'):
            if not self.validate_ci_duplicate(vals.get('identification_id', False), True):
                raise UserError('El cliente o proveedor ya se encuentra registrado con el Documento: %s'
                                % (vals.get('identification_id', False)))

        res = super(ResPartner, self).write(vals)
        return res
    '''
    # def validar_rif(self, field_value):
    #     res = {}
    #     rif_obj = re.compile(r"[VEJGC]{1}[0-9]{9}", re.X)
    #     if rif_obj.search(field_value.upper()):
    #         if len(field_value) == 10:
    #             res = {
    #                 'rif': field_value
    #             }
    #     return res

    # def validar_cedula(self, field_value):
    #     res = {}
    #     rif_obj = re.compile(r"[VEP]{1}[0-9]{6,15}", re.X)
    #     if rif_obj.search(field_value.upper()):
    #         if 7 <= len(field_value) <= 16:
    #             res = {
    #                 'rif': field_value
    #             }
    #     return res

    @api.depends('vat', 'company_id')
    def _compute_same_rif_partner_id(self):
        for partner in self:
            # Si el VAT/RIF está vacío, no hay duplicado posible (evita False == False)
            vat = (partner.vat or '').strip()
            if not vat or partner.parent_id:
                partner.same_vat_partner_id = False
                continue

            # use _origin to deal with onchange()
            partner_id = partner._origin.id
            # active_test = False because if a partner has been deactivated you still want to raise the error,
            # so that you can reactivate it instead of creating a new one, which would loose its history.
            Partner = self.with_context(active_test=False).sudo()
            domain = [
                ('vat', '=', vat),
                ('company_id', 'in', [False, partner.company_id.id]),
            ]
            if partner_id:
                domain += [('id', '!=', partner_id), '!', ('id', 'child_of', partner_id)]
            partner.same_vat_partner_id = Partner.search(domain, limit=1)

    @api.constrains('vat')
    def validate_rifs(self):
        for rec in self:
            # Solo aplica para contactos de Venezuela
            if not rec.country_id or rec.country_id.code != 'VE':
                continue

            vat = (rec.vat or '').strip()
            # Si el VAT/RIF está vacío, no buscar duplicados (evita False == False)
            if not vat:
                continue

            # Bypass duplicate check for child contacts (e.g., delivery addresses)
            if rec.parent_id:
                continue

            # Verificar duplicados buscando en 'vat' (campo stored),
            # excluyendo el registro actual para evitar falsos positivos
            domain = [
                ('vat', '=', vat),
                ('id', '!=', rec._origin.id or rec.id),
            ]
            duplicate = self.env['res.partner'].with_context(active_test=False).search(domain, limit=1)
            if duplicate:
                raise ValidationError(
                    'Ya existe un contacto con el mismo RIF/Cédula: '
                    '%s (%s)' % (duplicate.name, duplicate.vat)
                )

    '''
    #Method for the method write
    def exist_identification_document(self, id, nationality):
        if id:
            partner_duplicate = self.search_count([('identification_id', '=', id), ('nationality', '=', nationality)])
            print(partner_duplicate)
            if partner_duplicate>1:
                raise UserError('El cliente o proveedor ya se encuentra registrado con el Documento: %s'
                                    % (id))
            
    #Method for validate emails
    @api.constrains('email')
    def validate_email(self):
        for rec in self:
            if rec.email:
                if not self.validate_email_addrs(rec.email, 'email'):
                    raise UserError('El email es incorrecto. Ej: cuenta@dominio.xxx. Por favor intente de nuevo')
                
    @api.constrains('nationality')
    def validate_identification(self):
        self.validation_identification_document()

    #Method for validate the identification
    @api.constrains('identification_id')
    def validation_identification_document(self):
        for vals in self:
            if vals.company_type == 'person': 
                valor = vals.identification_id
                nationality = vals.nationality
                #if nationality == 'V' or nationality == 'E':
                if valor:
                    #if len(valor) == 7 or len(valor) == 8:
                    if  6 <= len(valor) <= 15:
                        if not valor.isdigit():
                            raise UserError(
                                'La Cédula solo debe ser Numérico. Por favor corregir para proceder a Crear/Editar el registro')
                    else:
                        raise UserError('La Cédula de Identidad no puede ser menor que 6 cifras ni mayor a 15')
                #if nationality == 'P':
                    #if (len(valor) > 20) or (len(valor) < 10):
                #    if 6 <= len(valor) <= 15:
                #        if not valor.isdigit():
                #            raise UserError(
                #                'El Pasaporte solo debe ser Numérico. Por favor corregir para proceder a Crear/Editar el registro')
                #    else:
                #        raise UserError('El Pasaporte no puede ser menor que 6 cifras ni mayor a 15')
                self.exist_identification_document(vals.identification_id, nationality)
    '''
    # Method for the method constrain validate_rifs (old dash format)
    # def validate_rif(self, field_value):
    #     res = {}
    #     rif_obj = re.compile(r"[VEJGC]{1}[-]{1}[0-9]{8}[-]{1}[0-9]{1}", re.X)
    #     if rif_obj.search(field_value.upper()):
    #         if len(field_value) == 12:
    #             res = {
    #                 'rif': field_value
    #             }
    #     return res

    # def write(self, vals):
    #     res = super(ResPartner, self).write(vals)
    #
    #     if vals.get('identification_id') and not vals.get('nationality'):
    #         valor = vals.get('identification_id')
    #         nationality = self.nationality
    #         self.validation_document_ident(valor, nationality)
    #     if vals.get('identification_id') and vals.get('nationality'):
    #         valor = vals.get('identification_id')
    #         nationality = vals.get('nationality')
    #         self.validation_document_ident(valor, nationality)
    #     if vals.get('nationality') and not vals.get('identification_id'):
    #         valor = self.identification_id
    #         nationality = vals.get('nationality')
    #         self.validation_document_ident(valor, nationality)
    #     if not self.validate_ci_duplicate(vals.get('identification_id', False)):
    #         raise UserError('El cliente o proveedor ya se encuentra registrado con el Documento: %s'
    #                         % (vals.get('identification_id', False)))
    #
    #     if self.rif:
    #         vals['rif'] = self.rif.upper()
    #         if self.country_id:
    #             if self.country_id.code == 'VE':
    #                 if not self.validate_rif_er(self.rif):
    #                     raise UserError(
    #                         'El rif tiene el formato incorrecto. Ej: V-01234567-8, E-01234567-8, J-01234567-8 o G-01234567-8. Por favor verifique el formato y si posee los 12 caracteres como se indica en el Ej. e intente de nuevo')
    #         vals['vat'] = self.rif
    #
    #     if vals.get('email'):
    #         if not self.validate_email_addrs(vals.get('email'), 'email'):
    #             raise UserError('El email es incorrecto. Ej: cuenta@dominio.xxx. Por favor intente de nuevo')
    #
    #
    #
    #     if vals.get('rif'):
    #         if self.country_id:
    #             if self.country_id.code == 'VE':
    #                 if self.validate_rif_duplicate(vals.get('rif'), res):
    #                     raise UserError('El cliente o proveedor ya se encuentra registrado con el rif: %s y se encuentra activo'
    #                             % (vals.get('rif')))
    #
    #     return res

    @api.constrains('vat', 'vat_type', 'country_id')
    def check_vat(self):
        for rec in self:
            if rec.country_id:
                if rec.country_id.code == 'VE':
                    return
                else:
                    return super().check_vat()

    @api.depends('company_type')
    def compute_value_parent_id(self):
        for rec in self:
            rec.value_parent = rec.parent_id.active

    '''
    @staticmethod
    def validation_document_ident(valor, nationality, type):
        if valor and type =='person':
            if nationality == 'V' or nationality == 'E':
                #if len(valor) == 7 or len(valor) == 8:
                if 6 <= len(valor) <= 9:
                    if not valor.isdigit():
                        raise UserError(
                                'La Cédula solo debe ser Numérico. Por favor corregir para proceder a Crear/Editar el registro')
                else:
                    raise UserError('La Cedula de Identidad no puede ser menor que 6 cifras ni mayor a 9.')
            if nationality == 'P':
                #if (len(valor) > 20) or (len(valor) < 10):
                if 6 <= len(valor) <= 15:
                    if not valor.isdigit():
                        raise UserError('El Pasaporte solo debe ser Numérico. Por favor corregir para proceder a Crear/Editar el registro')
                else:
                    raise UserError('El Pasaporte no puede ser menor que 6 cifras ni mayor a 15')

    '''
    def validate_ci_duplicate(self, valor, create=False):
        found = True
        partner_2 = self.search([('identification_id', '=', valor)])
        for cus_supp in partner_2:
            if create:
                if cus_supp and (cus_supp.customer_rank or cus_supp.supplier_rank):
                    found = False
                elif cus_supp and (cus_supp.customer_rank or cus_supp.supplier_rank):
                    found = False
        return found

    @api.onchange('company_type')
    def change_country_id_partner(self):
        """Establece el país de la compañía actual como default"""
        if self.env.company.country_id:
             self.country_id = self.env.company.country_id.id
        else:
             self.country_id = 238
    '''
    @staticmethod
    def validate_rif_er(field_value):
        res = {}
        rif_obj = re.compile(r"[VEJGC]{1}[-]{1}[0-9]{9}[-]{1}[0-9]{1}", re.X)
        rif_obj_2 = re.compile(r"[VEJGC]{1}[-]{1}[0-9]{8}[-]{1}[0-9]{1}", re.X)
        if rif_obj.search(field_value.upper()) or rif_obj_2.search(field_value.upper()):
            res = {
                'rif': field_value
            }
        return res
    '''
    '''
    def validate_rif_duplicate(self, valor, res):
        if self:
            aux_ids = self.ids
            aux_item = self
        else:
            aux_ids = res.ids
            aux_item = res
        for _ in aux_item:
            partner = self.env['res.partner'].search([('rif', '=', valor), ('id', 'not in', aux_ids)])
            if partner:
                return True
            else:
                return False
    '''
    @staticmethod
    def validate_email_addrs(email, field):
        res = {}
        mail_obj = re.compile(r"""
                    \b             # comienzo de delimitador de palabra
                    [\w.%+-]       # usuario: Cualquier caracter alfanumerico mas los signos (.%+-)
                    +@             # seguido de @
                    [\w.-]         # dominio: Cualquier caracter alfanumerico mas los signos (.-)
                    +\.            # seguido de .
                    [a-zA-Z]{2,3}  # dominio de alto nivel: 2 a 6 letras en minúsculas o mayúsculas.
                    \b             # fin de delimitador de palabra
                    """, re.X)  # bandera de compilacion X: habilita la modo verborrágico, el cual permite organizar
        # el patrón de búsqueda de una forma que sea más sencilla de entender y leer.
        if mail_obj.search(email):
            res = {
                field: email
            }
        return res