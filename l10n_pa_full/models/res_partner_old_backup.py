# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
import re


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_panama = fields.Boolean(
        string='Es Panamá',
        compute='_compute_is_panama',
        store=True,
        help='Indica si el país del contacto es Panamá'
    )
    ruc = fields.Char(
        string='RUC',
        help='Registro Único de Contribuyente de Panamá'
    )
    ruc_type = fields.Selection([
        ('natural_national', 'Persona Natural - Panameño por nacimiento'),
        ('natural_foreign_born', 'Persona Natural - Panameño nacido en extranjero'),
        ('natural_naturalized', 'Persona Natural - Panameño naturalizado'),
        ('natural_foreign', 'Persona Natural - Extranjero con domicilio legal'),
        ('legal_commercial', 'Persona Jurídica - Sociedad Comercial (Tipo 2)'),
        ('legal_non_commercial', 'Persona Jurídica - Institución No Comercial (Tipo 3)'),
        ('tax_number', 'Número Tributario (NT)'),
    ], string='Tipo de RUC', compute='_compute_ruc_type', store=True,
       help='Tipo de RUC detectado automáticamente según el formato')

    @api.depends('country_id')
    def _compute_is_panama(self):
        for partner in self:
            partner.is_panama = partner.country_id and partner.country_id.code == 'PA'

    @api.depends('ruc', 'is_panama')
    def _compute_ruc_type(self):
        """Detecta automáticamente el tipo de RUC según su formato"""
        for partner in self:
            if not partner.is_panama or not partner.ruc:
                partner.ruc_type = False
                continue
                
            ruc_clean = partner.ruc.upper().strip()
            
            # Detectar el tipo según el formato - orden importa
            if ruc_clean.startswith('PE-'):
                partner.ruc_type = 'natural_foreign_born'
            elif ruc_clean.startswith('N-'):
                partner.ruc_type = 'natural_naturalized'
            elif ruc_clean.startswith('E-'):
                partner.ruc_type = 'natural_foreign'
            elif '-NT-' in ruc_clean:
                partner.ruc_type = 'tax_number'
            elif re.match(r'^\d{9}-2-\d{4}$', ruc_clean):
                # Formato nuevo sociedad comercial (9 dígitos-2-año)
                partner.ruc_type = 'legal_commercial'
            elif re.match(r'^\d{8}-3-\d{4}$', ruc_clean):
                # Formato nuevo institución no comercial (8 dígitos-3-año)
                partner.ruc_type = 'legal_non_commercial'
            elif re.match(r'^([1-9]|1[0-3])-\d+-\d+$', ruc_clean):
                # Persona natural panameña (provincia-volumen-entrada)
                partner.ruc_type = 'natural_national'
            else:
                # Formato no reconocido o antiguo
                partner.ruc_type = False

    @api.onchange('ruc')
    def _onchange_ruc(self):
        """Sincroniza el RUC con el campo VAT estándar de Odoo"""
        for rec in self:
            if rec.ruc and rec.is_panama:
                rec.vat = rec.ruc.upper()
            elif rec.is_panama:
                rec.vat = ''

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para sincronizar RUC con VAT"""
        for vals in vals_list:
            # Sincronizar RUC a VAT si es necesario
            if 'ruc' in vals and vals.get('ruc'):
                # Verificar si es de Panamá
                country_id = vals.get('country_id')
                if country_id:
                    country = self.env['res.country'].browse(country_id)
                    if country.code == 'PA':
                        vals['vat'] = vals['ruc'].upper()
        
        return super().create(vals_list)

    def write(self, vals):
        """Override write para sincronizar RUC con VAT"""
        # Sincronizar RUC a VAT si es necesario
        if 'ruc' in vals:
            for partner in self:
                if partner.is_panama and vals.get('ruc'):
                    vals['vat'] = vals['ruc'].upper()
                elif partner.is_panama and not vals.get('ruc'):
                    vals['vat'] = False
        
        return super().write(vals)

    def _validate_ruc_natural_national(self, ruc):
        """
        Valida RUC de persona natural panameña por nacimiento.
        Formato: P-VV-EEEE
        - P: Provincia (1-13)
        - VV: Volumen (1-4 dígitos)
        - EEEE: Entrada (1-6 dígitos)
        Ejemplos: 8-926-1601, 1-23-456
        """
        pattern = re.compile(r'^([1-9]|1[0-3])-(\d{1,4})-(\d{1,6})$')
        match = pattern.match(ruc)
        
        if not match:
            raise ValidationError(
                'Formato de RUC incorrecto para Persona Natural Panameña por nacimiento.\n\n'
                'Formato válido: P-VV-EEEE\n'
                '- P: Número de provincia (1-13)\n'
                '- VV: Volumen (1 a 4 dígitos)\n'
                '- EEEE: Entrada (1 a 6 dígitos)\n\n'
                'Ejemplos válidos: 8-926-1601, 1-23-456'
            )
        
        provincia = int(match.group(1))
        if provincia < 1 or provincia > 13:
            raise ValidationError(
                f'Código de provincia inválido: {provincia}\n'
                'Las provincias válidas son del 1 al 13.'
            )

    def _validate_ruc_natural_foreign_born(self, ruc):
        """
        Valida RUC de panameño nacido en el extranjero.
        Formato: PE-VV-EEEE
        Ejemplo: PE-5-687
        """
        pattern = re.compile(r'^PE-(\d{1,4})-(\d{1,6})$', re.IGNORECASE)
        if not pattern.match(ruc):
            raise ValidationError(
                'Formato de RUC incorrecto para Panameño nacido en el extranjero.\n\n'
                'Formato válido: PE-VV-EEEE\n'
                '- VV: Volumen (1 a 4 dígitos)\n'
                '- EEEE: Entrada (1 a 6 dígitos)\n\n'
                'Ejemplo válido: PE-5-687'
            )

    def _validate_ruc_natural_naturalized(self, ruc):
        """
        Valida RUC de panameño naturalizado.
        Formato: N-VV-EEEE
        Ejemplo: N-19-473
        """
        pattern = re.compile(r'^N-(\d{1,4})-(\d{1,6})$', re.IGNORECASE)
        if not pattern.match(ruc):
            raise ValidationError(
                'Formato de RUC incorrecto para Panameño naturalizado.\n\n'
                'Formato válido: N-VV-EEEE\n'
                '- VV: Volumen (1 a 4 dígitos)\n'
                '- EEEE: Entrada (1 a 6 dígitos)\n\n'
                'Ejemplo válido: N-19-473'
            )

    def _validate_ruc_natural_foreign(self, ruc):
        """
        Valida RUC de extranjero con domicilio legal en Panamá.
        Formato: E-P-NNNNN
        - P: Provincia donde se originó la solicitud (1-13)
        - NNNNN: Número de orden de entrada
        Ejemplo: E-8-74258
        """
        pattern = re.compile(r'^E-([1-9]|1[0-3])-(\d{1,6})$', re.IGNORECASE)
        match = pattern.match(ruc)
        
        if not match:
            raise ValidationError(
                'Formato de RUC incorrecto para Extranjero con domicilio legal.\n\n'
                'Formato válido: E-P-NNNNN\n'
                '- P: Provincia (1-13)\n'
                '- NNNNN: Número de orden (1 a 6 dígitos)\n\n'
                'Ejemplo válido: E-8-74258'
            )
        
        provincia = int(match.group(1))
        if provincia < 1 or provincia > 13:
            raise ValidationError(
                f'Código de provincia inválido: {provincia}\n'
                'Las provincias válidas son del 1 al 13.'
            )

    def _validate_ruc_legal_commercial(self, ruc):
        """
        Valida RUC de Persona Jurídica - Sociedad Comercial (Tipo 2).
        Formato (post 2014): FFFFFFFFF-2-YYYY
        - FFFFFFFFF: Folio Real (9 dígitos consecutivos)
        - 2: Identificador de sociedad comercial
        - YYYY: Año de registro
        
        Incluye: Sociedad Anónima, Sociedad Limitada, Sociedad en Comandita por Acciones,
        Sociedad en Comandita Simple, Sucursales o Agencias de Empresas Extranjeras,
        Sociedades Colectivas.
        
        Ejemplo: 155986022-2-2019
        
        También acepta formato antiguo (pre-1985) con estructura más flexible.
        """
        # Formato nuevo (post Q3 2014) - 9 dígitos-2-año
        pattern_new = re.compile(r'^(\d{9})-2-(\d{4})$')
        # Formato antiguo (pre 1985) - más flexible, acepta cualquier combinación de dígitos
        pattern_old = re.compile(r'^(\d{1,9})-(\d{1,4})-(\d{1,9})$')
        
        if pattern_new.match(ruc):
            match = pattern_new.match(ruc)
            year = int(match.group(2))
            if year < 2014 or year > 2100:
                raise ValidationError(
                    f'Año de registro inválido: {year}\n'
                    'Para el formato nuevo (FFFFFFFFF-2-YYYY), el año debe ser 2014 o posterior.'
                )
        elif pattern_old.match(ruc):
            # Formato antiguo válido - acepta cualquier estructura de dígitos separados por guiones
            pass
        else:
            raise ValidationError(
                'Formato de RUC incorrecto para Sociedad Comercial (Tipo 2).\n\n'
                'Formato nuevo (desde 2014): FFFFFFFFF-2-YYYY\n'
                '- FFFFFFFFF: Folio Real de 9 dígitos\n'
                '- 2: Tipo de sociedad comercial\n'
                '- YYYY: Año de registro (2014 o posterior)\n\n'
                'Formato antiguo (pre-1985): NNNN-NNN-NNNNNN\n\n'
                'Ejemplos válidos: 155986022-2-2019, 4789-321-1515'
            )

    def _validate_ruc_legal_non_commercial(self, ruc):
        """
        Valida RUC de Persona Jurídica - Institución No Comercial (Tipo 3).
        Formato (post 2014): FFFFFFFF-3-YYYY
        - FFFFFFFF: Folio Real (8 dígitos consecutivos)
        - 3: Identificador de institución no comercial
        - YYYY: Año de registro
        
        Incluye: Fundaciones de Interés Privado, Asociaciones sin Fines de Lucro,
        Sociedades Civiles.
        
        Ejemplo: 26631254-3-2020
        
        También acepta formato antiguo (pre-1985) con estructura más flexible.
        """
        # Formato nuevo (post Q3 2014) - 8 dígitos-3-año
        pattern_new = re.compile(r'^(\d{8})-3-(\d{4})$')
        # Formato antiguo (pre 1985) - más flexible
        pattern_old = re.compile(r'^(\d{1,9})-(\d{1,4})-(\d{1,9})$')
        
        if pattern_new.match(ruc):
            match = pattern_new.match(ruc)
            year = int(match.group(2))
            if year < 2014 or year > 2100:
                raise ValidationError(
                    f'Año de registro inválido: {year}\n'
                    'Para el formato nuevo (FFFFFFFF-3-YYYY), el año debe ser 2014 o posterior.'
                )
        elif pattern_old.match(ruc):
            # Formato antiguo válido - acepta cualquier estructura de dígitos separados por guiones
            pass
        else:
            raise ValidationError(
                'Formato de RUC incorrecto para Institución No Comercial (Tipo 3).\n\n'
                'Formato nuevo (desde 2014): FFFFFFFF-3-YYYY\n'
                '- FFFFFFFF: Folio Real de 8 dígitos\n'
                '- 3: Tipo de institución no comercial\n'
                '- YYYY: Año de registro (2014 o posterior)\n\n'
                'Formato antiguo (pre-1985): NNNN-NNN-NNNNNN\n\n'
                'Ejemplos válidos: 26631254-3-2020, 123-45-678'
            )

    def _validate_ruc_tax_number(self, ruc):
        """
        Valida Número Tributario (NT).
        Para extranjeros residentes en Panamá que no pueden cumplir con los
        requisitos de registro de persona natural.
        
        Formato: P-NT-T-NN
        - P: Primer dígito (1 dígito)
        - NT: Identificador de número tributario
        - T: Tipo (1 dígito)
        - NN: Número secuencial (2 dígitos)
        
        Ejemplo: 3-NT-3-33
        """
        pattern = re.compile(r'^(\d{1})-NT-(\d{1})-(\d{2})$', re.IGNORECASE)
        if not pattern.match(ruc):
            raise ValidationError(
                'Formato de Número Tributario (NT) incorrecto.\n\n'
                'Formato válido: P-NT-T-NN\n'
                '- P: Primer dígito\n'
                '- NT: Identificador\n'
                '- T: Tipo (1 dígito)\n'
                '- NN: Número secuencial (2 dígitos)\n\n'
                'Ejemplo válido: 3-NT-3-33'
            )

    @api.constrains('ruc', 'is_panama')
    def _check_ruc_format(self):
        """Valida el formato del RUC panameño según su tipo"""
        for partner in self:
            # Solo validar si es de Panamá y tiene RUC
            if not partner.is_panama or not partner.ruc:
                continue
            
            ruc_clean = partner.ruc.upper().strip()
            
            try:
                # Detectar y validar según el tipo de RUC - orden importa!
                if ruc_clean.startswith('PE-'):
                    partner._validate_ruc_natural_foreign_born(ruc_clean)
                elif ruc_clean.startswith('N-'):
                    partner._validate_ruc_natural_naturalized(ruc_clean)
                elif ruc_clean.startswith('E-'):
                    partner._validate_ruc_natural_foreign(ruc_clean)
                elif '-NT-' in ruc_clean:
                    partner._validate_ruc_tax_number(ruc_clean)
                elif re.match(r'^\d{9}-2-\d{4}$', ruc_clean):
                    # Formato nuevo sociedad comercial - 9 dígitos exactos
                    partner._validate_ruc_legal_commercial(ruc_clean)
                elif re.match(r'^\d{8}-3-\d{4}$', ruc_clean):
                    # Formato nuevo institución no comercial - 8 dígitos exactos
                    partner._validate_ruc_legal_non_commercial(ruc_clean)
                elif re.match(r'^([1-9]|1[0-3])-\d+-\d+$', ruc_clean):
                    # Persona natural panameña por nacimiento
                    partner._validate_ruc_natural_national(ruc_clean)
                elif re.match(r'^\d+-\d+-\d+$', ruc_clean):
                    # Posible formato antiguo de persona jurídica o provincia inválida
                    # Verificar que no sea una provincia inválida (0, 14+)
                    first_part = ruc_clean.split('-')[0]
                    second_part = ruc_clean.split('-')[1]
                    
                    # Si tiene tipo 2 o 3 pero no cumple con formato nuevo exacto, rechazar
                    if second_part in ['2', '3']:
                        raise ValidationError(
                            f'Formato de RUC no reconocido: {partner.ruc}\n\n'
                            'Los RUCs con tipo 2 o 3 deben seguir el formato nuevo:\n'
                            '- Sociedad Comercial (tipo 2): FFFFFFFFF-2-YYYY (9 dígitos)\n'
                            '- Institución No Comercial (tipo 3): FFFFFFFF-3-YYYY (8 dígitos)\n\n'
                            f'El RUC proporcionado tiene {len(first_part)} dígitos antes del tipo.'
                        )
                    
                    # Si el primer dígito parece ser provincia, validar
                    if first_part.isdigit() and len(first_part) <= 2:
                        num = int(first_part)
                        if num == 0 or num > 13:
                            raise ValidationError(
                                f'Formato de RUC no reconocido: {partner.ruc}\n\n'
                                'Si intenta ingresar una Persona Natural Panameña, '
                                'la provincia debe estar entre 1 y 13.\n\n'
                                'Formatos válidos:\n'
                                '- Persona Natural: P-VV-EEEE donde P es 1-13 (ej: 8-926-1601)\n'
                                '- Formato antiguo empresa: NNNN-NNN-NNNNNN (ej: 4789-321-1515)'
                            )
                    # Si pasa todas las validaciones, es formato antiguo válido
                    pass
                else:
                    raise ValidationError(
                        f'Formato de RUC no reconocido: {partner.ruc}\n\n'
                        'Formatos válidos para Panamá:\n\n'
                        '1. Persona Natural Panameña: P-VV-EEEE (ej: 8-926-1601)\n'
                        '2. Panameño nacido en extranjero: PE-VV-EEEE (ej: PE-5-687)\n'
                        '3. Panameño naturalizado: N-VV-EEEE (ej: N-19-473)\n'
                        '4. Extranjero domiciliado: E-P-NNNNN (ej: E-8-74258)\n'
                        '5. Sociedad Comercial: FFFFFFFFF-2-YYYY (ej: 155986022-2-2019)\n'
                        '6. Institución No Comercial: FFFFFFFF-3-YYYY (ej: 26631254-3-2020)\n'
                        '7. Número Tributario: P-NT-T-NN (ej: 3-NT-3-33)\n'
                        '8. Formato antiguo (pre-1985): NNNN-NNN-NNNNNN (ej: 4789-321-1515)'
                    )
            except ValidationError:
                raise

    # Comentado temporalmente - configurar RUC manualmente después de instalación
    # @api.constrains('ruc', 'is_panama', 'company_type')
    # def _check_ruc_required(self):
    #     """Verifica que el RUC sea obligatorio para empresas panameñas"""
    #     for partner in self:
    #         if partner.is_panama and partner.company_type == 'company' and not partner.ruc:
    #             raise ValidationError(
    #                 'El RUC es obligatorio para empresas de Panamá.'
    #             )

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
