# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError
from lxml import etree


@tagged('l10n_ve_full')
class TestResPartnerVenezuela(TransactionCase):
    """Tests para la localización venezolana - Campo RIF e is_venezuela"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_ve = cls.env.ref('base.ve')
        cls.country_pa = cls.env.ref('base.pa')
        cls.country_us = cls.env.ref('base.us')

    def test_is_venezuela_computed_for_ve_partner(self):
        """Test que is_venezuela es True para partners de Venezuela"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner Venezuela',
            'country_id': self.country_ve.id,
        })
        self.assertTrue(partner.is_venezuela)

    def test_is_venezuela_computed_for_non_ve_partner(self):
        """Test que is_venezuela es False para partners de otros países"""
        partner_pa = self.env['res.partner'].create({
            'name': 'Test Partner Panama',
            'country_id': self.country_pa.id,
        })
        self.assertFalse(partner_pa.is_venezuela)

        partner_us = self.env['res.partner'].create({
            'name': 'Test Partner USA',
            'country_id': self.country_us.id,
        })
        self.assertFalse(partner_us.is_venezuela)

    def test_is_venezuela_updated_on_country_change(self):
        """Test que is_venezuela se actualiza cuando cambia el país"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'country_id': self.country_ve.id,
        })
        self.assertTrue(partner.is_venezuela)

        partner.country_id = self.country_pa.id
        self.assertFalse(partner.is_venezuela)

    def test_rif_syncs_to_vat(self):
        """RIF es related a VAT y debe persistir el mismo valor."""
        partner = self.env['res.partner'].create({
            'name': 'Test Company Venezuela',
            'country_id': self.country_ve.id,
            'company_type': 'company',
            'people_type_company': 'pjdo',
            'rif': 'J012345678',
        })
        self.assertEqual(partner.vat, 'J012345678')

    def test_ve_company_rif_required_for_pjdo(self):
        """En VE, compañías PJDO deben tener RIF (vat)"""
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'VE Company Missing RIF',
                'country_id': self.country_ve.id,
                'company_type': 'company',
                'people_type_company': 'pjdo',
                'vat': '',
            })

    def test_ve_company_rif_not_required_for_pjnd(self):
        """En VE, PJND no requiere RIF (según reglas de vista/documentación)."""
        partner = self.env['res.partner'].create({
            'name': 'VE Company PJND No RIF',
            'country_id': self.country_ve.id,
            'company_type': 'company',
            'people_type_company': 'pjnd',
        })
        self.assertFalse(partner.vat)

    def test_ve_company_rif_format_valid(self):
        """Formato válido: letra VEJGC + 9 dígitos (sin guiones)."""
        partner = self.env['res.partner'].create({
            'name': 'VE Company Valid RIF',
            'country_id': self.country_ve.id,
            'company_type': 'company',
            'people_type_company': 'pjdo',
            'rif': 'G123456789',
        })
        self.assertEqual(partner.vat, 'G123456789')

    def test_ve_company_rif_format_invalid_letter(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'VE Company Invalid RIF Letter',
                'country_id': self.country_ve.id,
                'company_type': 'company',
                'people_type_company': 'pjdo',
                'rif': 'X123456789',
            })

    def test_ve_company_rif_format_invalid_length(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'VE Company Invalid RIF Length',
                'country_id': self.country_ve.id,
                'company_type': 'company',
                'people_type_company': 'pjdo',
                'rif': 'J123',
            })

    def test_ve_person_vat_document_format_valid(self):
        partner = self.env['res.partner'].create({
            'name': 'VE Person Valid Doc',
            'country_id': self.country_ve.id,
            'company_type': 'person',
            'vat': 'V12345678',
        })
        self.assertEqual(partner.vat, 'V12345678')

    def test_ve_person_vat_document_format_invalid(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'VE Person Invalid Doc',
                'country_id': self.country_ve.id,
                'company_type': 'person',
                'vat': 'J012345678',
            })

    def test_is_venezuela_false_without_country(self):
        """Test que is_venezuela es False cuando no hay país asignado"""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner No Country',
            'company_type': 'company',
            'country_id': self.country_us.id,
        })
        # Forzar que no tenga país (puede haber default en DB)
        partner.country_id = False
        self.assertFalse(partner.is_venezuela)

    def test_ve_only_identity_fields_cleared_on_create_non_ve(self):
        """Si el país no es VE, estos campos deben quedar nulos por defecto."""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner Panama Identity Cleared',
            'company_type': 'person',
            'country_id': self.country_pa.id,
            'people_type_individual': 'pnre',
            'nationality': 'V',
            'identification_id': '19763505',
        })
        self.assertFalse(partner.people_type_individual)
        self.assertFalse(partner.nationality)
        self.assertFalse(partner.identification_id)

    def test_ve_only_identity_fields_kept_on_create_ve(self):
        """Si el país es VE, debe permitirse guardar los valores."""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner VE Identity Kept',
            'company_type': 'person',
            'country_id': self.country_ve.id,
            'people_type_individual': 'pnre',
            'nationality': 'V',
            'identification_id': '19763505',
        })
        self.assertEqual(partner.people_type_individual, 'pnre')
        self.assertEqual(partner.nationality, 'V')
        self.assertEqual(partner.identification_id, '19763505')

    def test_ve_only_identity_fields_cleared_on_country_change(self):
        """Al cambiar de VE a otro país, se limpian los campos."""
        partner = self.env['res.partner'].create({
            'name': 'Test Partner VE To PA',
            'company_type': 'person',
            'country_id': self.country_ve.id,
            'people_type_individual': 'pnre',
            'nationality': 'V',
            'identification_id': '19763505',
        })
        partner.write({'country_id': self.country_pa.id})
        self.assertFalse(partner.people_type_individual)
        self.assertFalse(partner.nationality)
        self.assertFalse(partner.identification_id)

    def test_partner_view_has_ve_visibility_rules(self):
        """La vista debe ocultar los campos cuando no sea Venezuela."""
        view = self.env.ref('l10n_ve_full.extra_partner_venezuela')
        arch = view.arch_db
        self.assertIn("name=\"people_type_individual\"", arch)
        self.assertIn("or not is_venezuela", arch)
        self.assertIn("name=\"nationality\"", arch)
        self.assertIn("name=\"identification_id\"", arch)

    def test_company_context_sets_vat_label_to_rif(self):
        """En contexto de compañía VE, el VAT debe rotularse como RIF en la vista."""
        company = self.env.company
        original_country = company.country_id
        try:
            company.country_id = self.country_ve
            base_form_view = self.env.ref('base.view_partner_form')
            arch, _view = self.env['res.partner']._get_view(view_id=base_form_view.id, view_type='form')
            arch_str = etree.tostring(arch, encoding='unicode')
            self.assertIn('string="RIF"', arch_str)
            self.assertIn('placeholder="Ej.: J-01234567-8"', arch_str)
        finally:
            company.country_id = original_country

    def test_ve_partners_empty_vat_no_duplicate_error(self):
        """Two VE partners with empty vat should NOT raise duplicate error (False == False fix)."""
        self.env['res.partner'].create({
            'name': 'Partner A Sin RIF',
            'country_id': self.country_ve.id,
            'company_type': 'person',
        })
        # This should NOT raise ValidationError
        partner_b = self.env['res.partner'].create({
            'name': 'Partner B Sin RIF',
            'country_id': self.country_ve.id,
            'company_type': 'person',
        })
        self.assertFalse(partner_b.vat)

    def test_ve_duplicate_vat_raises_error(self):
        """Two VE partners with the same vat SHOULD raise ValidationError."""
        self.env['res.partner'].create({
            'name': 'Partner Original',
            'country_id': self.country_ve.id,
            'company_type': 'person',
            'vat': 'V12345678',
        })
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'Partner Duplicado',
                'country_id': self.country_ve.id,
                'company_type': 'person',
                'vat': 'V12345678',
            })

    def test_ve_edit_partner_no_false_duplicate(self):
        """Editing a VE partner without changing vat should NOT raise duplicate error."""
        partner = self.env['res.partner'].create({
            'name': 'Partner Editable',
            'country_id': self.country_ve.id,
            'company_type': 'company',
            'people_type_company': 'pjdo',
            'vat': 'J999888777',
        })
        # Editing the name should not trigger a false duplicate
        partner.write({'name': 'Partner Editado'})


@tagged('l10n_ve_full')
class TestResCompanyVenezuela(TransactionCase):
    """Tests para res.company - Campo is_venezuela"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_ve = cls.env.ref('base.ve')
        cls.country_pa = cls.env.ref('base.pa')

    def test_company_is_venezuela_computed(self):
        """Test que is_venezuela se computa correctamente en res.company"""
        # Usar la compañía actual y cambiar su país temporalmente
        company = self.env.company
        original_country = company.partner_id.country_id
        
        # Cambiar a Venezuela
        company.partner_id.country_id = self.country_ve
        company._compute_is_venezuela()
        self.assertTrue(company.is_venezuela)
        
        # Restaurar país original
        company.partner_id.country_id = original_country

    def test_company_is_venezuela_false_for_panama(self):
        """Test que is_venezuela es False para empresas de otros países"""
        # Usar la compañía actual y cambiar su país temporalmente
        company = self.env.company
        original_country = company.partner_id.country_id
        
        # Cambiar a Panamá
        company.partner_id.country_id = self.country_pa
        company._compute_is_venezuela()
        self.assertFalse(company.is_venezuela)
        
        # Restaurar país original
        company.partner_id.country_id = original_country


@tagged('l10n_ve_full')
class TestSaleOrderVenezuela(TransactionCase):
    """Tests para sale.order - Campo is_venezuela relacionado"""
    # Nota: Estos tests requieren warehouse_id y otros datos que varían según la configuración.
    # Se prueban manualmente o en tests de integración.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_ve = cls.env.ref('base.ve')
        cls.country_pa = cls.env.ref('base.pa')

    def test_sale_order_is_venezuela_field_exists(self):
        """Test que el campo is_venezuela existe en sale.order"""
        self.assertIn('is_venezuela', self.env['sale.order']._fields)


@tagged('l10n_ve_full')
class TestPurchaseOrderVenezuela(TransactionCase):
    """Tests para purchase.order - Campo is_venezuela relacionado"""
    # Nota: Estos tests requieren documento fiscal y otros datos que varían según la configuración.
    # Se prueban manualmente o en tests de integración.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_ve = cls.env.ref('base.ve')
        cls.country_pa = cls.env.ref('base.pa')

    def test_purchase_order_is_venezuela_field_exists(self):
        """Test que el campo is_venezuela existe en purchase.order"""
        self.assertIn('is_venezuela', self.env['purchase.order']._fields)
