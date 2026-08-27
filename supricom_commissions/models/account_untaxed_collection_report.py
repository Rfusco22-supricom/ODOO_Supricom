# -*- coding: utf-8 -*-

from odoo import fields, models, tools


class AccountUntaxedCollectionReport(models.Model):
    _name = "account.untaxed.collection.report"
    _description = "Reporte de Cobros por Vendedor (Base Imponible)"
    _auto = False
    _order = "date desc, id desc"

    name = fields.Char(string="Factura", readonly=True)
    salesperson_id = fields.Many2one("res.users", string="Vendedor", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    invoice_id = fields.Many2one("account.move", string="Factura", readonly=True)
    payment_id = fields.Many2one("account.payment", string="Pago", readonly=True)
    move_id = fields.Many2one("account.move", string="Asiento de Pago", readonly=True)
    company_id = fields.Many2one("res.company", string="Compañía", readonly=True)
    date = fields.Date(string="Fecha de Cobro", readonly=True)
    amount_gross = fields.Float(string="Importe Bruto ($)", readonly=True)
    amount_untaxed = fields.Float(string="Base Imponible Cobrada ($)", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    apr.id AS id,
                    inv.name AS name,
                    inv.invoice_user_id AS salesperson_id,
                    inv.partner_id AS partner_id,
                    inv.id AS invoice_id,
                    pay.id AS payment_id,
                    pay_move.id AS move_id,
                    inv.company_id AS company_id,
                    COALESCE(pay_move.date, apr.max_date) AS date,
                    apr.amount AS amount_gross,
                    CASE
                        WHEN inv.amount_total != 0 THEN apr.amount * (inv.amount_untaxed / inv.amount_total)
                        ELSE apr.amount
                    END AS amount_untaxed,
                    inv.currency_id AS currency_id
                FROM account_partial_reconcile apr
                JOIN account_move_line deb_line ON apr.debit_move_id = deb_line.id
                JOIN account_move inv ON deb_line.move_id = inv.id
                JOIN account_move_line cred_line ON apr.credit_move_id = cred_line.id
                JOIN account_move pay_move ON cred_line.move_id = pay_move.id
                LEFT JOIN account_payment pay ON pay_move.id = pay.move_id
                WHERE inv.move_type = 'out_invoice'
                  AND inv.state = 'posted'
                  AND pay_move.state = 'posted'
            )
        """
            % self._table
        )
