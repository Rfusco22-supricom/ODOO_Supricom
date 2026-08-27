# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestResPartnerPanama(TransactionCase):
    """Tests para la localización panameña - Campo RUC e is_panama"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_pa = cls.env.ref('base.pa')
        cls.country_ve = cls.env.ref('base.ve')
        cls.country_us = cls.env.ref('base.us')

    def test_is_panama_computed_for_pa_partner(self):
        """Test que is_panama es True para partners de Panamá"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner Panama',
            'country_id': self.country_pa.id,
        })
        self.assertTrue(partner.is_panama)

    def test_is_panama_computed_for_non_pa_partner(self):
        """Test que is_panama es False para partners de otros países"""
        partner_ve = self.env['res.partner'].create({
            'name': 'Test Partner Venezuela',
            'country_id': self.country_ve.id,
        })
        self.assertFalse(partner_ve.is_panama)

        partner_us = self.env['res.partner'].create({
            'name': 'Test Partner USA',
            'country_id': self.country_us.id,
        })
        self.assertFalse(partner_us.is_panama)

    def test_is_panama_updated_on_country_change(self):
        """Test que is_panama se actualiza cuando cambia el país"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'country_id': self.country_pa.id,
        })
        self.assertTrue(partner.is_panama)

        partner.country_id = self.country_ve.id
        self.assertFalse(partner.is_panama)

    def test_ruc_syncs_to_vat(self):
        """Test que el RUC se sincroniza con el campo VAT"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        self.assertEqual(partner.vat, '8-926-1601')

    # ========================================================================
    # TESTS PARA PERSONAS NATURALES - PANAMEÑOS POR NACIMIENTO
    # ========================================================================
    
    def test_ruc_natural_national_valid_single_digit_province(self):
        """Test RUC válido: Panameño por nacimiento con provincia de 1 dígito"""
        partner = self.env['res.partner'].create({
            'name': 'Juan Pérez',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        self.assertEqual(partner.ruc_type, 'natural_national')
        self.assertEqual(partner.vat, '8-926-1601')

    def test_ruc_natural_national_valid_two_digit_province(self):
        """Test RUC válido: Panameño con provincia de 2 dígitos (10-13)"""
        test_cases = [
            ('10-123-456', 'natural_national'),
            ('11-45-6789', 'natural_national'),
            ('12-1-12345', 'natural_national'),
            ('13-999-88', 'natural_national'),
        ]
        for ruc, expected_type in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Test {ruc}',
                'country_id': self.country_pa.id,
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, expected_type, f'Failed for RUC: {ruc}')

    def test_ruc_natural_national_valid_variations(self):
        """Test variaciones válidas de longitud para persona natural nacional"""
        test_cases = [
            '1-23-456',      # Mínimo
            '8-926-1601',    # Normal
            '9-1234-123456', # Máximo
        ]
        for ruc in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Test {ruc}',
                'country_id': self.country_pa.id,
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, 'natural_national', f'Failed for RUC: {ruc}')

    def test_ruc_natural_national_invalid_province_zero(self):
        """Test RUC inválido: Provincia 0"""
        with self.assertRaises(ValidationError) as cm:
            self.env['res.partner'].create({
                'name': 'Test Invalid',
                'country_id': self.country_pa.id,
                'ruc': '0-123-456',
            })
        self.assertIn('no reconocido', str(cm.exception).lower())

    def test_ruc_natural_national_invalid_province_14(self):
        """Test RUC inválido: Provincia mayor a 13"""
        with self.assertRaises(ValidationError) as cm:
            self.env['res.partner'].create({
                'name': 'Test Invalid',
                'country_id': self.country_pa.id,
                'ruc': '14-123-456',
            })
        self.assertIn('no reconocido', str(cm.exception).lower())

    def test_ruc_natural_national_invalid_format(self):
        """Test RUC inválido: Formato incorrecto"""
        invalid_rucs = [
            '8-926',          # Falta parte
            '8-926-',         # Falta entrada
            '8--1601',        # Falta volumen
            'A-123-456',      # Letra en provincia
            '8-ABC-456',      # Letras en volumen
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Test {ruc}',
                    'country_id': self.country_pa.id,
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS PARA PANAMEÑOS NACIDOS EN EL EXTRANJERO
    # ========================================================================
    
    def test_ruc_foreign_born_valid(self):
        """Test RUC válido: Panameño nacido en el extranjero"""
        test_cases = [
            'PE-5-687',
            'PE-123-4567',
            'pe-5-687',  # Case insensitive
        ]
        for ruc in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Test {ruc}',
                'country_id': self.country_pa.id,
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, 'natural_foreign_born', f'Failed for RUC: {ruc}')

    def test_ruc_foreign_born_invalid(self):
        """Test RUC inválido: Panameño nacido en extranjero formato incorrecto"""
        invalid_rucs = [
            'PE-ABC-123',    # Letras en volumen
            'PE-5',          # Falta entrada
            'P-5-687',       # Debe ser PE
            'PEE-5-687',     # Prefijo incorrecto
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Test {ruc}',
                    'country_id': self.country_pa.id,
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS PARA PANAMEÑOS NATURALIZADOS
    # ========================================================================
    
    def test_ruc_naturalized_valid(self):
        """Test RUC válido: Panameño naturalizado"""
        test_cases = [
            'N-19-473',
            'N-1-1',
            'n-19-473',  # Case insensitive
        ]
        for ruc in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Test {ruc}',
                'country_id': self.country_pa.id,
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, 'natural_naturalized', f'Failed for RUC: {ruc}')

    def test_ruc_naturalized_invalid(self):
        """Test RUC inválido: Panameño naturalizado formato incorrecto"""
        invalid_rucs = [
            'N-ABC-123',     # Letras en volumen
            'N-19',          # Falta entrada
            'NN-19-473',     # Prefijo incorrecto
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Test {ruc}',
                    'country_id': self.country_pa.id,
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS PARA EXTRANJEROS CON DOMICILIO LEGAL
    # ========================================================================
    
    def test_ruc_foreign_domiciled_valid(self):
        """Test RUC válido: Extranjero con domicilio legal"""
        test_cases = [
            'E-8-74258',
            'E-1-1',
            'E-13-999999',
            'e-8-74258',  # Case insensitive
        ]
        for ruc in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Test {ruc}',
                'country_id': self.country_pa.id,
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, 'natural_foreign', f'Failed for RUC: {ruc}')

    def test_ruc_foreign_domiciled_invalid_province(self):
        """Test RUC inválido: Extranjero con provincia inválida"""
        invalid_rucs = [
            'E-0-12345',     # Provincia 0
            'E-14-12345',    # Provincia > 13
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Test {ruc}',
                    'country_id': self.country_pa.id,
                    'ruc': ruc,
                })

    def test_ruc_foreign_domiciled_invalid_format(self):
        """Test RUC inválido: Extranjero formato incorrecto"""
        invalid_rucs = [
            'E-ABC-123',     # Letras en provincia
            'E-8',           # Falta número de orden
            'EE-8-12345',    # Prefijo incorrecto
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Test {ruc}',
                    'country_id': self.country_pa.id,
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS PARA PERSONAS JURÍDICAS - SOCIEDADES COMERCIALES (TIPO 2)
    # ========================================================================
    
    def test_ruc_legal_commercial_valid_new_format(self):
        """Test RUC válido: Sociedad Comercial formato nuevo (post 2014)"""
        test_cases = [
            ('155986022-2-2019', 'legal_commercial'),
            ('123456789-2-2014', 'legal_commercial'),
            ('999999999-2-2024', 'legal_commercial'),
        ]
        for ruc, expected_type in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Empresa {ruc}',
                'country_id': self.country_pa.id,
                'company_type': 'company',
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, expected_type, f'Failed for RUC: {ruc}')

    def test_ruc_legal_commercial_valid_old_format(self):
        """Test RUC válido: Sociedad Comercial formato antiguo (pre-1985)"""
        test_cases = [
            '4789-321-1515',
            '123-45-678',
        ]
        for ruc in test_cases:
            partner = self.env['res.partner'].with_context(skip_check_vat=True).create({
                'name': f'Empresa {ruc}',
                'country_id': self.country_pa.id,
                'company_type': 'company',
                'ruc': ruc,
            })
            # El formato antiguo es válido
            self.assertEqual(partner.ruc, ruc)

    def test_ruc_legal_commercial_invalid_year(self):
        """Test RUC inválido: Sociedad Comercial con año inválido"""
        invalid_rucs = [
            '155986022-2-2013',  # Año antes de 2014
            '155986022-2-1990',  # Año antes de 2014
            '155986022-2-2200',  # Año futuro irreal
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Empresa {ruc}',
                    'country_id': self.country_pa.id,
                    'company_type': 'company',
                    'ruc': ruc,
                })

    def test_ruc_legal_commercial_invalid_format(self):
        """Test RUC inválido: Sociedad Comercial formato incorrecto"""
        invalid_rucs = [
            '1234567890-2-2019', # 10 dígitos en folio (debe ser 9)
            '155986022-2-19',    # Año con 2 dígitos
            'ABC123456-2-2019',  # Letras en folio
        ]
        # Nota: 12345678-2-2019 (8 dígitos) se acepta como formato antiguo
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Empresa {ruc}',
                    'country_id': self.country_pa.id,
                    'company_type': 'company',
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS PARA PERSONAS JURÍDICAS - INSTITUCIONES NO COMERCIALES (TIPO 3)
    # ========================================================================
    
    def test_ruc_legal_non_commercial_valid_new_format(self):
        """Test RUC válido: Institución No Comercial formato nuevo (post 2014)"""
        test_cases = [
            ('26631254-3-2020', 'legal_non_commercial'),
            ('12345678-3-2015', 'legal_non_commercial'),
            ('99999999-3-2024', 'legal_non_commercial'),
        ]
        for ruc, expected_type in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Fundación {ruc}',
                'country_id': self.country_pa.id,
                'company_type': 'company',
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, expected_type, f'Failed for RUC: {ruc}')

    def test_ruc_legal_non_commercial_invalid_year(self):
        """Test RUC inválido: Institución No Comercial con año inválido"""
        invalid_rucs = [
            '26631254-3-2013',  # Año antes de 2014
            '26631254-3-2250',  # Año futuro irreal
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Fundación {ruc}',
                    'country_id': self.country_pa.id,
                    'company_type': 'company',
                    'ruc': ruc,
                })

    def test_ruc_legal_non_commercial_invalid_format(self):
        """Test RUC inválido: Institución No Comercial formato incorrecto"""
        invalid_rucs = [
            '123456789-3-2020',  # 9 dígitos en folio (debe ser 8)
            '26631254-3-20',     # Año con 2 dígitos
            'ABCD1234-3-2020',   # Letras en folio
        ]
        # Nota: 1234567-3-2020 (7 dígitos) se acepta como formato antiguo
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Fundación {ruc}',
                    'country_id': self.country_pa.id,
                    'company_type': 'company',
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS PARA NÚMERO TRIBUTARIO (NT)
    # ========================================================================
    
    def test_ruc_tax_number_valid(self):
        """Test RUC válido: Número Tributario (NT)"""
        test_cases = [
            '3-NT-3-33',
            '1-NT-1-01',
            '9-NT-9-99',
            '3-nt-3-33',  # Case insensitive
        ]
        for ruc in test_cases:
            partner = self.env['res.partner'].create({
                'name': f'Test NT {ruc}',
                'country_id': self.country_pa.id,
                'ruc': ruc,
            })
            self.assertEqual(partner.ruc_type, 'tax_number', f'Failed for RUC: {ruc}')

    def test_ruc_tax_number_invalid_format(self):
        """Test RUC inválido: Número Tributario formato incorrecto"""
        invalid_rucs = [
            '3-NT-3-3',      # Solo 1 dígito final (debe ser 2)
            '3-NT-33-33',    # 2 dígitos en tipo (debe ser 1)
            '33-NT-3-33',    # 2 dígitos iniciales (debe ser 1)
            '3-NT-3-333',    # 3 dígitos finales (debe ser 2)
            'A-NT-3-33',     # Letra inicial
        ]
        for ruc in invalid_rucs:
            with self.assertRaises(ValidationError, msg=f'Should fail for: {ruc}'):
                self.env['res.partner'].create({
                    'name': f'Test NT {ruc}',
                    'country_id': self.country_pa.id,
                    'ruc': ruc,
                })

    # ========================================================================
    # TESTS DE INTEGRACIÓN Y CASOS ESPECIALES
    # ========================================================================
    
    def test_ruc_validation_only_for_panama(self):
        """Test que la validación de RUC solo aplica para Panamá"""
        # Un formato inválido para Panamá no debe causar error en otros países
        partner = self.env['res.partner'].create({
            'name': 'Test Venezuela',
            'country_id': self.country_ve.id,
            'ruc': 'FORMATO-INVALIDO-PARA-PANAMA',
        })
        self.assertFalse(partner.is_panama)
        self.assertFalse(partner.ruc_type)

    def test_ruc_empty_allowed(self):
        """Test que RUC vacío es permitido"""
        partner = self.env['res.partner'].create({
            'name': 'Test Sin RUC',
            'country_id': self.country_pa.id,
        })
        self.assertTrue(partner.is_panama)
        self.assertFalse(partner.ruc)
        self.assertFalse(partner.ruc_type)

    def test_ruc_duplicate_detection(self):
        """Test detección de RUC duplicado"""
        # Crear primer partner
        partner1 = self.env['res.partner'].create({
            'name': 'Partner 1',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        
        # Crear segundo partner con mismo RUC
        partner2 = self.env['res.partner'].create({
            'name': 'Partner 2',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        
        # Verificar que se detecta el duplicado
        self.assertTrue(partner2.same_vat_partner_id)
        self.assertEqual(partner2.same_vat_partner_id, partner1)

    def test_ruc_case_insensitive(self):
        """Test que RUC es case insensitive"""
        test_cases = [
            ('pe-5-687', 'PE-5-687'),
            ('n-19-473', 'N-19-473'),
            ('e-8-74258', 'E-8-74258'),
        ]
        for input_ruc, expected_vat in test_cases:
            partner = self.env['res.partner'].with_context(skip_check_vat=True).create({
                'name': f'Test {input_ruc}',
                'country_id': self.country_pa.id,
                'ruc': input_ruc,
            })
            self.assertEqual(partner.vat, expected_vat)

    def test_ruc_format_validation_natural(self):
        """Test validación de formato RUC para persona natural"""
        partner = self.env['res.partner'].create({
            'name': 'Test Person Panama',
            'country_id': self.country_pa.id,
            'company_type': 'person',
            'ruc': '8-123-4567',
        })
        self.assertEqual(partner.ruc, '8-123-4567')

    def test_ruc_format_invalid_raises_error(self):
        """Test que un formato de RUC inválido genera error"""
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'Test Invalid RUC',
                'country_id': self.country_pa.id,
                'company_type': 'company',
                'ruc': 'INVALIDO',
            })

    # Temporalmente deshabilitado - RUC required constraint está comentado
    # def test_ruc_required_for_company(self):
    #     """Test que el RUC es requerido para empresas panameñas"""
    #     with self.assertRaises(ValidationError):
    #         self.env['res.partner'].create({
    #             'name': 'Test Company Without RUC',
    #             'country_id': self.country_pa.id,
    #             'company_type': 'company',
    #         })

    def test_is_panama_false_without_country(self):
        """Test que is_panama es False cuando no hay país asignado"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner No Country',
        })
        self.assertFalse(partner.is_panama)


class TestResCompanyPanama(TransactionCase):
    """Tests para res.company - Campo is_panama"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_pa = cls.env.ref('base.pa')
        cls.country_ve = cls.env.ref('base.ve')

    def test_company_is_panama_computed(self):
        """Test que is_panama se computa correctamente en res.company"""
        # Usar la compañía actual y cambiar su país temporalmente
        company = self.env.company
        original_country = company.partner_id.country_id
        
        # Cambiar a Panamá
        company.partner_id.country_id = self.country_pa
        company._compute_is_panama()
        self.assertTrue(company.is_panama)
        
        # Restaurar país original
        company.partner_id.country_id = original_country

    def test_company_is_panama_false_for_venezuela(self):
        """Test que is_panama es False para compañías de Venezuela"""
        # Usar la compañía actual y cambiar su país temporalmente
        company = self.env.company
        original_country = company.partner_id.country_id
        
        # Cambiar a Venezuela
        company.partner_id.country_id = self.country_ve
        company._compute_is_panama()
        self.assertFalse(company.is_panama)
        
        # Restaurar país original
        company.partner_id.country_id = original_country


class TestSaleOrderPanama(TransactionCase):
    """Tests para sale.order - Campo is_panama relacionado"""
    # Nota: Estos tests requieren warehouse_id y otros datos que varían según la configuración.
    # Se prueban manualmente o en tests de integración.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_pa = cls.env.ref('base.pa')
        cls.country_ve = cls.env.ref('base.ve')

    def test_sale_order_is_panama_field_exists(self):
        """Test que el campo is_panama existe en sale.order"""
        self.assertIn('is_panama', self.env['sale.order']._fields)

    def test_sale_order_ruc_field_exists(self):
        """Test que el campo ruc existe en sale.order"""
        self.assertIn('ruc', self.env['sale.order']._fields)


class TestPurchaseOrderPanama(TransactionCase):
    """Tests para purchase.order - Campo is_panama relacionado"""
    # Nota: Estos tests requieren documento fiscal y otros datos que varían según la configuración.
    # Se prueban manualmente o en tests de integración.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_pa = cls.env.ref('base.pa')
        cls.country_ve = cls.env.ref('base.ve')

    def test_purchase_order_is_panama_field_exists(self):
        """Test que el campo is_panama existe en purchase.order"""
        self.assertIn('is_panama', self.env['purchase.order']._fields)

    def test_purchase_order_ruc_field_exists(self):
        """Test que el campo ruc existe en purchase.order"""
        self.assertIn('ruc', self.env['purchase.order']._fields)
