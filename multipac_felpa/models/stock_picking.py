# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = "stock.picking"

    invoice_ids = fields.Many2many(
        comodel_name="account.move", copy=False, string="Invoices", readonly=True
    )
    invoice_count = fields.Integer(
        string="Number of Invoices", compute="_compute_invoice_count"
    )

    def action_view_invoice(self):
        """This function returns an action that display existing invoices
        of given stock pickings.
        It can either be a in a list or in a form view, if there is only
        one invoice to show.
        """
        self.ensure_one()
        form_view_name = "account.view_move_form"
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "account.action_move_out_invoice_type"
        )
        if len(self.invoice_ids) > 1:
            result["domain"] = f"[('id', 'in', {self.invoice_ids.ids})]"
        else:
            form_view = self.env.ref(form_view_name)
            result["views"] = [(form_view.id, "form")]
            result["res_id"] = self.invoice_ids.id
        return result

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for order in self:
            order.invoice_count = len(order.invoice_ids)
