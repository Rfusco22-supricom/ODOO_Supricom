from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    commission_base_type = fields.Selection(
        related="company_id.commission_base_type",
        readonly=False,
    )
    commission_target_mode = fields.Selection(
        related="company_id.commission_target_mode",
        readonly=False,
    )
    commission_use_targets = fields.Boolean(
        related="company_id.commission_use_targets",
        readonly=False,
    )
    commission_use_min_price = fields.Boolean(
        related="company_id.commission_use_min_price",
        readonly=False,
    )
    commission_show_profitability = fields.Boolean(
        related="company_id.commission_show_profitability",
        readonly=False,
    )
    commission_min_target_pct = fields.Float(
        related="company_id.commission_min_target_pct",
        readonly=False,
    )
    commission_max_target_cap = fields.Float(
        related="company_id.commission_max_target_cap",
        readonly=False,
    )

    commission_credit_threshold = fields.Float(
        related="company_id.commission_credit_threshold",
        readonly=False,
    )
    commission_payment_tolerance = fields.Float(
        related="company_id.commission_payment_tolerance",
        readonly=False,
    )
    commission_use_pricelist_mapping = fields.Boolean(
        related="company_id.commission_use_pricelist_mapping",
        readonly=False,
    )
    commission_strict_full_payment = fields.Boolean(
        related="company_id.commission_strict_full_payment",
        readonly=False,
    )
    commission_cash_rate = fields.Float(
        related="company_id.commission_cash_rate",
        readonly=False,
    )
    commission_credit_rate = fields.Float(
        related="company_id.commission_credit_rate",
        readonly=False,
    )
    commission_grace_days = fields.Integer(
        related="company_id.commission_grace_days",
        readonly=False,
    )
    commission_use_fixed_amount = fields.Boolean(
        related="company_id.commission_use_fixed_amount",
        readonly=False,
    )
    commission_fixed_product_ids = fields.Many2many(
        related="company_id.commission_fixed_product_ids",
        readonly=False,
    )
    commission_fixed_product_tag_ids = fields.Many2many(
        related="company_id.commission_fixed_product_tag_ids",
        readonly=False,
    )
    commission_fixed_product_category_ids = fields.Many2many(
        related="company_id.commission_fixed_product_category_ids",
        readonly=False,
    )

    commission_use_fixed_percentage = fields.Boolean(
        related="company_id.commission_use_fixed_percentage",
        readonly=False,
    )
    commission_fixed_pct_product_ids = fields.Many2many(
        related="company_id.commission_fixed_pct_product_ids",
        readonly=False,
    )
    commission_fixed_pct_product_tag_ids = fields.Many2many(
        related="company_id.commission_fixed_pct_product_tag_ids",
        readonly=False,
    )
    commission_fixed_pct_product_category_ids = fields.Many2many(
        related="company_id.commission_fixed_pct_product_category_ids",
        readonly=False,
    )
