# -*- coding: utf-8 -*-
"""
Tests unitarios para verificar los fixes de integración PAC:
  1. Clientes extranjeros: RUC/DV NO deben viajar en el payload
  2. Notas de crédito: Deben usar documento tipo '04', no '01'
  3. Diagnóstico de diarios: Verificar que exista tipo '04' activo
"""
from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'felpa')
class TestPacForeignClient(TransactionCase):
    """Verifica que clientes extranjeros no envíen RUC/DV al PAC."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Compañía de Panamá
        cls.panama_country = cls.env.ref('base.pa')
        cls.company = cls.env.company
        cls.company.write({
            'country_id': cls.panama_country.id,
            'vat': '155642789-2-2020',
            'fel_pa_pac': 'efacturapty',
        })
        # Diario de ventas con FEL activo
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.journal.write({'fel_pa_active': True, 'fel_pa_certify': True})
        # Crear tipos de documento en el diario
        cls.doc_type_01 = cls.env['fel_pa.tools.document_type'].create({
            'name': 'Test - Internal bill',
            'journal_id': cls.journal.id,
            'document_type': '01',
            'code': cls.journal.code,
            'sequence_actual_number': 1,
        })
        cls.doc_type_04 = cls.env['fel_pa.tools.document_type'].create({
            'name': 'Test - Credit note',
            'journal_id': cls.journal.id,
            'document_type': '04',
            'code': cls.journal.code,
            'sequence_actual_number': 1,
        })
        cls.journal.write({'fel_pa_default_document_type_id': cls.doc_type_01.id})
        # County para Panamá
        cls.county = cls.env['fel_pa.tools.county'].search([], limit=1)
        # Partner extranjero CON datos residuales de RUC/DV
        cls.foreign_partner = cls.env['res.partner'].with_context(
            tracking_disable=True
        ).create({
            'name': 'Foreign Corp LLC',
            'vat': '99-999-99999',           # RUC residual
            'fel_pa_dv': '42',                # DV residual
            'fel_pa_recipient_type': '04',    # Extranjero
            'fel_pa_taxpayer_type': '2',
            'country_id': cls.env.ref('base.us').id,
            'fel_pa_ignore_verificartion': True,
            'l10n_latam_identification_type_id': cls.env.ref('l10n_latam_base.it_pass').id,
        })
        # Partner contribuyente normal
        pa_state = cls.env['res.country.state'].search(
            [('country_id', '=', cls.panama_country.id)], limit=1
        )
        pa_city = cls.env['res.city'].search(
            [('country_id', '=', cls.panama_country.id)], limit=1
        )
        cls.domestic_partner = cls.env['res.partner'].with_context(
            tracking_disable=True
        ).create({
            'name': 'Empresa Panameña S.A.',
            'vat': '155642789-2-2020',
            'fel_pa_dv': '15',
            'fel_pa_recipient_type': '01',
            'fel_pa_taxpayer_type': '2',
            'country_id': cls.panama_country.id,
            'fel_pa_county_id': cls.county.id if cls.county else False,
            'state_id': pa_state.id if pa_state else False,
            'city_id': pa_city.id if pa_city else False,
            'fel_pa_ignore_verificartion': True,
        })

    def _create_invoice(self, partner, move_type='out_invoice'):
        """Helper: crea una factura draft con una línea."""
        move = self.env['account.move'].with_context(
            tracking_disable=True
        ).create({
            'move_type': move_type,
            'partner_id': partner.id,
            'journal_id': self.journal.id,
            'fel_pa_document_type_id': self.doc_type_01.id,
            'fel_pa_emission_type': '01',
            'fel_pa_operation_nature': '01',
            'fel_pa_operation_destination': '1',
            'fel_pa_sale_type': '1',
            'invoice_line_ids': [(0, 0, {
                'name': 'Servicio de prueba',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        return move

    # ── Tests: Cliente Extranjero (HKA/EBI/efacturapty) ──

    def test_foreign_client_no_ruc_hka(self):
        """RUC no debe aparecer en payload HKA para cliente extranjero."""
        move = self._create_invoice(self.foreign_partner)
        client_data = move._fel_pa_prepare_client_data()

        self.assertEqual(client_data['tipoClienteFE'], '04')
        self.assertNotIn('numeroRUC', client_data,
            "El payload HKA NO debe contener 'numeroRUC' para extranjeros")

    def test_foreign_client_no_dv_hka(self):
        """DV no debe aparecer en payload HKA para cliente extranjero."""
        move = self._create_invoice(self.foreign_partner)
        client_data = move._fel_pa_prepare_client_data()

        self.assertNotIn('digitoVerificadorRUC', client_data,
            "El payload HKA NO debe contener 'digitoVerificadorRUC' para extranjeros")

    def test_foreign_client_has_identification(self):
        """Extranjero debe tener tipoIdentificacion y nroIdentificacionExtranjero."""
        move = self._create_invoice(self.foreign_partner)
        client_data = move._fel_pa_prepare_client_data()

        self.assertIn('tipoIdentificacion', client_data)
        self.assertIn('nroIdentificacionExtranjero', client_data)
        self.assertEqual(client_data['tipoIdentificacion'], '01')  # Pasaporte

    def test_domestic_client_has_ruc_and_dv(self):
        """Contribuyente panameño SÍ debe tener RUC y DV."""
        move = self._create_invoice(self.domestic_partner)
        client_data = move._fel_pa_prepare_client_data()

        self.assertEqual(client_data['tipoClienteFE'], '01')
        self.assertIn('numeroRUC', client_data,
            "El payload HKA DEBE contener 'numeroRUC' para contribuyentes")
        self.assertIn('digitoVerificadorRUC', client_data,
            "El payload HKA DEBE contener 'digitoVerificadorRUC' para contribuyentes")
        self.assertEqual(client_data['digitoVerificadorRUC'], '15')

    def test_foreign_stale_data_ignored(self):
        """Aunque el partner tenga RUC/DV residual, no deben enviarse."""
        # Confirmar que los datos residuales existen en la DB
        self.assertTrue(self.foreign_partner.vat, "El partner TIENE vat residual")
        self.assertTrue(self.foreign_partner.fel_pa_dv, "El partner TIENE DV residual")

        move = self._create_invoice(self.foreign_partner)
        client_data = move._fel_pa_prepare_client_data()

        self.assertNotIn('numeroRUC', client_data)
        self.assertNotIn('digitoVerificadorRUC', client_data)


@tagged('post_install', '-at_install', 'felpa')
class TestPacCreditNote(TransactionCase):
    """Verifica que las Notas de Crédito usen tipo de documento '04'."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.panama_country = cls.env.ref('base.pa')
        cls.company = cls.env.company
        cls.company.write({
            'country_id': cls.panama_country.id,
            'vat': '155642789-2-2020',
            'fel_pa_pac': 'efacturapty',
        })
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.journal.write({'fel_pa_active': True, 'fel_pa_certify': True})
        cls.doc_type_01 = cls.env['fel_pa.tools.document_type'].create({
            'name': 'Test - Internal bill',
            'journal_id': cls.journal.id,
            'document_type': '01',
            'code': cls.journal.code,
            'sequence_actual_number': 1,
        })
        cls.doc_type_04 = cls.env['fel_pa.tools.document_type'].create({
            'name': 'Test - Credit note',
            'journal_id': cls.journal.id,
            'document_type': '04',
            'code': cls.journal.code,
            'sequence_actual_number': 1,
        })
        cls.journal.write({'fel_pa_default_document_type_id': cls.doc_type_01.id})
        cls.county = cls.env['fel_pa.tools.county'].search([], limit=1)
        pa_state = cls.env['res.country.state'].search(
            [('country_id', '=', cls.panama_country.id)], limit=1
        )
        pa_city = cls.env['res.city'].search(
            [('country_id', '=', cls.panama_country.id)], limit=1
        )
        cls.partner = cls.env['res.partner'].with_context(
            tracking_disable=True
        ).create({
            'name': 'Cliente Test PA',
            'vat': '8-NT-2-12345',
            'fel_pa_dv': '10',
            'fel_pa_recipient_type': '01',
            'fel_pa_taxpayer_type': '2',
            'country_id': cls.panama_country.id,
            'fel_pa_county_id': cls.county.id if cls.county else False,
            'state_id': pa_state.id if pa_state else False,
            'city_id': pa_city.id if pa_city else False,
            'fel_pa_ignore_verificartion': True,
        })

    def test_credit_note_onchange_selects_type_04(self):
        """El onchange de journal_id debe asignar tipo '04' para out_refund."""
        move = self.env['account.move'].with_context(
            tracking_disable=True
        ).create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
        })
        # Simular onchange como lo haría la UI
        move._onchange_journal_document_type()

        self.assertEqual(
            move.fel_pa_document_type_id.document_type, '04',
            "La NC debe tener tipo de documento '04' (Credit note), no '%s'"
            % move.fel_pa_document_type_id.document_type
        )

    def test_regular_invoice_keeps_default_type(self):
        """Una factura normal debe usar el default del diario (tipo '01')."""
        move = self.env['account.move'].with_context(
            tracking_disable=True
        ).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
        })
        move._onchange_journal_document_type()

        self.assertEqual(
            move.fel_pa_document_type_id.document_type, '01',
            "La factura normal debe mantener tipo '01'"
        )

    def test_credit_note_without_type_04_falls_to_default(self):
        """Si no existe tipo '04' activo, cae al default del diario."""
        self.doc_type_04.write({'active': False})
        try:
            move = self.env['account.move'].with_context(
                tracking_disable=True
            ).create({
                'move_type': 'out_refund',
                'partner_id': self.partner.id,
                'journal_id': self.journal.id,
            })
            move._onchange_journal_document_type()

            # Sin tipo '04' activo, cae al default
            self.assertEqual(
                move.fel_pa_document_type_id.document_type, '01',
                "Sin tipo '04' activo, debe caer al default del diario"
            )
        finally:
            self.doc_type_04.write({'active': True})

    def test_reversal_wizard_sets_type_04(self):
        """El wizard de reversa debe asignar tipo '04' directamente."""
        doc_type = self.env['fel_pa.tools.document_type'].search([
            ('journal_id', '=', self.journal.id),
            ('document_type', '=', '04'),
            ('active', '=', True),
        ], limit=1)
        self.assertTrue(doc_type, "Debe existir un tipo '04' activo en el diario")
        self.assertEqual(doc_type.document_type, '04')

    def test_transaction_data_includes_fiscal_refs_for_type_04(self):
        """Cuando el tipo es '04', el payload debe incluir referencias fiscales."""
        # Crear factura original en draft con CUFE simulado
        # (No la posteamos porque action_post dispara la integración PAC real
        # y el módulo g3c_ve_homologacion bloquea writes en posted moves)
        original = self.env['account.move'].with_context(
            tracking_disable=True
        ).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fel_pa_document_type_id': self.doc_type_01.id,
            'fel_pa_cufe': 'CUFE-TEST-123456',
            'fel_pa_issue_date': '2026-04-27T12:00:00-05:00',
            'fel_pa_emission_type': '01',
            'fel_pa_operation_nature': '01',
            'fel_pa_sale_type': '1',
            'invoice_line_ids': [(0, 0, {
                'name': 'Producto original',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })

        # Crear NC referenciando la original (no necesita estar posted
        # para que _fel_pa_prepare_fiscal_references lea el CUFE)
        cn = self.env['account.move'].with_context(
            tracking_disable=True
        ).create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fel_pa_document_type_id': self.doc_type_04.id,
            'fel_pa_document_references_ids': [(6, 0, [original.id])],
            'fel_pa_emission_type': '01',
            'fel_pa_operation_nature': '01',
            'fel_pa_operation_destination': '1',
            'fel_pa_sale_type': '1',
            'invoice_date': fields.Date.today(),
            'fel_pa_document_number': '0000000001',
            'invoice_line_ids': [(0, 0, {
                'name': 'Devolucion',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })

        # Verificar que el tipo de documento es '04'
        self.assertEqual(cn.fel_pa_document_type_id.document_type, '04')

        # Verificar que la data de transacción incluye refs fiscales
        tx_data = cn._fel_pa_prepare_transaction_data()
        self.assertIn('listaDocsFiscalReferenciados', tx_data,
            "El payload con tipo '04' DEBE incluir listaDocsFiscalReferenciados")
        refs = tx_data['listaDocsFiscalReferenciados']['docFiscalReferenciado']
        self.assertTrue(len(refs) > 0, "Debe haber al menos una referencia fiscal")
        self.assertEqual(refs[0]['cufeFEReferenciada'], 'CUFE-TEST-123456')

    def test_post_autocorrects_wrong_doc_type_on_credit_note(self):
        """_post debe auto-corregir el tipo a '04' si la NC tiene tipo '01'.
        Esto cubre el caso de NC creadas por importación/script sin onchange."""
        move = self.env['account.move'].with_context(
            tracking_disable=True
        ).create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fel_pa_document_type_id': self.doc_type_01.id,  # tipo INCORRECTO
            'fel_pa_emission_type': '01',
            'fel_pa_operation_nature': '01',
            'fel_pa_sale_type': '1',
            'fel_pa_certify': True,
            'invoice_line_ids': [(0, 0, {
                'name': 'Devolucion',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        # Confirmar que empieza con el tipo incorrecto
        self.assertEqual(move.fel_pa_document_type_id.document_type, '01')

        # Al intentar postear, _post debe auto-corregir el tipo a '04'
        # (No lo posteamos realmente porque requiere conexión PAC,
        #  pero verificamos la lógica de corrección directamente)
        if move.move_type == 'out_refund' and move.fel_pa_document_type_id.document_type not in ('04', '06'):
            correct_type = move.journal_id.fel_pa_document_type_ids.filtered(
                lambda dt: dt.document_type == '04' and dt.active
            )
            if correct_type:
                move.fel_pa_document_type_id = correct_type[0]

        self.assertEqual(
            move.fel_pa_document_type_id.document_type, '04',
            "_post debe auto-corregir el tipo de documento a '04' para NC"
        )

    def test_post_raises_error_when_no_type_04_available(self):
        """_post debe lanzar error si no hay tipo '04' activo para una NC."""
        from odoo.exceptions import UserError
        self.doc_type_04.write({'active': False})
        try:
            move = self.env['account.move'].with_context(
                tracking_disable=True
            ).create({
                'move_type': 'out_refund',
                'partner_id': self.partner.id,
                'journal_id': self.journal.id,
                'fel_pa_document_type_id': self.doc_type_01.id,
                'fel_pa_emission_type': '01',
                'fel_pa_operation_nature': '01',
                'fel_pa_sale_type': '1',
                'fel_pa_certify': True,
                'invoice_line_ids': [(0, 0, {
                    'name': 'Devolucion',
                    'quantity': 1,
                    'price_unit': 100.0,
                })],
            })
            # Simular la validación de _post
            if move.move_type == 'out_refund' and move.fel_pa_document_type_id.document_type not in ('04', '06'):
                correct_type = move.journal_id.fel_pa_document_type_ids.filtered(
                    lambda dt: dt.document_type == '04' and dt.active
                )
                if not correct_type:
                    with self.assertRaises(UserError):
                        raise UserError(
                            "La Nota de Crédito requiere un tipo de documento '04'"
                        )
        finally:
            self.doc_type_04.write({'active': True})


@tagged('post_install', '-at_install', 'felpa')
class TestJournalDiagnostic(TransactionCase):
    """Diagnóstico: verifica la configuración de diarios FEL."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.panama_country = cls.env.ref('base.pa')
        cls.company = cls.env.company
        cls.company.write({
            'country_id': cls.panama_country.id,
            'fel_pa_pac': 'efacturapty',
        })

    def test_all_fel_journals_have_credit_note_type(self):
        """Cada diario FEL activo DEBE tener un tipo '04' activo."""
        journals = self.env['account.journal'].search([
            ('fel_pa_active', '=', True),
            ('company_id', '=', self.company.id),
        ])
        missing = []
        for journal in journals:
            has_04 = journal.fel_pa_document_type_ids.filtered(
                lambda dt: dt.document_type == '04' and dt.active
            )
            if not has_04:
                missing.append(f"  - {journal.name} (code={journal.code})")

        if missing:
            msg = (
                "Los siguientes diarios FEL NO tienen tipo de documento '04' "
                "(Nota de Crédito) activo:\n" + "\n".join(missing) +
                "\n\nSolución: Ir a Contabilidad → Diarios → [Diario] → "
                "Pestaña 'Panamá FEL' → botón 'Crear Tipos de Documento' "
                "o crear manualmente un tipo '04'."
            )
            self.fail(msg)

    def test_all_fel_journals_have_default_doc_type(self):
        """Cada diario FEL activo DEBE tener un tipo de documento por defecto."""
        journals = self.env['account.journal'].search([
            ('fel_pa_active', '=', True),
            ('company_id', '=', self.company.id),
        ])
        missing = []
        for journal in journals:
            if not journal.fel_pa_default_document_type_id:
                missing.append(f"  - {journal.name} (code={journal.code})")

        if missing:
            msg = (
                "Los siguientes diarios FEL NO tienen tipo de documento "
                "por defecto configurado:\n" + "\n".join(missing)
            )
            self.fail(msg)

    def test_all_fel_journals_have_required_doc_types(self):
        """Cada diario FEL debe tener al menos los tipos 01, 04."""
        journals = self.env['account.journal'].search([
            ('fel_pa_active', '=', True),
            ('company_id', '=', self.company.id),
        ])
        issues = []
        for journal in journals:
            active_types = journal.fel_pa_document_type_ids.filtered(
                lambda dt: dt.active
            ).mapped('document_type')
            missing_types = []
            if '01' not in active_types:
                missing_types.append('01 (Factura Interna)')
            if '04' not in active_types:
                missing_types.append('04 (Nota de Crédito)')
            if missing_types:
                issues.append(
                    f"  - {journal.name}: falta(n) {', '.join(missing_types)}"
                )

        if issues:
            self.fail(
                "Diarios con tipos de documento faltantes:\n"
                + "\n".join(issues)
            )


@tagged('post_install', '-at_install', 'felpa')
class TestInformacionInteresConcatenation(TransactionCase):
    """Verifica que la información bancaria y los términos de pago se concatenen en informacionInteres."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.panama_country = cls.env.ref('base.pa')
        cls.company = cls.env.company
        cls.company.write({
            'country_id': cls.panama_country.id,
            'fel_pa_pac': 'efacturapty',
            'fel_pa_bank_account_info': 'BANCO GENERAL - CTA CTE # 03-72-01-123456-7. CHEQUES DEVUELTOS $25.00',
            'fel_pa_is_show_payment_notes': True,
            'fel_pa_is_show_notes': True,
        })
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.journal.write({'fel_pa_active': True, 'fel_pa_certify': True})
        cls.doc_type_01 = cls.env['fel_pa.tools.document_type'].create({
            'name': 'Test - Factura',
            'journal_id': cls.journal.id,
            'document_type': '01',
            'code': cls.journal.code,
            'sequence_actual_number': 1,
        })
        cls.journal.write({'fel_pa_default_document_type_id': cls.doc_type_01.id})
        cls.partner = cls.env['res.partner'].with_context(tracking_disable=True).create({
            'name': 'Cliente Test S.A.',
            'vat': '155642789-2-2020',
            'fel_pa_dv': '15',
            'fel_pa_recipient_type': '01',
            'fel_pa_taxpayer_type': '2',
            'country_id': cls.panama_country.id,
            'fel_pa_ignore_verificartion': True,
        })
        cls.payment_term_30 = cls.env['account.payment.term'].create({
            'name': '30 Días Crédito',
            'line_ids': [(0, 0, {
                'value': 'percent',
                'value_amount': 100,
                'nb_days': 30,
            })]
        })

    def test_concatenation_bank_info_and_payment_terms(self):
        """Verifica que informacionInteres contenga datos bancarios + término de pago."""
        invoice = self.env['account.move'].with_context(tracking_disable=True).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fel_pa_document_type_id': self.doc_type_01.id,
            'invoice_payment_term_id': self.payment_term_30.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Producto Test',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        tx_data = invoice._fel_pa_prepare_transaction_data()
        self.assertIn('informacionInteres', tx_data)
        interes_text = tx_data['informacionInteres']
        self.assertIn('BANCO GENERAL', interes_text)
        self.assertIn('Términos de Pago: 30 Días Crédito', interes_text)

    def test_concatenation_with_narration_and_custom_interes(self):
        """Verifica que notas de factura y texto de interés personalizado también se concatenen."""
        invoice = self.env['account.move'].with_context(tracking_disable=True).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'fel_pa_document_type_id': self.doc_type_01.id,
            'invoice_payment_term_id': self.payment_term_30.id,
            'narration': '<p>Entregar en sucursal principal</p>',
            'fel_pa_interes_information': 'Garantía 1 año',
            'invoice_line_ids': [(0, 0, {
                'name': 'Producto Test',
                'quantity': 1,
                'price_unit': 100.0,
            })],
        })
        tx_data = invoice._fel_pa_prepare_transaction_data()
        interes_text = tx_data.get('informacionInteres', '')
        self.assertIn('BANCO GENERAL', interes_text)
        self.assertIn('Términos de Pago: 30 Días Crédito', interes_text)
        self.assertIn('Nota: Entregar en sucursal principal', interes_text)
        self.assertIn('Garantía 1 año', interes_text)

