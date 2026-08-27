# -*- coding: utf-8 -*-
"""
Test de coexistencia entre localizaciones de Panamá y Venezuela.
Verifica que ambas localizaciones puedan funcionar simultáneamente sin conflictos.
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestPanamaVenezuelaCoexistence(TransactionCase):
    """Tests para verificar coexistencia de localizaciones PA y VE"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_pa = cls.env.ref('base.pa')
        cls.country_ve = cls.env.ref('base.ve')

    def test_panama_partner_does_not_affect_venezuela(self):
        """Verificar que crear partner panameño no afecta partners venezolanos"""
        # Crear partner de Venezuela
        partner_ve = self.env['res.partner'].create({
            'name': 'Cliente Venezuela',
            'country_id': self.country_ve.id,
            'identification_id': '12345678',
            'nationality': 'V',
        })
        self.assertTrue(partner_ve.is_venezuela)
        self.assertFalse(partner_ve.is_panama)
        
        # Crear partner de Panamá con RUC válido
        partner_pa = self.env['res.partner'].create({
            'name': 'Cliente Panamá',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        self.assertTrue(partner_pa.is_panama)
        self.assertFalse(partner_pa.is_venezuela)
        
        # Verificar que el partner venezolano no fue afectado
        partner_ve.refresh()
        self.assertTrue(partner_ve.is_venezuela)
        self.assertFalse(partner_ve.is_panama)

    def test_venezuela_partner_does_not_affect_panama(self):
        """Verificar que crear partner venezolano no afecta partners panameños"""
        # Crear partner de Panamá
        partner_pa = self.env['res.partner'].create({
            'name': 'Cliente Panamá',
            'country_id': self.country_pa.id,
            'ruc': '155986022-2-2019',
        })
        self.assertTrue(partner_pa.is_panama)
        self.assertFalse(partner_pa.is_venezuela)
        self.assertEqual(partner_pa.ruc_type, 'legal_commercial')
        
        # Crear partner de Venezuela
        partner_ve = self.env['res.partner'].create({
            'name': 'Cliente Venezuela',
            'country_id': self.country_ve.id,
            'identification_id': '87654321',
            'nationality': 'V',
        })
        self.assertTrue(partner_ve.is_venezuela)
        self.assertFalse(partner_ve.is_panama)
        
        # Verificar que el partner panameño no fue afectado
        partner_pa.refresh()
        self.assertTrue(partner_pa.is_panama)
        self.assertFalse(partner_pa.is_venezuela)
        self.assertEqual(partner_pa.ruc_type, 'legal_commercial')

    def test_invalid_panama_ruc_does_not_affect_venezuela_validation(self):
        """Verificar que validación de RUC panameño no afecta otras localizaciones"""
        # Un RUC inválido para Panamá debe fallar solo si el país es Panamá
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': 'Cliente Panamá Inválido',
                'country_id': self.country_pa.id,
                'ruc': 'FORMATO-INVALIDO',
            })
        
        # Pero el mismo texto puede usarse en otro campo para Venezuela sin problemas
        partner_ve = self.env['res.partner'].create({
            'name': 'Cliente Venezuela',
            'country_id': self.country_ve.id,
            'ruc': 'CUALQUIER-TEXTO',  # Campo ruc existe pero no se valida para VE
        })
        self.assertTrue(partner_ve.is_venezuela)
        self.assertFalse(partner_ve.is_panama)

    def test_multiple_countries_in_same_database(self):
        """Test que múltiples países pueden coexistir sin problemas"""
        # Crear partners de diferentes países
        partners = []
        
        # Panamá - varios tipos de RUC
        partners.append(self.env['res.partner'].create({
            'name': 'Empresa PA Comercial',
            'country_id': self.country_pa.id,
            'company_type': 'company',
            'ruc': '155986022-2-2019',
        }))
        
        partners.append(self.env['res.partner'].create({
            'name': 'Persona PA Natural',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        }))
        
        partners.append(self.env['res.partner'].create({
            'name': 'Fundación PA',
            'country_id': self.country_pa.id,
            'company_type': 'company',
            'ruc': '26631254-3-2020',
        }))
        
        # Venezuela
        partners.append(self.env['res.partner'].create({
            'name': 'Cliente Venezuela',
            'country_id': self.country_ve.id,
            'identification_id': '12345678',
            'nationality': 'V',
        }))
        
        # Verificar que todos fueron creados correctamente
        self.assertEqual(len(partners), 4)
        
        # Verificar campos específicos de cada país
        pa_partners = [p for p in partners if p.is_panama]
        ve_partners = [p for p in partners if p.is_venezuela]
        
        self.assertEqual(len(pa_partners), 3)
        self.assertEqual(len(ve_partners), 1)
        
        # Verificar tipos de RUC panameños
        self.assertEqual(pa_partners[0].ruc_type, 'legal_commercial')
        self.assertEqual(pa_partners[1].ruc_type, 'natural_national')
        self.assertEqual(pa_partners[2].ruc_type, 'legal_non_commercial')

    def test_partner_country_change_updates_validations(self):
        """Test que cambiar país actualiza las validaciones aplicables"""
        # Crear partner sin país específico
        partner = self.env['res.partner'].create({
            'name': 'Cliente Internacional',
        })
        self.assertFalse(partner.is_panama)
        self.assertFalse(partner.is_venezuela)
        
        # Cambiar a Panamá y agregar RUC válido
        partner.write({
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        self.assertTrue(partner.is_panama)
        self.assertFalse(partner.is_venezuela)
        self.assertEqual(partner.ruc_type, 'natural_national')
        
        # Cambiar a Venezuela
        partner.write({
            'country_id': self.country_ve.id,
        })
        self.assertFalse(partner.is_panama)
        self.assertTrue(partner.is_venezuela)
        # El RUC sigue ahí pero ya no se valida para Venezuela
        self.assertEqual(partner.ruc, '8-926-1601')

    def test_fields_do_not_conflict(self):
        """Verificar que los campos de ambas localizaciones no entran en conflicto"""
        # Panamá usa: is_panama, ruc, ruc_type
        # Venezuela usa: is_venezuela, rif, identification_id, nationality
        
        partner_pa = self.env['res.partner'].create({
            'name': 'Test Panamá',
            'country_id': self.country_pa.id,
            'ruc': '8-926-1601',
        })
        
        # Verificar campos de Panamá
        self.assertTrue(hasattr(partner_pa, 'is_panama'))
        self.assertTrue(hasattr(partner_pa, 'ruc'))
        self.assertTrue(hasattr(partner_pa, 'ruc_type'))
        
        # Verificar campos de Venezuela
        self.assertTrue(hasattr(partner_pa, 'is_venezuela'))
        self.assertTrue(hasattr(partner_pa, 'rif'))
        self.assertTrue(hasattr(partner_pa, 'identification_id'))
        self.assertTrue(hasattr(partner_pa, 'nationality'))
        
        # Verificar que los campos tienen valores correctos
        self.assertTrue(partner_pa.is_panama)
        self.assertFalse(partner_pa.is_venezuela)
        self.assertEqual(partner_pa.ruc, '8-926-1601')
        self.assertEqual(partner_pa.ruc_type, 'natural_national')
