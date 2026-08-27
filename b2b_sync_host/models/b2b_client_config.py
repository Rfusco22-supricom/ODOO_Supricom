# -*- coding: utf-8 -*-
import secrets
from odoo import api, fields, models


class B2bClientConfig(models.Model):
    _name = "b2b.client.config"
    _description = "Configuración de Clientes B2B Autenticados"

    name = fields.Char(string="Nombre del Cliente", required=True)
    api_key = fields.Char(
        string="API Key / Token",
        required=True,
        default=lambda self: secrets.token_hex(20),
        copy=False,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contacto / Cliente Asociado",
        required=True,
        domain="[('customer_rank', '>', 0)]",
    )
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Tarifa / Lista de Precios Asignada",
        required=True,
    )
    auto_confirm_orders = fields.Boolean(
        string="Confirmar Pedidos Automáticamente",
        default=True,
        help="Si está activo, los pedidos recibidos por API se confirmarán de inmediato.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("api_key_uniq", "unique(api_key)", "La API Key B2B debe ser única por cliente."),
    ]

    def action_generate_new_key(self):
        """Genera una nueva clave API de acceso."""
        for rec in self:
            rec.api_key = secrets.token_hex(20)
