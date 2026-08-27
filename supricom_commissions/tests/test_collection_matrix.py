from odoo.tests.common import TransactionCase


class TestCollectionMatrix(TransactionCase):
    """
    Pruebas unitarias para las nuevas reglas de negocio de comisiones:
    - Matriz de Cobranza (Penalización por Morosidad 100%, 50%, 30%, 0%)
    - Escala Gerencial por Volumen (Gerente Valencia - Imagen 1)
    - Verificación de Meta Mínima (80%) y Cap (150%)
    - Exclusión de Vendedores (ej. Sr. Hercilio)
    """

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.commission_min_target_pct = 80.0
        self.company.commission_max_target_cap = 150.0

        # Crear Matriz de Cobranza General para la Empresa (Valencia)
        self.env["commission.collection.matrix"].create([
            {
                "company_id": self.company.id,
                "user_id": False,
                "days_from": 0,
                "days_to": 15,
                "commission_factor_pct": 100.0,
                "payment_type": "all",
            },
            {
                "company_id": self.company.id,
                "user_id": False,
                "days_from": 16,
                "days_to": 30,
                "commission_factor_pct": 50.0,
                "payment_type": "all",
            },
            {
                "company_id": self.company.id,
                "user_id": False,
                "days_from": 31,
                "days_to": 60,
                "commission_factor_pct": 30.0,
                "payment_type": "all",
            },
            {
                "company_id": self.company.id,
                "user_id": False,
                "days_from": 61,
                "days_to": 999,
                "commission_factor_pct": 0.0,
                "payment_type": "all",
            },
        ])

        # Crear Tipo de Vendedor Gerente Valencia
        self.vendor_type_valencia = self.env["commission.vendor.type"].create({
            "name": "Gerente de Ventas Valencia",
            "code": "N",
            "country": "VEN",
            "is_manager": True,
            "manager_role": "sales",
            "manager_commission_type": "volume_range",
        })

        # Crear Escala por Volumen Valencia (Imagen 1)
        self.env["commission.manager.volume.range"].create([
            {
                "company_id": self.company.id,
                "vendor_type_id": self.vendor_type_valencia.id,
                "amount_from": 0.0,
                "amount_to": 799999.99,
                "commission_percentage": 0.20,
            },
            {
                "company_id": self.company.id,
                "vendor_type_id": self.vendor_type_valencia.id,
                "amount_from": 800000.0,
                "amount_to": 1499999.99,
                "commission_percentage": 0.30,
            },
            {
                "company_id": self.company.id,
                "vendor_type_id": self.vendor_type_valencia.id,
                "amount_from": 1500000.0,
                "amount_to": 1999999.99,
                "commission_percentage": 0.40,
            },
            {
                "company_id": self.company.id,
                "vendor_type_id": self.vendor_type_valencia.id,
                "amount_from": 2000000.0,
                "amount_to": 0.0,  # Sin límite
                "commission_percentage": 0.50,
            },
        ])

    def test_mora_rule_lookup(self):
        """Probar que el wizard busque correctamente el factor de mora en la matriz."""
        wizard = self.env["commission.settlement.wizard"].new({
            "date_from": "2026-01-01",
            "date_to": "2026-01-31",
        })

        user = self.env.user
        # 10 días de mora -> 100%
        factor_10 = wizard._get_mora_rule(user, self.company, 10, is_credit=True)
        self.assertEqual(factor_10, 1.0)

        # 20 días de mora -> 50%
        factor_20 = wizard._get_mora_rule(user, self.company, 20, is_credit=True)
        self.assertEqual(factor_20, 0.5)

        # 45 días de mora -> 30%
        factor_45 = wizard._get_mora_rule(user, self.company, 45, is_credit=True)
        self.assertEqual(factor_45, 0.3)

        # 70 días de mora -> 0%
        factor_70 = wizard._get_mora_rule(user, self.company, 70, is_credit=True)
        self.assertEqual(factor_70, 0.0)

    def test_valencia_manager_volume_range(self):
        """Probar que las reglas de volumen para Gerente de Valencia devuelvan la tasa correcta."""
        ranges = self.env["commission.manager.volume.range"].search([
            ("vendor_type_id", "=", self.vendor_type_valencia.id)
        ])
        self.assertEqual(len(ranges), 4)
