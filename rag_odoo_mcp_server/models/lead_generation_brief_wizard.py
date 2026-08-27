# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models, _
from odoo.addons.iap.tools import iap_tools

WEB_LEAD_BRIEF_PARAM = "rag_lead_generator.web_lead_brief_json"
WEB_LEAD_BRIEF_META_PARAM = "rag_lead_generator.web_lead_brief_meta_json"


class LeadBriefWizard(models.TransientModel):
    _name = "rag_odoo_mcp_server.lead_brief_wizard"
    _description = "Lead generation brief wizard for Claude / MCP"

    def _default_lead_type(self):
        if self.env.user.has_group("crm.group_use_lead"):
            return "lead"
        return "opportunity"

    def _default_country_ids(self):
        return self.env.user.company_id.country_id

    # ── Identity ─────────────────────────────────────────────────────────
    brief_title = fields.Char(
        "Brief title",
        default="Claude lead brief",
        required=True,
    )

    # ── Targeting ────────────────────────────────────────────────────────
    lead_number = fields.Integer("Number of leads", required=True, default=3)
    search_type = fields.Selection(
        [("companies", "Companies"), ("people", "Companies and their Contacts")],
        string="Target",
        required=True,
        default="companies",
    )
    lead_type = fields.Selection(
        [("lead", "Leads"), ("opportunity", "Opportunities")],
        string="Type",
        required=True,
        default=_default_lead_type,
    )
    country_ids = fields.Many2many(
        "res.country",
        "rag_odoo_mcp_lead_brief_wiz_country_rel",
        "wizard_id",
        "country_id",
        string="Countries",
        default=_default_country_ids,
    )
    state_ids = fields.Many2many(
        "res.country.state",
        "rag_odoo_mcp_lead_brief_wiz_state_rel",
        "wizard_id",
        "state_id",
        string="States",
    )
    available_state_ids = fields.Many2many(
        "res.country.state",
        compute="_compute_available_state_ids",
    )
    industry_ids = fields.Many2many(
        "crm.iap.lead.industry",
        "rag_odoo_mcp_lead_brief_wiz_industry_rel",
        "wizard_id",
        "industry_id",
        string="Industries",
    )
    filter_on_size = fields.Boolean("Filter on Size", default=False)
    company_size_min = fields.Integer("Size from", default=1)
    company_size_max = fields.Integer("Size to", default=1000)

    # ── Contacts ─────────────────────────────────────────────────────────
    contact_number = fields.Integer("Extra contacts per company", default=1)
    contact_filter_type = fields.Selection(
        [("role", "Role"), ("seniority", "Seniority")],
        string="Contact filter",
        default="role",
    )
    preferred_role_id = fields.Many2one("crm.iap.lead.role", string="Preferred Role")
    role_ids = fields.Many2many(
        "crm.iap.lead.role",
        "rag_odoo_mcp_lead_brief_wiz_role_rel",
        "wizard_id",
        "role_id",
        string="Other Roles",
    )
    seniority_id = fields.Many2one("crm.iap.lead.seniority", string="Seniority")

    # ── CRM defaults ─────────────────────────────────────────────────────
    team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        compute="_compute_team_id",
        store=True,
        readonly=False,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
    )
    tag_ids = fields.Many2many(
        "crm.tag",
        "rag_odoo_mcp_lead_brief_wiz_tag_rel",
        "wizard_id",
        "tag_id",
        string="Default Tags",
    )

    # ── Claude AI instructions ───────────────────────────────────────────
    lead_nature = fields.Selection(
        [
            ("outbound", "Outbound web research"),
            ("inbound", "Inbound / content / ads"),
            ("event", "Event / trade show"),
            ("partner", "Partner / referral"),
            ("other", "Other"),
        ],
        string="Lead nature",
        default="outbound",
    )
    subsector_notes = fields.Char("Sub-sector / niche")
    revenue_hint = fields.Char("Revenue band (hint)")
    geo_notes = fields.Char("Geography notes")
    job_titles_keywords = fields.Char("Additional job titles / keywords")
    buyer_persona = fields.Text("Buyer persona")
    product_service_fit = fields.Text("What we sell (fit)")
    keywords_include = fields.Char("Keywords to include")
    keywords_exclude = fields.Char("Keywords to exclude")
    competitor_landscape = fields.Char("Competitors to watch")
    research_sources_hint = fields.Selection(
        [
            ("general", "General web"),
            ("directories", "Directories"),
            ("news", "News and press"),
            ("other", "Other"),
        ],
        default="general",
    )
    language_id = fields.Many2one("res.lang", string="Language")
    compliance_notes = fields.Text("Compliance / opt-in")
    extra_notes = fields.Text("Notes for Claude")

    # ── Marketing / UTM ──────────────────────────────────────────────────
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda s: s.env.company,
    )
    campaign_id = fields.Many2one("utm.campaign", string="Campaign")
    medium_id = fields.Many2one("utm.medium", string="Medium")
    source_id = fields.Many2one("utm.source", string="Source")
    expected_revenue_hint = fields.Monetary(
        "Typical deal size (hint)",
        currency_field="currency_id",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda s: s.env.company.currency_id,
    )
    prefer_iap_enrich = fields.Boolean("Enrich leads from web after creation")

    # ─── Computed ────────────────────────────────────────────────────────

    @api.depends("country_ids")
    def _compute_available_state_ids(self):
        for wiz in self:
            countries = wiz.country_ids.filtered(
                lambda c: c.code in iap_tools._STATES_FILTER_COUNTRIES_WHITELIST
            )
            wiz.available_state_ids = self.env["res.country.state"].search(
                [("country_id", "in", countries.ids)]
            )

    @api.onchange("available_state_ids")
    def _onchange_available_state_ids(self):
        for wiz in self:
            wiz.state_ids -= wiz.state_ids.filtered(
                lambda s: (s._origin.id or s.id) not in wiz.available_state_ids.ids
            )

    @api.depends("user_id", "lead_type")
    def _compute_team_id(self):
        for wiz in self:
            if not wiz.user_id:
                continue
            user = wiz.user_id
            if wiz.team_id and user in wiz.team_id.member_ids | wiz.team_id.user_id:
                continue
            team_domain = (
                [("use_leads", "=", True)]
                if wiz.lead_type == "lead"
                else [("use_opportunities", "=", True)]
            )
            team = self.env["crm.team"]._get_default_team_id(
                user_id=user.id, domain=team_domain
            )
            wiz.team_id = team.id

    # ─── Actions ─────────────────────────────────────────────────────────

    def action_save_brief_for_mcp(self):
        """Save the brief as a persistent lead_brief record and to ir.config_parameter."""
        self.ensure_one()

        Brief = self.env["rag_odoo_mcp_server.lead_brief"]

        brief_vals = {
            "name": self.brief_title,
            "active": True,
            "lead_number": self.lead_number,
            "search_type": self.search_type,
            "lead_type": self.lead_type,
            "country_ids": [(6, 0, self.country_ids.ids)],
            "state_ids": [(6, 0, self.state_ids.ids)],
            "industry_ids": [(6, 0, self.industry_ids.ids)],
            "filter_on_size": self.filter_on_size,
            "company_size_min": self.company_size_min,
            "company_size_max": self.company_size_max,
            "contact_number": self.contact_number,
            "contact_filter_type": self.contact_filter_type,
            "preferred_role_id": self.preferred_role_id.id if self.preferred_role_id else False,
            "role_ids": [(6, 0, self.role_ids.ids)],
            "seniority_id": self.seniority_id.id if self.seniority_id else False,
            "team_id": self.team_id.id if self.team_id else False,
            "user_id": self.user_id.id if self.user_id else False,
            "tag_ids": [(6, 0, self.tag_ids.ids)],
            "lead_nature": self.lead_nature,
            "subsector_notes": self.subsector_notes or "",
            "revenue_hint": self.revenue_hint or "",
            "geo_notes": self.geo_notes or "",
            "job_titles_keywords": self.job_titles_keywords or "",
            "buyer_persona": self.buyer_persona or "",
            "product_service_fit": self.product_service_fit or "",
            "keywords_include": self.keywords_include or "",
            "keywords_exclude": self.keywords_exclude or "",
            "competitor_landscape": self.competitor_landscape or "",
            "research_sources_hint": self.research_sources_hint,
            "language_id": self.language_id.id if self.language_id else False,
            "compliance_notes": self.compliance_notes or "",
            "extra_notes": self.extra_notes or "",
            "company_id": self.company_id.id if self.company_id else False,
            "campaign_id": self.campaign_id.id if self.campaign_id else False,
            "medium_id": self.medium_id.id if self.medium_id else False,
            "source_id": self.source_id.id if self.source_id else False,
            "expected_revenue_hint": self.expected_revenue_hint,
            "currency_id": self.currency_id.id if self.currency_id else False,
            "prefer_iap_enrich": self.prefer_iap_enrich,
        }

        brief = Brief.create(brief_vals)

        # Also save to ir.config_parameter for backward-compat fallback (lead_gen_get_brief)
        payload = brief._build_payload()
        payload["llm_brief_text"] = brief._build_llm_brief_text()
        meta = {
            "saved_at": fields.Datetime.to_string(fields.Datetime.now()),
            "saved_by": self.env.user.display_name,
            "saved_uid": self.env.user.id,
            "company_id": self.company_id.id if self.company_id else None,
        }
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(WEB_LEAD_BRIEF_PARAM, json.dumps(payload, default=str))
        icp.set_param(WEB_LEAD_BRIEF_META_PARAM, json.dumps(meta, default=str))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lead brief saved for Claude"),
                "message": _(
                    "Lead brief '%s' saved and activated. "
                    "Call tool lead_gen_get_brief in Claude to start generating leads."
                ) % brief.name,
                "type": "success",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def action_open_lead_brief_wizard(self):
        """Open the lead brief wizard from the Leads list view."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Claude — lead generation brief"),
            "res_model": "rag_odoo_mcp_server.lead_brief_wizard",
            "target": "new",
            "views": [[False, "form"]],
            "context": {"is_modal": True},
        }
