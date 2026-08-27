from odoo import models, fields


class CommissionVendorType(models.Model):
    _name = "commission.vendor.type"
    _description = "Commission Vendor Type"

    name = fields.Char(
        string="Nombre",
        required=True,
        help="Nombre descriptivo del tipo de vendedor (ej. Nómina, Outsourcing).",
    )
    code = fields.Selection(
        [
            ("N", "N"),
            ("E", "E"),
            ("O", "O"),
            ("P", "P"),
            ("X", "X"),
            ("I", "I"),
        ],
        string="Código",
        required=True,
        help="Código corto para identificar el tipo de vendedor en reportes y lógica interna.",
    )
    country = fields.Selection(
        [
            ("VEN", "Venezuela"),
            ("PAN", "Panamá"),
        ],
        string="País",
        required=True,
        help="País al que aplica este tipo de vendedor (define moneda y reglas específicas).",
    )
    is_manager = fields.Boolean(
        string="Es Gerente",
        help="Marcar si este tipo de vendedor corresponde a un rol gerencial.",
    )
    manager_role = fields.Selection(
        [("sales", "Gerente de Ventas"), ("operations", "Gerente de Operaciones")],
        string="Rol de Gerente",
        help="Especifica el tipo de gerencia para aplicar reglas de comisión por equipo.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        default=lambda self: False,
        required=False,
        help="Compañía a la que pertenece este tipo de vendedor (opcional).",
    )
    manager_commission_type = fields.Selection(
        [
            ("fixed", "Porcentaje Fijo"),
            ("volume_range", "Escala por Facturación/Cobranza"),
            ("achievement_range", "Escala por Cumplimiento de Meta"),
        ],
        string="Modo de Comisión Gerencial",
        default="fixed",
        help="Define cómo se calcula la comisión gerencial para este rol.",
    )
    manager_fixed_rate = fields.Float(
        string="% Fijo Comisión Gerente",
        default=0.0,
        help="Porcentaje fijo de comisión para la gerencia (ej. 0.15 para Gerente de Operaciones Panamá).",
    )
    excluded_user_ids = fields.Many2many(
        "res.users",
        "comm_vendor_type_excluded_users_rel",
        "vendor_type_id",
        "user_id",
        string="Vendedores Excluidos",
        help="Vendedores cuyas ventas/cobros se excluyen del cálculo de comisión de esta gerencia (ej. Sr. Hercilio).",
    )
    volume_range_ids = fields.One2many(
        "commission.manager.volume.range",
        "vendor_type_id",
        string="Escalas por Volumen",
        help="Tramos de volumen cobrado/facturado para determinar el % gerencial (ej. Valencia).",
    )

