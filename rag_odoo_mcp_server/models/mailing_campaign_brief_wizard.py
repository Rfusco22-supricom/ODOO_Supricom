# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class MailingCampaignBriefImage(models.TransientModel):
    _name = "rag_odoo_mcp_server.mailing_campaign_brief_image"
    _description = "Custom image for Claude campaign brief"

    wizard_id = fields.Many2one(
        "rag_odoo_mcp_server.mailing_campaign_brief_wizard",
        ondelete="cascade",
    )
    image = fields.Binary("Image", attachment=True)
    image_filename = fields.Char("Filename")
    description = fields.Char(
        "Usage hint",
        placeholder="e.g. hero banner, product shot, promo badge",
    )


class MailingCampaignBriefWizard(models.TransientModel):
    _name = "rag_odoo_mcp_server.mailing_campaign_brief_wizard"
    _description = "Campaign generation brief for Claude / MCP"

    # ── Identity ──────────────────────────────────────────────────────────
    brief_title = fields.Char(
        "Brief title",
        default="Claude campaign brief",
        required=True,
    )

    # ── Products ──────────────────────────────────────────────────────────
    product_ids = fields.Many2many(
        "product.template",
        "rag_odoo_mcp_mail_brief_product_rel",
        "wizard_id",
        "product_id",
        string="Products to promote",
        help="Claude will generate one campaign per product if several are selected.",
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
    cta_text = fields.Char(
        "Preferred CTA",
        placeholder='e.g. "Shop Now", "Get 20% Off", "Discover More"',
    )
    extra_instructions = fields.Text(
        "Campaign instructions",
        placeholder=(
            "Discount codes, seasonal context, product angle to highlight, "
            "competitor mentions to avoid, forbidden words..."
        ),
    )

    # ── Audience ──────────────────────────────────────────────────────────
    contact_list_ids = fields.Many2many(
        "mailing.list",
        "rag_odoo_mcp_mail_brief_list_rel",
        "wizard_id",
        "list_id",
        string="Target mailing lists",
    )
    target_audience = fields.Text(
        "Target audience",
        placeholder=(
            "Describe who receives this campaign: demographics, interests, "
            "purchase history, geographic focus..."
        ),
    )

    # ── Custom images ─────────────────────────────────────────────────────
    image_ids = fields.One2many(
        "rag_odoo_mcp_server.mailing_campaign_brief_image",
        "wizard_id",
        string="Custom images",
        help=(
            "Upload images Claude should use in the campaign (logos, product shots, banners). "
            "These are saved as accessible URLs and passed to Claude alongside the brief."
        ),
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

    # ─────────────────────────────────────────────────────────────────────

    def _save_images_as_attachments(self):
        """
        Persist wizard binary images as ir.attachment records so the LLM
        can reference them by URL. Returns a list of dicts with id + url.
        """
        icp = self.env["ir.config_parameter"].sudo()
        base_url = (icp.get_param("web.base.url") or "").rstrip("/")

        # Delete any previously saved brief images
        self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "rag_odoo_mcp_server.mailing_campaign_brief_wizard"),
            ("res_id", "=", 0),
        ]).unlink()

        saved = []
        for img in self.image_ids:
            if not img.image:
                continue
            attach = self.env["ir.attachment"].sudo().create({
                "name": img.image_filename or ("campaign_image_%d.jpg" % (len(saved) + 1)),
                "type": "binary",
                "datas": img.image,
                "res_model": "rag_odoo_mcp_server.mailing_campaign_brief_wizard",
                "res_id": 0,
                "public": True,
            })
            saved.append({
                "attachment_id": attach.id,
                "url": "%s/web/image/ir.attachment/%d/datas" % (base_url, attach.id),
                "description": img.description or "",
                "filename": attach.name,
            })
        return saved

    def action_save_brief_for_mcp(self):
        self.ensure_one()

        Brief = self.env["rag_odoo_mcp_server.campaign_brief"]

        # Save images as attachments
        image_records = self._save_images_as_attachments()

        # Create the persistent brief record (active by default — deactivates others)
        brief_vals = {
            "name": self.brief_title,
            "active": True,
            "product_ids": [(6, 0, self.product_ids.ids)],
            "campaign_goal": self.campaign_goal,
            "campaign_tone": self.campaign_tone,
            "cta_text": self.cta_text or "",
            "extra_instructions": self.extra_instructions or "",
            "contact_list_ids": [(6, 0, self.contact_list_ids.ids)],
            "target_audience": self.target_audience or "",
            "schedule_type": self.schedule_type,
            "schedule_date": self.schedule_date,
            "utm_campaign_id": self.utm_campaign_id.id if self.utm_campaign_id else False,
        }
        brief = Brief.create(brief_vals)

        # Link saved image attachments to the brief
        BriefImage = self.env["rag_odoo_mcp_server.campaign_brief_image"]
        for img_data in image_records:
            BriefImage.create({
                "brief_id": brief.id,
                "attachment_id": img_data["attachment_id"],
                "description": img_data.get("description", ""),
            })

        # Recompute JSON now that images are linked
        brief._compute_brief_json()

        product_names = ", ".join(self.product_ids.mapped("name")) or "no specific product"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Brief saved for Claude"),
                "message": _(
                    "Campaign brief '%s' saved and activated for %s. "
                    "Call tool mailing_get_campaign_brief in Claude to start generating."
                ) % (brief.name, product_names),
                "type": "success",
                "sticky": True,
            },
        }


class MailingMailing(models.Model):
    _inherit = "mailing.mailing"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("body_arch"):
                vals["body_arch"] = self._ensure_design_element(vals["body_arch"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("body_arch"):
            vals["body_arch"] = self._ensure_design_element(vals["body_arch"])
        return super().write(vals)

    @staticmethod
    def _ensure_design_element(html):
        """Ensure body_arch has required elements for the mass_mailing editor."""
        if not html:
            return html
        # 1) <style id="design-element"> must exist inside .o_layout
        if "o_layout" in html and 'id="design-element"' not in html:
            idx = html.find(">", html.find("o_layout"))
            if idx != -1:
                html = html[:idx+1] + '\n  <style id="design-element"></style>' + html[idx+1:]
        # 2) o_editable must be on the oe_structure div (drop zone for snippets)
        if "oe_structure" in html and "o_editable" not in html:
            html = html.replace("oe_structure", "oe_structure o_editable", 1)
        return html
