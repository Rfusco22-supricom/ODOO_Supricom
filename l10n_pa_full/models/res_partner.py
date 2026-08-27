# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)

        if view_type == 'form':
            company_country_code = (self.env.company.country_id.code or '').upper()
            if company_country_code == 'PA':
                label = 'RUC'
                placeholder = 'Ej.: 8-926-1601 / 155986022-2-2019 / PE-5-687'
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
                 pass
        
        return res

    is_panama = fields.Boolean(
        string='Es Panamá',
        compute='_compute_is_panama',
        store=True,
        help='Indica si el país del contacto es Panamá'
    )
    ruc = fields.Char(
        string='RUC',
        related='vat',
        readonly=False,
        store=False,
        help='Registro Único de Contribuyente de Panamá'
    )
    ruc_type = fields.Selection([
        ('natural', 'Persona Natural'),
        ('juridica', 'Persona Jurídica'),
    ], string='Tipo de RUC', 
       help='Tipo de RUC: Natural (personas) o Jurídica (empresas/organizaciones)')

    @api.depends('country_id')
    def _compute_is_panama(self):
        for partner in self:
            partner.is_panama = partner.country_id and partner.country_id.code == 'PA'

    @api.constrains('ruc', 'is_panama', 'ruc_type')
    def _check_ruc_format(self):
        """
        Valida el formato del RUC panameño según documentación oficial:
        https://lookuptax.com/docs/tax-identification-number/panama-tax-id-guide
        """
        for partner in self:
            if not partner.is_panama or not partner.ruc:
                continue
            
            ruc = partner.ruc.strip().upper()
            
            # Verificar estructura básica
            parts = ruc.split('-')
            if len(parts) != 3:
                raise ValidationError(
                    'El RUC debe tener el formato: PP-TIPO-NNNNNN o NNNNNN-TIPO-NNNNNN\n'
                    'Ejemplo: 8-123-4567 o 155777-2-2019'
                )
            
            provincia, tomo, asiento = parts
            
            # Detectar si tiene dígito de tipo 2 o 3 en el tomo (identifica persona jurídica)
            has_type_digit = tomo in ['2', '3'] or (len(tomo) >= 2 and tomo[0] in ['2', '3'] and tomo[1:].isdigit())
            
            if partner.ruc_type == 'natural':
                # ===== PERSONAS NATURALES =====
                
                # Nuevos formatos con código de tipo
                # Formato: PP-TIPO-NNNNNN
                # PP: Provincia (1-13, con o sin cero inicial)
                # TIPO: AV (nacimiento), PI (nacimiento), NT (nacido extranjero), N (naturalizado), PE (extranjero), E (extranjero)
                # NNNNNN: Asiento (1-6 dígitos)
                pattern_new = re.compile(r'^(0?[1-9]|1[0-3])-(AV|PI|NT|PE|E|N)-\d{1,6}$')
                
                if pattern_new.match(ruc):
                    # Validar provincia (1-13)
                    try:
                        prov_num = int(provincia)
                        if prov_num < 1 or prov_num > 13:
                            raise ValidationError(
                                f'Provincia inválida: {prov_num}\n'
                                'Las provincias de Panamá van del 1 al 13:\n'
                                '1=Bocas del Toro, 2=Coclé, 3=Colón, 4=Chiriquí, 5=Darién, '
                                '6=Herrera, 7=Los Santos, 8=Panamá, 9=Veraguas, '
                                '10=Kuna Yala, 11=Emberá-Wounaan, 12=Ngäbe-Buglé, 13=Panamá Oeste'
                            )
                    except ValueError:
                        pass  # El regex ya validó que es numérico
                    return  # Formato válido
                
                # Formato antiguo (solo si NO tiene dígito de tipo 2 o 3)
                # Formato: PP-NNNN-NNNNNN
                if not has_type_digit:
                    pattern_old = re.compile(r'^(0?[1-9]|1[0-3])-\d{1,4}-\d{1,6}$')
                    if pattern_old.match(ruc):
                        # Validar provincia
                        try:
                            prov_num = int(provincia)
                            if prov_num < 1 or prov_num > 13:
                                raise ValidationError(
                                    f'Provincia inválida: {prov_num}\n'
                                    'Las provincias de Panamá van del 1 al 13'
                                )
                        except ValueError:
                            raise ValidationError('La provincia debe ser un número entre 1 y 13')
                        return  # Formato antiguo válido
                
                # Si llegamos aquí, el formato es inválido
                raise ValidationError(
                    'Formato de RUC inválido para Persona Natural.\n\n'
                    'Formatos válidos:\n'
                    '• Nuevo formato: PP-TIPO-NNNNNN\n'
                    '  Ejemplos: 8-123-4567, 8-PI-12345, 8-NT-12345, 8-PE-12345\n'
                    '  TIPO puede ser: AV, PI (nacimiento), NT (nacido extranjero), '
                    'N (naturalizado), PE o E (extranjero)\n\n'
                    '• Formato antiguo: PP-NNNN-NNNNNN\n'
                    '  Ejemplo: 8-123-456\n\n'
                    'PP = Provincia (1-13), NNNNNN = Número de asiento'
                )
            
            elif partner.ruc_type == 'juridica':
                # ===== PERSONAS JURÍDICAS =====
                
                # Formato: NNNNNN-TIPO-NNNNNN
                # NNNNNN: Folio (4-6 dígitos)
                # TIPO: 2 (sociedades comerciales) o 3 (instituciones no comerciales)
                # NNNNNN: Asiento (4-6 dígitos)
                pattern_juridica = re.compile(r'^\d{4,6}-(2|3)-\d{4,6}$')
                
                if not pattern_juridica.match(ruc):
                    raise ValidationError(
                        'Formato de RUC inválido para Persona Jurídica.\n\n'
                        'Formato válido: NNNNNN-TIPO-NNNNNN\n'
                        'Ejemplo: 155777-2-2019\n\n'
                        'TIPO puede ser:\n'
                        '• 2: Sociedades Comerciales\n'
                        '• 3: Instituciones No Comerciales\n\n'
                        'El folio (primera parte) y el asiento (tercera parte) '
                        'deben tener entre 4 y 6 dígitos cada uno.'
                    )
                
                # Validar longitudes
                folio, tipo, asiento_num = parts
                if len(folio) < 4 or len(folio) > 6:
                    raise ValidationError(
                        f'El folio (primera parte) debe tener entre 4 y 6 dígitos. '
                        f'Actual: {len(folio)} dígitos'
                    )
                if len(asiento_num) < 4 or len(asiento_num) > 6:
                    raise ValidationError(
                        f'El asiento (tercera parte) debe tener entre 4 y 6 dígitos. '
                        f'Actual: {len(asiento_num)} dígitos'
                    )

    def _compute_same_vat_partner_id(self):
        """Extiende para considerar también el RUC en la búsqueda de duplicados"""
        super()._compute_same_vat_partner_id()
        for partner in self:
            if partner.is_panama and partner.ruc:
                Partner = self.with_context(active_test=False).sudo()
                domain = [
                    ('ruc', '=', partner.ruc),
                    ('company_id', 'in', [False, partner.company_id.id]),
                    ('id', '!=', partner._origin.id),
                ]
                if partner._origin.id:
                    domain += ['!', ('id', 'child_of', partner._origin.id)]
                duplicate = Partner.search(domain, limit=1)
                if duplicate and not partner.parent_id:
                    partner.same_vat_partner_id = duplicate
