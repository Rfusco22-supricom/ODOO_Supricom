# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models, _


class LeadBrief(models.Model):
    _name = "rag_odoo_mcp_server.lead_brief"
    _description = "Claude lead generation brief"
    _order = "write_date desc"

    name = fields.Char("Brief title", required=True, default="Claude lead brief")
    active = fields.Boolean(
        "Active",
        default=False,
        help="Only one brief can be active at a time. The active brief is the one used by Claude.",
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
        default="lead",
    )
    country_ids = fields.Many2many(
        "res.country",
        "rag_odoo_mcp_lead_brief_country_rel",
        "brief_id",
        "country_id",
        string="Countries",
    )
    state_ids = fields.Many2many(
        "res.country.state",
        "rag_odoo_mcp_lead_brief_state_rel",
        "brief_id",
        "state_id",
        string="States",
    )
    industry_ids = fields.Many2many(
        "crm.iap.lead.industry",
        "rag_odoo_mcp_lead_brief_industry_rel",
        "brief_id",
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
        "rag_odoo_mcp_lead_brief_role_rel",
        "brief_id",
        "role_id",
        string="Other Roles",
    )
    seniority_id = fields.Many2one("crm.iap.lead.seniority", string="Seniority")

    # ── CRM defaults ─────────────────────────────────────────────────────
    team_id = fields.Many2one("crm.team", string="Sales Team")
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        domain="[('share', '=', False)]",
    )
    tag_ids = fields.Many2many(
        "crm.tag",
        "rag_odoo_mcp_lead_brief_tag_rel",
        "brief_id",
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

    # ── Metadata ─────────────────────────────────────────────────────────
    brief_json = fields.Text(
        "Brief JSON (read-only)",
        help="Auto-generated JSON payload read by the MCP tool lead_gen_get_brief.",
    )

    # ─── Lifecycle ───────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.active:
                self.search([("id", "!=", rec.id), ("active", "=", True)]).write({"active": False})
            rec._compute_brief_json()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("active"):
            self.search([("id", "not in", self.ids), ("active", "=", True)]).write({"active": False})
        # Recompute JSON if any content field changed
        _skip = {"brief_json", "active", "write_date", "create_date", "__last_update"}
        if set(vals.keys()) - _skip:
            for rec in self:
                rec._compute_brief_json()
        return res

    def _compute_brief_json(self):
        """Rebuild the JSON payload stored on the record."""
        for rec in self:
            payload = rec._build_payload()
            payload["llm_brief_text"] = rec._build_llm_brief_text()
            payload["saved_at"] = fields.Datetime.to_string(fields.Datetime.now())
            payload["saved_by"] = self.env.user.display_name
            rec.brief_json = json.dumps(payload, default=str)

    def _build_payload(self):
        """Build the full brief payload dict."""
        self.ensure_one()
        return {
            "brief_title": self.name,
            "lead_number": self.lead_number,
            "search_type": self.search_type,
            "lead_type": self.lead_type,
            "country_ids": self.country_ids.ids,
            "country_names": self.country_ids.mapped("name"),
            "state_ids": self.state_ids.ids,
            "state_names": self.state_ids.mapped("name"),
            "industry_ids": self.industry_ids.ids,
            "industry_names": self.industry_ids.mapped("name"),
            "filter_on_size": self.filter_on_size,
            "company_size_min": self.company_size_min,
            "company_size_max": self.company_size_max,
            "contact_number": self.contact_number,
            "contact_filter_type": self.contact_filter_type,
            "preferred_role_id": self.preferred_role_id.id if self.preferred_role_id else None,
            "preferred_role_name": self.preferred_role_id.name if self.preferred_role_id else None,
            "role_ids": self.role_ids.ids,
            "role_names": self.role_ids.mapped("name"),
            "seniority_id": self.seniority_id.id if self.seniority_id else None,
            "seniority_name": self.seniority_id.name if self.seniority_id else None,
            "team_id": self.team_id.id if self.team_id else None,
            "team_name": self.team_id.name if self.team_id else None,
            "user_id": self.user_id.id if self.user_id else None,
            "user_name": self.user_id.name if self.user_id else None,
            "tag_ids": self.tag_ids.ids,
            "tag_names": self.tag_ids.mapped("name"),
            "lead_nature": self.lead_nature,
            "subsector_notes": self.subsector_notes,
            "revenue_hint": self.revenue_hint,
            "geo_notes": self.geo_notes,
            "job_titles_keywords": self.job_titles_keywords,
            "buyer_persona": self.buyer_persona,
            "product_service_fit": self.product_service_fit,
            "keywords_include": self.keywords_include,
            "keywords_exclude": self.keywords_exclude,
            "competitor_landscape": self.competitor_landscape,
            "research_sources_hint": self.research_sources_hint,
            "language": self.language_id.code if self.language_id else None,
            "company_id": self.company_id.id if self.company_id else None,
            "campaign_id": self.campaign_id.id if self.campaign_id else None,
            "medium_id": self.medium_id.id if self.medium_id else None,
            "source_id": self.source_id.id if self.source_id else None,
            "expected_revenue_hint": self.expected_revenue_hint,
            "currency_id": self.currency_id.id if self.currency_id else None,
            "prefer_web_enrich": self.prefer_iap_enrich,
            "compliance_notes": self.compliance_notes,
            "extra_notes": self.extra_notes,
        }

    def _build_llm_brief_text(self):
        """Build the human-readable brief text for Claude."""
        self.ensure_one()
        lines = [
            "=== LEAD GENERATION BRIEF — ACT ON THIS IMMEDIATELY ===",
            "",
            "You must now: use your knowledge to find real companies matching the criteria below,",
            "then call crm_lead_create for each one. Do NOT ask for permission. Just do it.",
            "",
            "**Title:** %s" % (self.name or ""),
            "**Target:** %s | **Type:** %s | **Leads wanted:** %s"
            % (self.search_type, self.lead_type, self.lead_number),
            "**Industries:** %s" % (", ".join(self.industry_ids.mapped("name")) or "—"),
            "**Countries:** %s" % (", ".join(self.country_ids.mapped("name")) or "—"),
            "**States:** %s" % (", ".join(self.state_ids.mapped("name")) or "—"),
            "**Company size:** %s — %s to %s employees"
            % (self.filter_on_size, self.company_size_min, self.company_size_max),
            "**Geo / revenue notes:** %s | %s" % (self.geo_notes or "—", self.revenue_hint or "—"),
        ]
        if self.search_type == "people":
            lines.extend([
                "**Contacts:** %s per company | filter: %s" % (self.contact_number, self.contact_filter_type),
                "**Role / seniority:** %s / %s / %s" % (
                    self.preferred_role_id.name if self.preferred_role_id else "—",
                    ", ".join(self.role_ids.mapped("name")) or "—",
                    self.seniority_id.name if self.seniority_id else "—",
                ),
            ])
        lines.extend([
            "**Sales team / salesperson:** %s / %s" % (
                self.team_id.display_name if self.team_id else "—",
                self.user_id.display_name if self.user_id else "—",
            ),
            "**Default tags:** %s" % (", ".join(self.tag_ids.mapped("name")) or "—"),
            "**Lead nature:** %s | **Sub-sector:** %s" % (self.lead_nature, self.subsector_notes or "—"),
            "**Job titles / keywords:** %s" % (self.job_titles_keywords or "—"),
            "**Buyer persona:** %s" % ((self.buyer_persona or "—")[:500]),
            "**What we sell:** %s" % ((self.product_service_fit or "—")[:500]),
            "**Keywords +/-:** %s | %s" % (self.keywords_include or "—", self.keywords_exclude or "—"),
            "**Competitors:** %s | **Research angle:** %s"
            % (self.competitor_landscape or "—", self.research_sources_hint or "—"),
            "**Language:** %s" % (self.language_id.display_name if self.language_id else "—"),
            "**UTM:** campaign %s | medium %s | source %s" % (
                self.campaign_id.id or "—",
                self.medium_id.id or "—",
                self.source_id.id or "—",
            ),
            "**Deal size hint:** %s | **Enrich preferred:** %s"
            % (self.expected_revenue_hint or "—", self.prefer_iap_enrich),
            "**Compliance:** %s" % (self.compliance_notes or "—"),
            "**Extra notes:** %s" % (self.extra_notes or "—"),
            "",
            "ACTION: find %s matching companies now, call crm_lead_create for each." % self.lead_number,
            "Include source URL and research notes in the description field of each lead.",
        ])
        return "\n".join(lines)

    def action_activate(self):
        self.ensure_one()
        self.search([("id", "!=", self.id), ("active", "=", True)]).write({"active": False})
        self.active = True
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Brief activated"),
                "message": _("'%s' is now the active lead brief for Claude.") % self.name,
                "type": "success",
            },
        }

    def action_deactivate(self):
        self.ensure_one()
        self.active = False
