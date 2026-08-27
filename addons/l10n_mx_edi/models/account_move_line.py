from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _filter_aml_lot_valuation(self):
        # EXTENDS account
        return super()._filter_aml_lot_valuation() and not self.move_id.l10n_mx_edi_cfdi_cancel_id

    def _get_product_unspsc_code(self):
        self.ensure_one()

        return (
            "84111506"
            if self in self._get_downpayment_lines()
            else self.product_id.unspsc_code_id.code
        )

    def _get_uom_unspsc_code(self):
        self.ensure_one()

        return (
            "ACT"
            if self in self._get_downpayment_lines()
            else self.product_uom_id.unspsc_code_id.code
        )
