# -*- coding: utf-8 -*-
"""
Models that store Claude-built dashboards inside Odoo.

A dashboard is a header (rag.mcp.dashboard) with N widgets
(rag.mcp.dashboard.widget). Widgets describe a query against an Odoo
model (model_name + domain + grouping/measure or list_fields) plus a
12-column grid layout. The OWL client action `rag_mcp_dashboard.viewer`
reads these specs and renders them with Chart.js / lists / KPIs.

The MCP tools in controllers/mcp_backend.py are the Claude-facing
interface for creating and editing these records.
"""
import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


WIDGET_TYPES = [
    ("kpi", "KPI"),
    ("bar", "Bar chart"),
    ("line", "Line chart"),
    ("pie", "Pie chart"),
    ("donut", "Donut chart"),
    ("table", "Table"),
    ("pivot", "Pivot"),
]

AGGREGATORS = [
    ("count", "Count"),
    ("sum", "Sum"),
    ("avg", "Average"),
    ("min", "Min"),
    ("max", "Max"),
]


class RagMcpDashboard(models.Model):
    _name = "rag.mcp.dashboard"
    _description = "Claude Dashboard"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    user_id = fields.Many2one(
        "res.users",
        string="Owner",
        default=lambda self: self.env.user,
        ondelete="set null",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    is_shared = fields.Boolean(
        string="Shared",
        default=False,
        help="If checked, all internal users can see this dashboard.",
    )
    widget_ids = fields.One2many(
        "rag.mcp.dashboard.widget", "dashboard_id", string="Widgets",
    )
    widget_count = fields.Integer(compute="_compute_widget_count")
    created_by_claude = fields.Boolean(default=False, readonly=True)

    @api.depends("widget_ids")
    def _compute_widget_count(self):
        for rec in self:
            rec.widget_count = len(rec.widget_ids)

    def action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "rag_mcp_dashboard.viewer",
            "name": self.name,
            "params": {"dashboard_id": self.id},
        }

    def to_spec(self):
        """JSON-friendly description, used by the MCP `dashboard_get` tool
        and by the OWL renderer."""
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "is_shared": self.is_shared,
            "owner_id": self.user_id.id if self.user_id else False,
            "owner_name": self.user_id.name if self.user_id else "",
            "company_id": self.company_id.id if self.company_id else False,
            "created_by_claude": self.created_by_claude,
            "widgets": [w.to_spec() for w in self.widget_ids],
        }


class RagMcpDashboardWidget(models.Model):
    _name = "rag.mcp.dashboard.widget"
    _description = "Claude Dashboard Widget"
    _order = "sequence, id"

    dashboard_id = fields.Many2one(
        "rag.mcp.dashboard", required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    title = fields.Char(required=True)
    widget_type = fields.Selection(WIDGET_TYPES, required=True, default="kpi")
    model_name = fields.Char(string="Odoo model", required=True)
    domain = fields.Text(default="[]")
    measure_field = fields.Char()
    measure_aggregator = fields.Selection(AGGREGATORS, default="count")
    group_by = fields.Char(
        help="Comma-separated list of field names. Date fields support "
             ":day :week :month :quarter :year (e.g. date_order:month).",
    )
    list_fields = fields.Char(
        help="Comma-separated list of field names for table/pivot widgets.",
    )
    record_limit = fields.Integer(default=20)
    col_x = fields.Integer(string="X", default=0)
    col_y = fields.Integer(string="Y", default=0)
    col_w = fields.Integer(string="Width", default=6)
    col_h = fields.Integer(string="Height", default=4)
    options_json = fields.Text(string="Options (JSON)", default="{}")

    @api.constrains("domain")
    def _check_domain_json(self):
        for rec in self:
            if not rec.domain:
                continue
            try:
                value = json.loads(rec.domain)
            except Exception as e:
                raise ValidationError("Widget %r: domain is not valid JSON (%s)" % (rec.title, e))
            if not isinstance(value, list):
                raise ValidationError("Widget %r: domain must be a JSON list." % rec.title)

    @api.constrains("options_json")
    def _check_options_json(self):
        for rec in self:
            if not rec.options_json:
                continue
            try:
                json.loads(rec.options_json)
            except Exception as e:
                raise ValidationError("Widget %r: options_json is not valid JSON (%s)" % (rec.title, e))

    @api.constrains("model_name")
    def _check_model_exists(self):
        for rec in self:
            if not rec.model_name:
                continue
            if rec.model_name not in self.env:
                raise ValidationError("Widget %r: unknown Odoo model %r." % (rec.title, rec.model_name))

    def _split_csv(self, value):
        if not value:
            return []
        return [p.strip() for p in value.split(",") if p.strip()]

    def to_spec(self):
        self.ensure_one()
        try:
            domain = json.loads(self.domain or "[]")
        except Exception:
            domain = []
        try:
            options = json.loads(self.options_json or "{}")
        except Exception:
            options = {}
        return {
            "id": self.id,
            "title": self.title,
            "widget_type": self.widget_type,
            "model": self.model_name,
            "domain": domain,
            "measure_field": self.measure_field or "",
            "measure_aggregator": self.measure_aggregator or "count",
            "group_by": self._split_csv(self.group_by),
            "list_fields": self._split_csv(self.list_fields),
            "record_limit": self.record_limit or 20,
            "layout": {
                "x": self.col_x or 0,
                "y": self.col_y or 0,
                "w": self.col_w or 6,
                "h": self.col_h or 4,
            },
            "options": options,
        }
