# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models, _


class MailingCampaignBrief(models.Model):
    _name = "rag_odoo_mcp_server.campaign_brief"
    _description = "Claude campaign brief"
    _order = "write_date desc"

    name = fields.Char("Brief title", required=True, default="Claude campaign brief")
    active = fields.Boolean(
        "Active",
        default=False,
        help="Only one brief can be active at a time. The active brief is the one used by Claude.",
    )

    # ── Products ──────────────────────────────────────────────────────────
    product_ids = fields.Many2many(
        "product.template",
        "rag_odoo_mcp_campaign_brief_product_rel",
        "brief_id",
        "product_id",
        string="Products to promote",
    )

    # ── Campaign style ────────────────────────────────────────────────────
    campaign_goal = fields.Selection(
        [
            ("conversion", "Drive sales / conversion"),
            ("launch", "Product launch"),
            ("awareness", "Brand awareness"),
            ("retention", "Customer retention"),
            ("reactivation", "Re-engage inactive contacts"),
        ],
        string="Goal",
        default="conversion",
        required=True,
    )
    campaign_tone = fields.Selection(
        [
            ("professional", "Professional"),
            ("casual", "Casual and friendly"),
            ("urgent", "Urgent / limited time offer"),
            ("inspirational", "Inspirational"),
            ("storytelling", "Storytelling"),
        ],
        string="Tone",
        default="professional",
        required=True,
    )
    cta_text = fields.Char("Preferred CTA")
    extra_instructions = fields.Text("Campaign instructions")

    # ── Audience ──────────────────────────────────────────────────────────
    contact_list_ids = fields.Many2many(
        "mailing.list",
        "rag_odoo_mcp_campaign_brief_list_rel",
        "brief_id",
        "list_id",
        string="Target mailing lists",
    )
    target_audience = fields.Text("Target audience")

    # ── Custom images ─────────────────────────────────────────────────────
    image_ids = fields.One2many(
        "rag_odoo_mcp_server.campaign_brief_image",
        "brief_id",
        string="Custom images",
    )

    # ── Scheduling ────────────────────────────────────────────────────────
    schedule_type = fields.Selection(
        [("now", "Send immediately"), ("scheduled", "Schedule for later")],
        string="Delivery",
        default="now",
        required=True,
    )
    schedule_date = fields.Datetime("Schedule date")
    utm_campaign_id = fields.Many2one("utm.campaign", string="UTM campaign")

    # ── Metadata ──────────────────────────────────────────────────────────
    brief_json = fields.Text(
        "Brief JSON (read-only)",
        help="Auto-generated JSON payload read by the MCP tool mailing_get_campaign_brief.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.active:
                # Deactivate other briefs
                self.search([("id", "!=", rec.id), ("active", "=", True)]).write({"active": False})
            rec._compute_brief_json()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("active"):
            # Deactivate other briefs
            self.search([("id", "not in", self.ids), ("active", "=", True)]).write({"active": False})
        # Recompute JSON if any content field changed
        content_fields = {
            "name", "product_ids", "campaign_goal", "campaign_tone",
            "cta_text", "extra_instructions", "contact_list_ids",
            "target_audience", "schedule_type", "schedule_date",
            "utm_campaign_id",
        }
        if content_fields & set(vals.keys()):
            for rec in self:
                rec._compute_brief_json()
        return res

    def _compute_brief_json(self):
        """Rebuild the JSON payload stored on the record."""
        icp = self.env["ir.config_parameter"].sudo()
        base_url = (icp.get_param("web.base.url") or "").rstrip("/")

        for rec in self:
            products = []
            for tmpl in rec.product_ids:
                products.append({
                    "id": tmpl.id,
                    "name": tmpl.name,
                    "default_code": tmpl.default_code or "",
                    "description_sale": (tmpl.description_sale or "").strip(),
                    "list_price": tmpl.list_price,
                    "currency": tmpl.currency_id.name if tmpl.currency_id else "",
                    "categ": tmpl.categ_id.name if tmpl.categ_id else "",
                    "image_url": "%s/web/image/product.template/%d/image_1920/600x400" % (base_url, tmpl.id),
                })

            mailing_lists = [
                {"id": ml.id, "name": ml.name, "contact_count": ml.contact_count}
                for ml in rec.contact_list_ids
            ]

            image_data = []
            for img in rec.image_ids:
                if img.attachment_id:
                    image_data.append({
                        "attachment_id": img.attachment_id.id,
                        "url": "%s/web/image/ir.attachment/%d/datas" % (base_url, img.attachment_id.id),
                        "description": img.description or "",
                        "filename": img.attachment_id.name or "",
                    })
                elif img.image:
                    # image stored via attachment=True — find the auto-created attachment
                    attach = self.env["ir.attachment"].search([
                        ("res_model", "=", "rag_odoo_mcp_server.campaign_brief_image"),
                        ("res_id", "=", img.id),
                        ("res_field", "=", "image"),
                    ], limit=1)
                    if attach:
                        image_data.append({
                            "attachment_id": attach.id,
                            "url": "%s/web/image/%d" % (base_url, attach.id),
                            "description": img.description or "",
                            "filename": img.image_filename or "",
                        })

            payload = {
                "brief_title": rec.name,
                "products": products,
                "campaign_goal": rec.campaign_goal,
                "campaign_tone": rec.campaign_tone,
                "cta_text": rec.cta_text or "",
                "extra_instructions": rec.extra_instructions or "",
                "contact_list_ids": rec.contact_list_ids.ids,
                "mailing_lists": mailing_lists,
                "target_audience": rec.target_audience or "",
                "custom_images": image_data,
                "schedule_type": rec.schedule_type,
                "schedule_date": fields.Datetime.to_string(rec.schedule_date) if rec.schedule_date else None,
                "utm_campaign_id": rec.utm_campaign_id.id if rec.utm_campaign_id else None,
                "utm_campaign_name": rec.utm_campaign_id.name if rec.utm_campaign_id else None,
                "saved_at": fields.Datetime.to_string(fields.Datetime.now()),
                "saved_by": self.env.user.display_name,
            }
            rec.brief_json = json.dumps(payload, default=str)

    def action_activate(self):
        """Activate this brief and deactivate all others."""
        self.ensure_one()
        self.search([("id", "!=", self.id), ("active", "=", True)]).write({"active": False})
        self.active = True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Brief activated"),
                "message": _("'%s' is now the active brief for Claude.") % self.name,
                "type": "success",
            },
        }

    def action_deactivate(self):
        """Deactivate this brief."""
        self.ensure_one()
        self.active = False


class CampaignBriefImage(models.Model):
    _name = "rag_odoo_mcp_server.campaign_brief_image"
    _description = "Custom image for Claude campaign brief"

    brief_id = fields.Many2one(
        "rag_odoo_mcp_server.campaign_brief",
        ondelete="cascade",
        required=True,
    )
    attachment_id = fields.Many2one("ir.attachment", string="Image attachment", ondelete="set null")
    description = fields.Char("Usage hint", placeholder="e.g. hero banner, product shot, promo badge")
    image = fields.Binary("Image", attachment=True)
    image_filename = fields.Char("Filename")
