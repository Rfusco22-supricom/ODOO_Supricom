from datetime import date

from odoo import models


class L10nInGSTReturnPeriod(models.Model):
    _inherit = 'l10n_in.gst.return.period'

    def _get_section_domain(self, section_code):
        sgst_tag_ids = self.env.ref('l10n_in.tax_tag_base_sgst').ids + self.env.ref('l10n_in.tax_tag_sgst').ids
        cgst_tag_ids = self.env.ref('l10n_in.tax_tag_base_cgst').ids + self.env.ref('l10n_in.tax_tag_cgst').ids
        igst_tag_ids = self.env.ref('l10n_in.tax_tag_base_igst').ids + self.env.ref('l10n_in.tax_tag_igst').ids
        cess_tag_ids = (
            self.env.ref('l10n_in.tax_tag_base_cess').ids
            + self.env.ref('l10n_in.tax_tag_cess').ids)
        zero_rated_tag_ids = self.env.ref('l10n_in.tax_tag_zero_rated').ids
        gst_tags = sgst_tag_ids + cgst_tag_ids + igst_tag_ids + cess_tag_ids + zero_rated_tag_ids
        other_than_gst_tag = (
            self.env.ref("l10n_in.tax_tag_exempt").ids
            + self.env.ref("l10n_in.tax_tag_nil_rated").ids
            + self.env.ref("l10n_in.tax_tag_non_gst_supplies").ids
        )
        export_tags = igst_tag_ids + zero_rated_tag_ids + cess_tag_ids + other_than_gst_tag
        domain = [
            ("date", ">=", self.start_date),
            ("date", "<=", self.end_date),
            ("move_id.state", "=", "posted"),
            ("company_id", "in", self.company_ids.ids or self.company_id.ids),
            ("display_type", "not in", ('rounding', 'line_note', 'line_section'))
        ]
        match section_code:
            case "b2b":
                return (
                    domain
                    + [
                        ("move_id.move_type", "in", ["out_invoice", "out_receipt"]),
                        ("move_id.debit_origin_id", "=", False),
                        '|', '&',
                        ("move_id.l10n_in_gst_treatment", "in", ("regular", "deemed_export", "uin_holders", "composition")),
                        ("tax_tag_ids", "in", gst_tags),
                        '&',
                        ("move_id.l10n_in_gst_treatment", "=", "special_economic_zone"),
                        ("tax_tag_ids", "in", gst_tags + other_than_gst_tag),
                    ]
                )
            case "b2cl":
                return (
                    domain
                    + [
                        ("move_id.move_type", "in", ["out_invoice", "out_receipt"]),
                        ("move_id.debit_origin_id", "=", False),
                        ("move_id.l10n_in_gst_treatment", "in", ("unregistered", "consumer")),
                        ("move_id.l10n_in_state_id", "!=", self.company_id.state_id.id),
                        "|", "&",
                        ("date", "<", date(2024, 11, 1)),
                        ("move_id.amount_total", ">", 250000),
                        "&",
                        ("date", ">=", date(2024, 11, 1)),
                        ("move_id.amount_total", ">", 100000),
                        ("tax_tag_ids", "in", gst_tags),
                    ]
                )
            case "cdnr":
                return (
                    domain
                    + [
                        "|",
                        ("move_id.move_type", "=", "out_refund"),
                        "&",
                        ("move_id.move_type", "=", "out_invoice"),
                        ("move_id.debit_origin_id", "!=", False),
                        '|', '&',
                        ("move_id.l10n_in_gst_treatment", "in", ("regular", "deemed_export", "uin_holders", "composition")),
                        ("tax_tag_ids", "in", gst_tags),
                        '&',
                        ("move_id.l10n_in_gst_treatment", "=", "special_economic_zone"),
                        ("tax_tag_ids", "in", gst_tags + other_than_gst_tag),
                    ]
                )
            case "cdnur":
                return (
                    domain
                    + [
                        "|",
                        ("move_id.move_type", "=", "out_refund"),
                        "&",
                        ("move_id.move_type", "=", "out_invoice"),
                        ("move_id.debit_origin_id", "!=", False),
                        "|", "&",
                        ("move_id.l10n_in_gst_treatment", "=", "overseas"),
                        ("tax_tag_ids", "in", export_tags),
                        "&", "&", "&",
                        ("tax_tag_ids", "in", gst_tags),
                        ("move_id.l10n_in_gst_treatment", "in", ["unregistered", "consumer"]),
                        ("move_id.l10n_in_transaction_type", "=", "inter_state"),
                        "|", "&",
                        ("date", "<", date(2024, 11, 1)),
                        ("move_id.amount_total", ">", 250000),
                        "&",
                        ("date", ">=", date(2024, 11, 1)),
                        ("move_id.amount_total", ">", 100000),
                    ]
                )
            case "exp":
                return (
                    domain
                    + [
                        ("move_id.move_type", "in", ["out_invoice", "out_receipt"]),
                        ("move_id.debit_origin_id", "=", False),
                        ("move_id.l10n_in_gst_treatment", "=", "overseas"),
                        ("tax_tag_ids", "in", export_tags),
                    ]
                )
        return super()._get_section_domain(section_code)
