# -*- coding: utf-8 -*-
from odoo.tests import common
from odoo.exceptions import ValidationError
from lxml import etree


class TestResPartnerPanama(common.TransactionCase):
    """Tests para validación de RUC panameño"""

    def setUp(self):
        super().setUp()
        self.panama = self.env.ref('base.pa')
        self.partner_obj = self.env['res.partner']

    def _create_partner_panama(self, ruc, ruc_type='natural', name='Test Partner'):
        """Helper para crear un partner de Panamá"""
        return self.partner_obj.with_context(skip_check_vat=True).create({
            'name': name,
            'country_id': self.panama.id,
            'ruc': ruc,
            'ruc_type': ruc_type,
        })

    # ===== TESTS PERSONAS NATURALES - NUEVOS FORMATOS =====
    
    def test_ruc_natural_new_format_valid(self):
        """RUC válido de persona natural con nuevo formato"""
        # Panameños por nacimiento
        partner = self._create_partner_panama('8-123-4567', 'natural')
        self.assertEqual(partner.ruc, '8-123-4567')
        self.assertEqual(partner.vat, '8-123-4567')

    def test_ruc_natural_with_leading_zero(self):
        """RUC con cero inicial en provincia"""
        partner = self._create_partner_panama('08-123-4567', 'natural')
        self.assertEqual(partner.ruc, '08-123-4567')

    def test_ruc_natural_pi_type(self):
        """RUC con tipo PI"""
        partner = self._create_partner_panama('13-PI-12345', 'natural')
        self.assertEqual(partner.ruc, '13-PI-12345')

    def test_ruc_natural_av_type(self):
        """RUC con tipo AV"""
        partner = self._create_partner_panama('1-AV-1', 'natural')
        self.assertEqual(partner.ruc, '1-AV-1')

    def test_ruc_natural_nt_type(self):
        """RUC con tipo NT (nacido en extranjero)"""
        partner = self._create_partner_panama('8-NT-12345', 'natural')
        self.assertEqual(partner.ruc, '8-NT-12345')

    def test_ruc_natural_n_type(self):
        """RUC con tipo N (naturalizado)"""
        partner = self._create_partner_panama('8-N-12345', 'natural')
        self.assertEqual(partner.ruc, '8-N-12345')

    def test_ruc_natural_pe_type(self):
        """RUC con tipo PE (extranjero)"""
        partner = self._create_partner_panama('8-PE-12345', 'natural')
        self.assertEqual(partner.ruc, '8-PE-12345')

    def test_ruc_natural_e_type(self):
        """RUC con tipo E (extranjero)"""
        partner = self._create_partner_panama('8-E-12345', 'natural')
        self.assertEqual(partner.ruc, '8-E-12345')

    # ===== TESTS PERSONAS NATURALES - FORMATO ANTIGUO =====

    def test_ruc_natural_old_format_valid(self):
        """RUC válido de persona natural con formato antiguo"""
        partner = self._create_partner_panama('8-123-456', 'natural')
        self.assertEqual(partner.ruc, '8-123-456')

    def test_ruc_natural_old_format_minimal(self):
        """RUC formato antiguo mínimo"""
        partner = self._create_partner_panama('1-1-1', 'natural')
        self.assertEqual(partner.ruc, '1-1-1')

    def test_ruc_natural_old_format_maximal(self):
        """RUC formato antiguo máximo"""
        partner = self._create_partner_panama('13-9999-999999', 'natural')
        self.assertEqual(partner.ruc, '13-9999-999999')

    # ===== TESTS PERSONAS NATURALES - FORMATOS INVÁLIDOS =====

    def test_ruc_natural_invalid_province_zero(self):
        """RUC con provincia 0 debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('0-123-456', 'natural')

    def test_ruc_natural_invalid_province_14(self):
        """RUC con provincia 14 debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('14-123-456', 'natural')

    def test_ruc_natural_invalid_province_15(self):
        """RUC con provincia 15 en nuevo formato debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('15-PI-12345', 'natural')

    def test_ruc_natural_invalid_type_xx(self):
        """RUC con tipo inválido XX debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('8-XX-12345', 'natural')

    def test_ruc_natural_incomplete(self):
        """RUC incompleto debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('8-123-', 'natural')

    def test_ruc_natural_no_dashes(self):
        """RUC sin guiones debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('8123456', 'natural')

    # ===== TESTS PERSONAS JURÍDICAS - VÁLIDOS =====

    def test_ruc_juridica_type_2_valid(self):
        """RUC válido de persona jurídica tipo 2 (comercial)"""
        partner = self._create_partner_panama('155777-2-2019', 'juridica')
        self.assertEqual(partner.ruc, '155777-2-2019')
        self.assertEqual(partner.vat, '155777-2-2019')

    def test_ruc_juridica_type_2_min_length(self):
        """RUC jurídica tipo 2 con longitud mínima"""
        partner = self._create_partner_panama('1234-2-123456', 'juridica')
        self.assertEqual(partner.ruc, '1234-2-123456')

    def test_ruc_juridica_type_2_max_length(self):
        """RUC jurídica tipo 2 con longitud máxima"""
        partner = self._create_partner_panama('123456-2-1234', 'juridica')
        self.assertEqual(partner.ruc, '123456-2-1234')

    def test_ruc_juridica_type_3_valid(self):
        """RUC válido de persona jurídica tipo 3 (no comercial)"""
        partner = self._create_partner_panama('98765-3-54321', 'juridica')
        self.assertEqual(partner.ruc, '98765-3-54321')

    def test_ruc_juridica_type_3_valid_2(self):
        """RUC válido de persona jurídica tipo 3 con longitud máxima"""
        partner = self._create_partner_panama('1234-3-123456', 'juridica')
        self.assertEqual(partner.ruc, '1234-3-123456')

    # ===== TESTS PERSONAS JURÍDICAS - INVÁLIDOS =====

    def test_ruc_juridica_short_folio(self):
        """RUC jurídica con folio muy corto debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('123-2-2019', 'juridica')

    def test_ruc_juridica_long_folio(self):
        """RUC jurídica con folio muy largo debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('1234567-2-2019', 'juridica')

    def test_ruc_juridica_short_asiento(self):
        """RUC jurídica con asiento muy corto debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('1234-2-123', 'juridica')

    def test_ruc_juridica_long_asiento(self):
        """RUC jurídica con asiento muy largo debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('1234-2-1234567', 'juridica')

    def test_ruc_juridica_invalid_type_5(self):
        """RUC jurídica con tipo inválido 5 debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('1234-5-123456', 'juridica')

    def test_ruc_juridica_10_digits_folio(self):
        """RUC jurídica con 10 dígitos en folio debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('1234567890-2-2019', 'juridica')

    def test_ruc_juridica_9_digits_folio(self):
        """RUC jurídica con 9 dígitos en folio debe fallar"""
        with self.assertRaises(ValidationError):
            self._create_partner_panama('123456789-3-2020', 'juridica')

    # ===== TESTS FUNCIONALIDAD GENERAL =====

    def test_vat_synchronization_create(self):
        """VAT debe sincronizarse automáticamente en create"""
        partner = self._create_partner_panama('8-123-4567', 'natural')
        self.assertEqual(partner.vat, '8-123-4567')

    def test_vat_synchronization_write(self):
        """VAT debe sincronizarse automáticamente en write"""
        partner = self._create_partner_panama('8-123-4567', 'natural')
        partner.write({'ruc': '8-456-7890'})
        self.assertEqual(partner.vat, '8-456-7890')

    def test_is_panama_computed(self):
        """Campo is_panama debe computarse correctamente"""
        partner = self.partner_obj.create({
            'name': 'Test Partner',
            'country_id': self.panama.id,
        })
        self.assertTrue(partner.is_panama)

    def test_ruc_not_required_when_not_panama(self):
        """RUC no debe ser obligatorio si el país no es Panamá"""
        usa = self.env.ref('base.us')
        partner = self.partner_obj.create({
            'name': 'US Partner',
            'country_id': usa.id,
        })
        self.assertFalse(partner.is_panama)
        # No debería fallar sin RUC

    def test_company_context_sets_vat_label_to_ruc(self):
        """En contexto de compañía PA, el VAT debe rotularse como RUC en la vista."""
        company = self.env.company
        original_country = company.country_id
        try:
            company.country_id = self.panama
            base_form_view = self.env.ref('base.view_partner_form')
            arch, _view = self.env['res.partner']._get_view(view_id=base_form_view.id, view_type='form')
            arch_str = etree.tostring(arch, encoding='unicode')
            self.assertIn('string="RUC"', arch_str)
            self.assertIn('placeholder="Ej.: 8-926-1601 / 155986022-2-2019 / PE-5-687"', arch_str)
        finally:
            company.country_id = original_country
