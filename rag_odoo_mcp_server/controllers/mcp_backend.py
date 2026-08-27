# -*- coding: utf-8 -*-
"""
MCP tool backend using Odoo's cursor and environment.
Used by the in-Odoo MCP controller; no standalone dependencies.
Supports read-only SQL tools and ORM-based data retrieval/write (search_read, create, write, unlink, execute).
"""
import json
import re

# Access Manager (optional feature) — ported access-rules MCP tools.
from . import access_management_tools

# SEO Manager tools (optional feature). On-site SEO audit + fixes for the Odoo
# Website app. Merged into TOOL_DEFINITIONS / DISPATCH below and gated by the
# SEO Manager feature flag. The `website` module is resolved at runtime, so
# importing this on an instance without Website is safe.
from . import seo_tools


def _identifier_ok(name):
    """Allow only safe SQL identifiers (schema/table names)."""
    return name and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name)


def _rows_to_dicts(cr, rows=None):
    """Convert cr.fetchall() + cr.description to list of dicts."""
    if rows is None:
        rows = cr.fetchall()
    if not cr.description or not rows:
        return []
    keys = [d[0] for d in cr.description]
    result = []
    for row in rows:
        r = dict(zip(keys, row))
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
            elif isinstance(v, (bytes, bytearray)):
                r[k] = v.decode("utf-8", errors="replace")
        result.append(r)
    return result


def list_tables(cr, env, schema="public"):
    if not _identifier_ok(schema):
        return []
    cr.execute("""
        SELECT c.relname AS table_name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind = 'r'
        ORDER BY c.relname
    """, (schema,))
    return _rows_to_dicts(cr)


def describe_table(cr, env, table_name, schema="public"):
    if not _identifier_ok(schema) or not _identifier_ok(table_name):
        return []
    cr.execute("""
        SELECT a.attname AS column_name,
               pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
               NOT a.attnotnull AS nullable,
               pg_get_expr(d.adbin, d.adrelid) AS default_expr
        FROM pg_attribute a
        LEFT JOIN pg_attrdef d ON a.attrelid = d.adrelid AND a.attnum = d.adnum
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = %s AND c.relname = %s
          AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
    """, (schema, table_name))
    return _rows_to_dicts(cr)


def get_table_row_count(cr, env, table_name, schema="public"):
    if not _identifier_ok(schema) or not _identifier_ok(table_name):
        raise ValueError("Invalid schema or table name")
    # Identifiers validated: only [a-zA-Z0-9_], no SQL injection
    cr.execute("SELECT COUNT(*) FROM %s.%s" % (schema, table_name))
    return cr.fetchone()[0]


def run_readonly_query(cr, env, query, max_rows=500):
    q = query.strip()
    if not q.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed. Got: " + q[:50])
    if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE)\b", q, re.I):
        raise ValueError("Query must be read-only (SELECT only).")
    cr.execute(q)
    rows = cr.fetchall()
    rows = rows[:max_rows] if len(rows) > max_rows else rows
    columns = [d[0] for d in cr.description] if cr.description else []
    result = _rows_to_dicts(cr, rows)
    return {"row_count": len(result), "columns": columns, "rows": result}


def get_odoo_models_info(cr, env):
    cr.execute("""
        SELECT model, name, info
        FROM ir_model
        WHERE model IS NOT NULL AND model != ''
        ORDER BY model
        LIMIT 500
    """)
    return _rows_to_dicts(cr)


def get_table_schema_pg(cr, env, table_name, schema="public"):
    cols = describe_table(cr, env, table_name, schema or "public")
    if not _identifier_ok(schema) or not _identifier_ok(table_name):
        return {"table": table_name, "schema": schema or "public", "columns": [], "indexes": []}
    cr.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s AND tablename = %s
    """, (schema or "public", table_name))
    indexes = _rows_to_dicts(cr)
    return {"table": table_name, "schema": schema or "public", "columns": cols, "indexes": indexes}


# ---------------------------------------------------------------------------
# ORM-based tools (data retrieval and management)
# ---------------------------------------------------------------------------

def _parse_domain(domain):
    """Parse domain from JSON string or list. Return a list of tuples."""
    if domain is None:
        return []
    if isinstance(domain, list):
        return domain
    if isinstance(domain, str):
        return json.loads(domain)
    return []


def _parse_values(values):
    """Parse values dict from JSON string or dict."""
    if values is None:
        return {}
    if isinstance(values, dict):
        return values
    if isinstance(values, str):
        return json.loads(values)
    return {}


def _parse_ids(ids):
    """Parse ids: int, list of int, or JSON string."""
    if ids is None:
        return []
    if isinstance(ids, int):
        return [ids]
    if isinstance(ids, list):
        return [int(x) for x in ids]
    if isinstance(ids, str):
        data = json.loads(ids)
        return [data] if isinstance(data, int) else [int(x) for x in data]
    return []


def _serialize_value(v):
    """Convert Odoo record/value to JSON-serializable (e.g. for display)."""
    if hasattr(v, "isoformat"):  # date, datetime
        return v.isoformat()
    if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], int):
        return v  # (id, name) display
    if hasattr(v, "id"):
        return {"id": v.id, "display_name": getattr(v, "display_name", str(v))}
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="replace")
    return v


def odoo_search_read(cr, env, model, domain=None, fields=None, limit=100, order=None):
    """
    Search and read records from an Odoo model (ORM).
    Use for: customers from Spain, products with low stock, today's sales orders, unpaid invoices, etc.
    """
    Model = env.get(model)
    if Model is None:
        raise ValueError(_model_not_found_msg(model))
    domain = _parse_domain(domain)
    if fields is None:
        fields = []
    if isinstance(fields, str):
        fields = json.loads(fields) if fields.strip() else []
    limit = min(int(limit), 500) if limit else 100
    order = order or ""
    records = Model.search_read(domain, fields or None, limit=limit, order=order or None)
    # Serialize for JSON (dates, many2one tuples, etc.)
    out = []
    for r in records:
        row = {}
        for k, v in r.items():
            row[k] = _serialize_value(v)
        out.append(row)
    return {"model": model, "count": len(out), "records": out}


def _model_not_found_msg(model):
    return (
        "Model not found: %s. Use get_odoo_models_info to list available models (names are module.model, e.g. website.website)."
        % model
    )


def odoo_create(cr, env, model, values):
    """Create one record in an Odoo model. values: dict of field names to values (JSON or dict)."""
    Model = env.get(model)
    if Model is None:
        raise ValueError(_model_not_found_msg(model))
    values = _parse_values(values)
    if not values:
        raise ValueError("values is required and must not be empty")
    record = Model.create(values)
    return {"model": model, "id": record.id, "created": True, "display_name": record.display_name}


def odoo_write(cr, env, model, ids, values):
    """Update record(s) in an Odoo model. ids: single id or list; values: dict (JSON or dict)."""
    Model = env.get(model)
    if Model is None:
        raise ValueError(_model_not_found_msg(model))
    ids = _parse_ids(ids)
    if not ids:
        raise ValueError("ids is required (integer or list of ids)")
    values = _parse_values(values)
    if not values:
        raise ValueError("values is required and must not be empty")
    records = Model.browse(ids)
    records.write(values)
    return {"model": model, "ids": ids, "updated": len(records)}


def odoo_unlink(cr, env, model, ids):
    """Delete record(s) from an Odoo model. ids: single id or list (JSON or list)."""
    Model = env.get(model)
    if Model is None:
        raise ValueError(_model_not_found_msg(model))
    ids = _parse_ids(ids)
    if not ids:
        raise ValueError("ids is required (integer or list of ids)")
    records = Model.browse(ids)
    n = len(records)
    records.unlink()
    return {"model": model, "ids": ids, "deleted": n}


def odoo_execute(cr, env, model, ids, method_name, args=None, kwargs=None):
    """
    Call a method on record(s), e.g. action_confirm on sale.order.
    args: list (JSON array), kwargs: dict (JSON object). Optional.
    """
    Model = env.get(model)
    if Model is None:
        raise ValueError(_model_not_found_msg(model))
    ids = _parse_ids(ids)
    if not ids:
        raise ValueError("ids is required (integer or list of ids)")
    args = json.loads(args) if isinstance(args, str) else (args or [])
    kwargs = json.loads(kwargs) if isinstance(kwargs, str) else (kwargs or {})
    records = Model.browse(ids)
    method = getattr(records, method_name, None)
    if method is None:
        raise ValueError("Method not found: %s on %s" % (method_name, model))
    result = method(*args, **kwargs)
    # Serialize result for display
    if result is None or isinstance(result, (bool, int, float, str)):
        pass  # keep as-is
    elif hasattr(result, "id") and not isinstance(result, (list, tuple)):
        result = {"id": result.id, "display_name": getattr(result, "display_name", str(result))}
    elif isinstance(result, (list, tuple)) and result and hasattr(result[0], "id"):
        result = [{"id": r.id, "display_name": getattr(r, "display_name", str(r))} for r in result]
    elif hasattr(result, "isoformat"):
        result = result.isoformat()
    return {"model": model, "ids": ids, "method": method_name, "result": result}


def _format_search_read(result):
    lines = ["Model: %s | Records: %s" % (result.get("model", ""), result.get("count", 0)), ""]
    for r in result.get("records", [])[:50]:
        lines.append("  " + str(r))
    if result.get("count", 0) > 50:
        lines.append("  ... and %s more" % (result["count"] - 50))
    return "\n".join(lines)


def _format_create(result):
    return "Created %s (id=%s): %s" % (result.get("model", ""), result.get("id"), result.get("display_name", ""))


def _format_write(result):
    return "Updated %s record(s) in %s (ids=%s)" % (result.get("updated", 0), result.get("model", ""), result.get("ids", []))


def _format_unlink(result):
    return "Deleted %s record(s) from %s (ids=%s)" % (result.get("deleted", 0), result.get("model", ""), result.get("ids", []))


def _format_execute(result):
    return "Executed %s on %s (ids=%s). Result: %s" % (
        result.get("method", ""), result.get("model", ""), result.get("ids", []), result.get("result", "")
    )


# Formatters (same output as standalone mcp_server.py)
def _format_list_tables(result):
    lines = ["Tables in schema (total: %s):" % len(result), ""]
    for r in result:
        lines.append("  - %s  (%s)" % (r.get("table_name", "?"), r.get("size", "?")))
    return "\n".join(lines)


def _format_describe(result):
    if not result:
        return "No columns found (table or schema may not exist)."
    lines = ["Column | Type | Nullable | Default", "------ | ---- | -------- | -------"]
    for r in result:
        lines.append("%s | %s | %s | %s" % (r.get("column_name"), r.get("data_type"), r.get("nullable"), r.get("default_expr") or ""))
    return "\n".join(lines)


def _format_run_query(result):
    rows = result.get("rows", [])
    cols = result.get("columns", [])
    count = result.get("row_count", 0)
    if not cols:
        return "No columns (empty result). Row count: %s" % count
    header = " | ".join(cols)
    sep = "-" * min(80, len(header))
    lines = ["Rows returned: %s" % count, "Columns: %s" % cols, "", header, sep]
    for r in rows[:100]:
        line = " | ".join(str(r.get(c, "")) for c in cols)
        lines.append(line)
    if len(rows) > 100:
        lines.append("... and %s more rows" % (len(rows) - 100))
    return "\n".join(lines)


def _format_odoo_models(result):
    lines = ["Odoo models (ir_model) — %s entries:" % len(result), ""]
    for r in result[:80]:
        lines.append("  - %s  |  %s" % (r.get("model", ""), r.get("name") or ""))
    if len(result) > 80:
        lines.append("  ... and %s more" % (len(result) - 80))
    return "\n".join(lines)


def _format_schema_pg(result):
    lines = ["Table: %s.%s" % (result.get("schema", "public"), result.get("table", "")), ""]
    lines.append("Columns:")
    for c in result.get("columns", []):
        lines.append("  - %s: %s (nullable=%s)" % (c.get("column_name"), c.get("data_type"), c.get("nullable")))
    lines.append("")
    lines.append("Indexes:")
    for ix in result.get("indexes", []):
        lines.append("  - %s" % ix.get("indexname", ""))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude Dashboards — MCP tools for rag.mcp.dashboard / rag.mcp.dashboard.widget
# ---------------------------------------------------------------------------

# Field types we treat as numeric measures (sum/avg/min/max/count).
_NUMERIC_FIELD_TYPES = {"integer", "float", "monetary"}
# Field types we treat as groupable.
_GROUPABLE_FIELD_TYPES = {
    "char", "selection", "many2one", "boolean", "date", "datetime",
}
# Prefixes / names we hide from schema-help output (mixin / technical fields).
_HIDDEN_FIELD_PREFIXES = (
    "message_", "activity_", "image_", "access_",
)
_HIDDEN_FIELD_NAMES = frozenset({
    "display_name", "__last_update", "create_uid", "create_date",
    "write_uid", "write_date",
})


def _widget_field_to_vals(spec):
    """Translate a JSON spec dict into rag.mcp.dashboard.widget create vals.
    Returns (vals, errors). Caller decides whether to fail or skip.
    """
    errors = []
    vals = {}
    if not isinstance(spec, dict):
        return None, ["widget spec must be an object"]
    title = (spec.get("title") or "").strip()
    if not title:
        errors.append("widget.title is required")
    widget_type = (spec.get("widget_type") or spec.get("type") or "").strip()
    if widget_type not in {"kpi", "bar", "line", "pie", "donut", "table", "pivot"}:
        errors.append("widget.widget_type must be one of: kpi, bar, line, pie, donut, table, pivot")
    model_name = (spec.get("model") or spec.get("model_name") or "").strip()
    if not model_name:
        errors.append("widget.model is required")
    domain = spec.get("domain", [])
    if isinstance(domain, list):
        domain_str = json.dumps(domain)
    elif isinstance(domain, str) and domain.strip():
        try:
            json.loads(domain)
            domain_str = domain
        except Exception as e:
            errors.append("widget.domain is not valid JSON: %s" % e)
            domain_str = "[]"
    else:
        domain_str = "[]"
    options = spec.get("options")
    if options is None:
        options_str = "{}"
    elif isinstance(options, dict):
        options_str = json.dumps(options)
    elif isinstance(options, str) and options.strip():
        try:
            json.loads(options)
            options_str = options
        except Exception as e:
            errors.append("widget.options is not valid JSON: %s" % e)
            options_str = "{}"
    else:
        options_str = "{}"
    aggregator = (spec.get("measure_aggregator") or spec.get("aggregator") or "count").strip()
    if aggregator not in {"count", "sum", "avg", "min", "max"}:
        errors.append("widget.measure_aggregator must be one of: count, sum, avg, min, max")

    def _csv(value):
        if value is None:
            return ""
        if isinstance(value, list):
            return ",".join(str(v).strip() for v in value if str(v).strip())
        return str(value).strip()

    layout = spec.get("layout") or {}
    if not isinstance(layout, dict):
        layout = {}
    vals.update({
        "title": title,
        "widget_type": widget_type,
        "model_name": model_name,
        "domain": domain_str,
        "measure_field": (spec.get("measure_field") or "").strip() or False,
        "measure_aggregator": aggregator,
        "group_by": _csv(spec.get("group_by")),
        "list_fields": _csv(spec.get("list_fields")),
        "record_limit": int(spec.get("record_limit") or 20),
        "col_x": int(layout.get("x", spec.get("col_x", 0)) or 0),
        "col_y": int(layout.get("y", spec.get("col_y", 0)) or 0),
        "col_w": int(layout.get("w", spec.get("col_w", 6)) or 6),
        "col_h": int(layout.get("h", spec.get("col_h", 4)) or 4),
        "options_json": options_str,
        "sequence": int(spec.get("sequence") or 10),
    })
    return vals, errors


def _coerce_widgets_arg(widgets):
    """Accept a list of dicts or a JSON string; return list of dicts."""
    if widgets is None:
        return []
    if isinstance(widgets, str):
        try:
            widgets = json.loads(widgets)
        except Exception as e:
            raise ValueError("widgets is not valid JSON: %s" % e)
    if isinstance(widgets, dict):
        widgets = [widgets]
    if not isinstance(widgets, list):
        raise ValueError("widgets must be a JSON array of widget objects")
    return widgets


def _dashboard_url_hint(dashboard_id):
    return "Open in Odoo: navigate to 'Claude Dashboards' menu, or use action_open on rag.mcp.dashboard id=%s" % dashboard_id


def _user_dashboard_domain(env, mine_only):
    """Domain that mirrors the record rule in dashboard_security.xml so that
    SUPERUSER queries from the MCP layer still respect ownership/sharing."""
    user = env.user
    if mine_only:
        return [("user_id", "=", user.id)]
    if user._is_admin():
        return []
    return ["|", ("user_id", "=", user.id), ("is_shared", "=", True)]


def dashboard_list(cr, env, mine_only=False, company_id=None):
    """List dashboards visible to the calling user."""
    Dashboard = env["rag.mcp.dashboard"]
    domain = _user_dashboard_domain(env, bool(mine_only))
    if company_id:
        domain = list(domain) + [("company_id", "=", int(company_id))]
    records = Dashboard.search(domain, order="sequence, id")
    return {
        "count": len(records),
        "dashboards": [
            {
                "id": d.id,
                "name": d.name,
                "owner_id": d.user_id.id if d.user_id else False,
                "owner_name": d.user_id.name if d.user_id else "",
                "is_shared": d.is_shared,
                "widget_count": d.widget_count,
                "created_by_claude": d.created_by_claude,
            }
            for d in records
        ],
    }


def dashboard_get(cr, env, dashboard_id, company_id=None):
    """Return one dashboard with all widget specs."""
    Dashboard = env["rag.mcp.dashboard"]
    rec = Dashboard.browse(int(dashboard_id))
    if not rec.exists():
        raise ValueError("Dashboard %s not found" % dashboard_id)
    if company_id and rec.company_id and rec.company_id.id != int(company_id):
        raise ValueError("Dashboard %s does not match company_id %s" % (dashboard_id, company_id))
    rec.check_access_rights("read")
    rec.check_access_rule("read")
    spec = rec.to_spec()
    spec["url_hint"] = _dashboard_url_hint(rec.id)
    return spec


def dashboard_get_schema_help(cr, env, model, company_id=None):
    """Return field metadata to help an LLM build correct widget specs.
    Filters out technical/mixin fields and groups results into numeric/groupable/date.
    """
    Model = env.get(model)
    if Model is None:
        raise ValueError(_model_not_found_msg(model))
    fields_info = Model.fields_get()
    numeric_fields = []
    groupable_fields = []
    date_fields = []
    for fname, finfo in fields_info.items():
        if fname in _HIDDEN_FIELD_NAMES:
            continue
        if any(fname.startswith(p) for p in _HIDDEN_FIELD_PREFIXES):
            continue
        if not finfo.get("store", True):
            continue
        ftype = finfo.get("type")
        label = finfo.get("string") or fname
        entry = {"name": fname, "type": ftype, "label": label}
        if ftype == "many2one":
            entry["relation"] = finfo.get("relation")
        if ftype == "selection":
            entry["selection"] = list(finfo.get("selection") or [])
        if ftype in _NUMERIC_FIELD_TYPES:
            numeric_fields.append(entry)
        if ftype in ("date", "datetime"):
            date_fields.append(entry)
            groupable_fields.append(entry)
        elif ftype in _GROUPABLE_FIELD_TYPES:
            groupable_fields.append(entry)
    numeric_fields.sort(key=lambda x: x["name"])
    groupable_fields.sort(key=lambda x: x["name"])
    date_fields.sort(key=lambda x: x["name"])
    return {
        "model": model,
        "numeric_fields": numeric_fields,
        "groupable_fields": groupable_fields,
        "date_fields": date_fields,
    }


def dashboard_create(cr, env, name, widgets, description=None, is_shared=False, company_id=None):
    """Create a dashboard with N widgets in one shot. Returns id + summary."""
    if not name or not str(name).strip():
        raise ValueError("name is required")
    widgets_list = _coerce_widgets_arg(widgets)
    widget_cmds = []
    errors = []
    for idx, w in enumerate(widgets_list):
        vals, errs = _widget_field_to_vals(w)
        if errs:
            errors.append({"index": idx, "errors": errs})
            continue
        widget_cmds.append((0, 0, vals))
    if errors:
        raise ValueError("Invalid widgets: %s" % json.dumps(errors))
    create_vals = {
        "name": str(name).strip(),
        "description": description or "",
        "is_shared": bool(is_shared),
        "created_by_claude": True,
        "widget_ids": widget_cmds,
    }
    if company_id:
        create_vals["company_id"] = int(company_id)
    rec = env["rag.mcp.dashboard"].create(create_vals)
    return {
        "id": rec.id,
        "name": rec.name,
        "widget_count": rec.widget_count,
        "is_shared": rec.is_shared,
        "url_hint": _dashboard_url_hint(rec.id),
    }


def dashboard_update(cr, env, dashboard_id, name=None, description=None, is_shared=None):
    """Update header fields of a dashboard."""
    rec = env["rag.mcp.dashboard"].browse(int(dashboard_id))
    if not rec.exists():
        raise ValueError("Dashboard %s not found" % dashboard_id)
    vals = {}
    if name is not None:
        vals["name"] = str(name).strip()
    if description is not None:
        vals["description"] = description
    if is_shared is not None:
        vals["is_shared"] = bool(is_shared)
    if not vals:
        return {"id": rec.id, "updated": False}
    rec.write(vals)
    return {"id": rec.id, "updated": True, "fields": list(vals.keys())}


def dashboard_add_widget(cr, env, dashboard_id, widget, company_id=None):
    """Add one widget to an existing dashboard."""
    rec = env["rag.mcp.dashboard"].browse(int(dashboard_id))
    if not rec.exists():
        raise ValueError("Dashboard %s not found" % dashboard_id)
    spec = widget
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception as e:
            raise ValueError("widget is not valid JSON: %s" % e)
    vals, errs = _widget_field_to_vals(spec)
    if errs:
        raise ValueError("Invalid widget: %s" % "; ".join(errs))
    vals["dashboard_id"] = rec.id
    w = env["rag.mcp.dashboard.widget"].create(vals)
    return {"id": w.id, "dashboard_id": rec.id, "title": w.title, "widget_type": w.widget_type}


def dashboard_remove_widget(cr, env, widget_id, company_id=None):
    """Delete one widget."""
    w = env["rag.mcp.dashboard.widget"].browse(int(widget_id))
    if not w.exists():
        raise ValueError("Widget %s not found" % widget_id)
    parent_id = w.dashboard_id.id
    title = w.title
    w.unlink()
    return {"id": int(widget_id), "dashboard_id": parent_id, "title": title, "deleted": True}


def dashboard_delete(cr, env, dashboard_id, company_id=None):
    """Delete a dashboard (cascades to widgets)."""
    rec = env["rag.mcp.dashboard"].browse(int(dashboard_id))
    if not rec.exists():
        raise ValueError("Dashboard %s not found" % dashboard_id)
    name = rec.name
    rec.unlink()
    return {"id": int(dashboard_id), "name": name, "deleted": True}


# Formatters --------------------------------------------------------------

def _format_dashboard_list(result):
    lines = ["Dashboards: %s" % result.get("count", 0), ""]
    for d in result.get("dashboards", []):
        flags = []
        if d.get("is_shared"):
            flags.append("shared")
        if d.get("created_by_claude"):
            flags.append("by-claude")
        suffix = (" [%s]" % ",".join(flags)) if flags else ""
        lines.append("  - id=%s | %s | owner=%s | widgets=%s%s" % (
            d.get("id"), d.get("name"), d.get("owner_name") or "?",
            d.get("widget_count", 0), suffix,
        ))
    return "\n".join(lines)


def _format_dashboard_get(result):
    lines = [
        "Dashboard #%s: %s" % (result.get("id"), result.get("name")),
        "Owner: %s | Shared: %s | Widgets: %s" % (
            result.get("owner_name") or "?",
            result.get("is_shared"),
            len(result.get("widgets") or []),
        ),
    ]
    if result.get("description"):
        lines.append("Description: %s" % result["description"])
    lines.append("")
    for w in result.get("widgets", []):
        layout = w.get("layout") or {}
        lines.append(
            "  - widget_id=%s | %s | %s on %s | layout=(x=%s,y=%s,w=%s,h=%s)" % (
                w.get("id"), w.get("title"), w.get("widget_type"),
                w.get("model"), layout.get("x"), layout.get("y"),
                layout.get("w"), layout.get("h"),
            )
        )
    if result.get("url_hint"):
        lines.append("")
        lines.append(result["url_hint"])
    return "\n".join(lines)


def _format_dashboard_schema(result):
    model = result.get("model", "")
    lines = ["Schema help for %s" % model, ""]
    lines.append("Numeric fields (use as measure_field):")
    for f in result.get("numeric_fields", [])[:80]:
        lines.append("  - %s (%s) — %s" % (f["name"], f["type"], f.get("label", "")))
    lines.append("")
    lines.append("Groupable fields (use in group_by):")
    for f in result.get("groupable_fields", [])[:80]:
        extra = ""
        if f.get("relation"):
            extra = " -> %s" % f["relation"]
        elif f.get("selection"):
            extra = " values=%s" % [s[0] for s in f["selection"][:8]]
        lines.append("  - %s (%s)%s" % (f["name"], f["type"], extra))
    lines.append("")
    lines.append("Date fields (support :day :week :month :quarter :year):")
    for f in result.get("date_fields", [])[:30]:
        lines.append("  - %s (%s)" % (f["name"], f["type"]))
    return "\n".join(lines)


def _format_dashboard_create(result):
    return (
        "Created dashboard #%s '%s' with %s widget(s). %s"
        % (result.get("id"), result.get("name"), result.get("widget_count"),
           result.get("url_hint", ""))
    )


def _format_dashboard_update(result):
    if not result.get("updated"):
        return "Dashboard #%s — nothing to update." % result.get("id")
    return "Updated dashboard #%s. Fields: %s" % (result.get("id"), result.get("fields", []))


def _format_dashboard_add_widget(result):
    return "Added widget #%s '%s' (%s) to dashboard #%s" % (
        result.get("id"), result.get("title"), result.get("widget_type"),
        result.get("dashboard_id"),
    )


def _format_dashboard_remove_widget(result):
    return "Deleted widget #%s '%s' from dashboard #%s" % (
        result.get("id"), result.get("title"), result.get("dashboard_id"),
    )


def _format_dashboard_delete(result):
    return "Deleted dashboard #%s '%s'" % (result.get("id"), result.get("name"))


# ═══════════════════════════════════════════════════════════════════════════
# Multi-company helper used by the lead-gen and mailing brief tools.
# ═══════════════════════════════════════════════════════════════════════════

def _apply_company_context(env, company_id):
    """Apply company context to the environment if company_id is provided."""
    if company_id is None:
        return env
    company_id = int(company_id)
    company = env['res.company'].browse(company_id)
    if not company.exists():
        raise ValueError(
            "Company not found: id=%s. Pass a valid res.company id." % company_id
        )
    if hasattr(env, 'with_company'):
        return env.with_company(company_id)
    return env.with_context(allowed_company_ids=[company_id])


# ---------------------------------------------------------------------------
# Lead generation: dedup utilities (self-contained, no dependency on rag_lead_generator)
# ---------------------------------------------------------------------------

def _normalize_text(value):
    """Strip, lowercase, collapse whitespace."""
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _normalize_domain_name(website):
    """Extract bare domain from a URL (strip protocol, www., trailing dots)."""
    website = _normalize_text(website)
    if not website:
        return ""
    website = re.sub(r"^https?://", "", website)
    website = website.split("/")[0]
    if website.startswith("www."):
        website = website[4:]
    return website.strip(".")


def _build_lead_fingerprint(lead_data):
    """Build a dedup fingerprint string from lead data dict."""
    website_domain = _normalize_domain_name(lead_data.get("website"))
    partner_name = _normalize_text(lead_data.get("partner_name"))
    email_from = _normalize_text(lead_data.get("email_from"))
    country = _normalize_text(lead_data.get("country"))
    city = _normalize_text(lead_data.get("city"))
    contact_name = _normalize_text(lead_data.get("contact_name"))
    phone = _normalize_text(lead_data.get("phone"))

    if website_domain:
        return "domain:%s" % website_domain
    if email_from and "@" in email_from:
        return "email:%s" % email_from
    if partner_name and country:
        return "company:%s|country:%s" % (partner_name, country)
    if partner_name and city:
        return "company:%s|city:%s" % (partner_name, city)
    if partner_name:
        return "company:%s" % partner_name
    if contact_name and phone:
        return "contact:%s|phone:%s" % (contact_name, phone)
    if contact_name and email_from:
        return "contact:%s|email:%s" % (contact_name, email_from)
    return ""


def _collect_existing_lead_fingerprints(env, lead_type, company_id):
    """Return a set of fingerprint strings for existing crm.lead records."""
    domain = [("type", "=", lead_type)]
    if company_id:
        domain.append(("company_id", "=", int(company_id)))

    existing = env["crm.lead"].search_read(
        domain,
        fields=["partner_name", "email_from", "website", "country_id", "city"],
        limit=5000,
    )

    fingerprints = set()
    for row in existing:
        country_name = ""
        if row.get("country_id") and isinstance(row["country_id"], (list, tuple)) and len(row["country_id"]) > 1:
            country_name = row["country_id"][1]
        fp = _build_lead_fingerprint({
            "website": row.get("website"),
            "partner_name": row.get("partner_name"),
            "email_from": row.get("email_from"),
            "country": country_name,
            "city": row.get("city"),
        })
        if fp:
            fingerprints.add(fp)
    return fingerprints


# ---------------------------------------------------------------------------
# Lead generation: MCP tools
# ---------------------------------------------------------------------------

_LEAD_BRIEF_PARAM = "rag_lead_generator.web_lead_brief_json"
_LEAD_BRIEF_META_PARAM = "rag_lead_generator.web_lead_brief_meta_json"


def lead_gen_get_brief(cr, env, company_id=None):
    """Read the lead generation brief saved by the user in Odoo (CRM > Leads > 'Claude Lead Brief' button)."""
    brief = None
    meta = {}

    # 1) Try persistent brief model (this module first, then rag_mcp_crm_manager for back-compat)
    for _model_name in ("rag_odoo_mcp_server.lead_brief", "rag_mcp_crm_manager.lead_brief"):
        Brief = env.get(_model_name)
        if Brief is None:
            continue
        active_brief = Brief.search([("active", "=", True)], limit=1)
        if not active_brief:
            continue
        active_brief._compute_brief_json()
        try:
            brief = json.loads(active_brief.brief_json or "{}")
            meta = {
                "saved_at": brief.pop("saved_at", None),
                "saved_by": brief.pop("saved_by", None),
                "source": _model_name,
            }
            break
        except (json.JSONDecodeError, TypeError):
            brief = None

    # 2) Fallback: ir.config_parameter (backward compat with rag_lead_generator)
    if brief is None:
        icp = env["ir.config_parameter"].sudo()
        brief_raw = icp.get_param(_LEAD_BRIEF_PARAM, "")
        meta_raw = icp.get_param(_LEAD_BRIEF_META_PARAM, "")

        if not brief_raw:
            return {
                "status": "no_brief",
                "message": (
                    "No lead generation brief found. "
                    "Ask the user to go to CRM > Leads, click 'Claude Lead Brief' button, "
                    "fill the targeting form, and click 'Save for Claude (MCP)' to save the brief. "
                    "If you don't see that button: " + _CRM_MANAGER_HINT
                ),
            }

        try:
            brief = json.loads(brief_raw)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "message": "Brief JSON is corrupted. Ask the user to re-save it."}

        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        meta["source"] = "ir.config_parameter"

    # Extract defaults that Claude should pass to crm_lead_create
    defaults = {}
    for key in ("team_id", "user_id", "campaign_id", "medium_id", "source_id", "company_id"):
        val = brief.get(key) or brief.get("default_%s" % key)
        if val:
            defaults[key] = int(val)
    tag_ids = brief.get("tag_ids")
    if tag_ids and isinstance(tag_ids, list):
        defaults["tag_ids"] = tag_ids
    rev = brief.get("expected_revenue_hint")
    if rev:
        defaults["expected_revenue"] = rev
    lead_type = brief.get("lead_type", "lead")
    defaults["lead_type"] = lead_type

    next_steps = (
        "## Next steps\n\n"
        "1. Read the brief below carefully — it describes the targeting criteria.\n"
        "2. Use your knowledge to find REAL companies matching these criteria.\n"
        "3. For each company, call `crm_lead_create` with the lead data.\n"
        "   Pass defaults from `defaults_for_crm_lead_create` (team_id, user_id, tag_ids, etc.).\n"
        "4. The tool handles deduplication automatically — duplicates are skipped.\n"
        "5. Generate exactly %s leads as requested in the brief.\n"
        % brief.get("lead_number", 3)
    )

    return {
        "status": "ok",
        "brief": brief,
        "meta": meta,
        "defaults_for_crm_lead_create": defaults,
        "next_steps": next_steps,
    }


def _format_lead_gen_brief(result):
    status = result.get("status", "")
    if status == "no_brief":
        return result.get("message", "No brief found.")
    if status == "error":
        return "ERROR: %s" % result.get("message", "Unknown error")

    parts = []
    brief = result.get("brief", {})
    llm_text = brief.get("llm_brief_text", "")
    if llm_text:
        parts.append(llm_text)
    else:
        parts.append(json.dumps(brief, indent=2, default=str))

    parts.append("")
    parts.append("--- defaults_for_crm_lead_create ---")
    parts.append(json.dumps(result.get("defaults_for_crm_lead_create", {}), indent=2, default=str))

    meta = result.get("meta", {})
    if meta:
        parts.append("")
        parts.append("--- meta ---")
        parts.append("Saved by: %s at %s" % (meta.get("saved_by", "?"), meta.get("saved_at", "?")))

    parts.append("")
    parts.append(result.get("next_steps", ""))
    return "\n".join(parts)


def crm_lead_create(
    cr, env,
    name=None, partner_name=None, contact_name=None,
    email_from=None, phone=None, function=None,
    description=None, website=None, street=None,
    city=None, country=None, lead_type=None,
    team_id=None, user_id=None, tag_ids=None,
    campaign_id=None, medium_id=None, source_id=None,
    expected_revenue=None, company_id=None,
):
    """Create one CRM lead with deduplication and country resolution."""
    env = _apply_company_context(env, company_id)

    CrmLead = _require_model(env, "crm.lead", "crm_lead_create")

    if lead_type and lead_type not in ("lead", "opportunity"):
        raise ValueError("lead_type must be 'lead' or 'opportunity', got: %s" % lead_type)
    lead_type = lead_type or "lead"

    if not partner_name and not name:
        raise ValueError("At least partner_name or name is required.")

    lead_data_for_fp = {
        "website": website, "partner_name": partner_name, "email_from": email_from,
        "country": country, "city": city, "contact_name": contact_name, "phone": phone,
    }
    fingerprint = _build_lead_fingerprint(lead_data_for_fp)

    if fingerprint:
        existing_fps = _collect_existing_lead_fingerprints(env, lead_type, company_id)
        if fingerprint in existing_fps:
            return {
                "status": "duplicate_skipped",
                "fingerprint": fingerprint,
                "message": "Lead already exists for: %s" % (partner_name or website or email_from or name),
            }

    vals = {
        "type": lead_type,
        "name": name or ("%s — AI Lead" % (partner_name or "New Lead")),
    }
    for field, value in [
        ("partner_name", partner_name), ("contact_name", contact_name),
        ("email_from", email_from), ("phone", phone), ("function", function),
        ("description", description), ("website", website),
        ("street", street), ("city", city),
    ]:
        if value:
            vals[field] = value

    if country:
        Country = env["res.country"]
        match = Country.search([("name", "ilike", country)], limit=1)
        if not match:
            match = Country.search([("code", "=ilike", country)], limit=1)
        if match:
            vals["country_id"] = match.id

    for field, value in [
        ("team_id", team_id), ("user_id", user_id),
        ("campaign_id", campaign_id), ("medium_id", medium_id),
        ("source_id", source_id),
    ]:
        if value is not None:
            vals[field] = int(value)

    if expected_revenue is not None:
        vals["expected_revenue"] = float(expected_revenue)

    if tag_ids is not None:
        if isinstance(tag_ids, str):
            tag_ids = json.loads(tag_ids)
        if isinstance(tag_ids, list) and tag_ids:
            vals["tag_ids"] = [(6, 0, [int(t) for t in tag_ids])]

    if company_id is not None:
        vals["company_id"] = int(company_id)

    lead = CrmLead.create(vals)
    return {
        "status": "created",
        "id": lead.id,
        "display_name": lead.display_name,
        "fingerprint": fingerprint,
    }


def _format_crm_lead_create(result):
    status = result.get("status", "")
    if status == "duplicate_skipped":
        return "DUPLICATE SKIPPED — %s (fingerprint: %s)" % (
            result.get("message", ""), result.get("fingerprint", ""))
    return "CREATED crm.lead id=%s: %s (fingerprint: %s)" % (
        result.get("id", "?"), result.get("display_name", ""), result.get("fingerprint", ""))


def crm_lead_update(cr, env, lead_ids, values, company_id=None):
    """Update one or more CRM leads. Accepts any crm.lead field."""
    env = _apply_company_context(env, company_id)

    CrmLead = _require_model(env, "crm.lead", "crm_lead_update")

    if isinstance(lead_ids, str):
        lead_ids = json.loads(lead_ids)
    if isinstance(lead_ids, int):
        lead_ids = [lead_ids]
    if not lead_ids:
        raise ValueError("lead_ids is required (integer or list of ids)")

    vals = _parse_values(values)
    if not vals:
        raise ValueError("values is required and must not be empty")

    if "country" in vals and "country_id" not in vals:
        country_name = vals.pop("country")
        if country_name:
            Country = env["res.country"]
            match = Country.search([("name", "ilike", country_name)], limit=1)
            if not match:
                match = Country.search([("code", "=ilike", country_name)], limit=1)
            if match:
                vals["country_id"] = match.id

    tag_ids = vals.get("tag_ids")
    if tag_ids is not None:
        if isinstance(tag_ids, str):
            tag_ids = json.loads(tag_ids)
        if isinstance(tag_ids, list) and tag_ids:
            vals["tag_ids"] = [(6, 0, [int(t) for t in tag_ids])]

    records = CrmLead.browse([int(x) for x in lead_ids])
    if not records.exists():
        raise ValueError("No leads found for ids: %s" % lead_ids)
    records.write(vals)
    return {"updated": len(records), "ids": lead_ids}


def _format_crm_lead_update(result):
    return "Updated %s lead(s) ids=%s" % (result.get("updated", 0), result.get("ids", []))


def crm_lead_search(cr, env, domain=None, fields=None, limit=50, order=None, company_id=None):
    """Search CRM leads. Returns id, name, partner_name, email_from, phone, stage, team, user, etc."""
    env = _apply_company_context(env, company_id)

    CrmLead = _require_model(env, "crm.lead", "crm_lead_search")

    domain = _parse_domain(domain)
    if fields is None or fields == "":
        fields = [
            "name", "partner_name", "contact_name", "email_from", "phone",
            "function", "website", "city", "country_id", "stage_id",
            "team_id", "user_id", "type", "expected_revenue", "tag_ids",
            "description",
        ]
    elif isinstance(fields, str):
        fields = json.loads(fields) if fields.strip() else []
    limit = min(int(limit), 500) if limit else 50

    records = CrmLead.search_read(domain, fields or None, limit=limit, order=order or None)
    out = []
    for r in records:
        row = {}
        for k, v in r.items():
            row[k] = _serialize_value(v)
        out.append(row)
    return {"model": "crm.lead", "count": len(out), "records": out}


def _format_crm_lead_search(result):
    lines = ["crm.lead | Records: %s" % result.get("count", 0), ""]
    for r in result.get("records", [])[:50]:
        lines.append("  " + str(r))
    if result.get("count", 0) > 50:
        lines.append("  ... and %s more" % (result["count"] - 50))
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Email campaign (mailing.mailing) tools — ported from rag_mcp_crm_manager
# ═══════════════════════════════════════════════════════════════════════════

MAILING_MODEL = "mailing.mailing"

# Many2many fields that accept plain [id, ...] lists from LLMs and need ORM coercion
MAILING_M2M_FIELDS = frozenset({"contact_list_ids", "tag_ids"})

# Persistent campaign brief model: this module first, then rag_mcp_crm_manager (back-compat)
_CAMPAIGN_BRIEF_MODELS = ("rag_odoo_mcp_server.campaign_brief", "rag_mcp_crm_manager.campaign_brief")


def _format_json(data):
    return json.dumps(data, indent=2, default=str)


def _coerce_m2m(vals, m2m_fields):
    """Convert plain integer lists [1, 2] to ORM many2many format [(6, 0, [1, 2])]."""
    result = dict(vals)
    for fname in m2m_fields:
        v = result.get(fname)
        if isinstance(v, list) and v and all(isinstance(x, int) for x in v):
            result[fname] = [(6, 0, v)]
    return result


def _resolve_campaign_brief_model(env):
    """Return the active campaign-brief recordset model, or None if no model is installed."""
    for name in _CAMPAIGN_BRIEF_MODELS:
        model = env.get(name)
        if model is not None:
            return model
    return None


# Feature-flag for the lead-gen + mailing brief features. Toggled by the
# "CRM Manager" checkbox in Settings → RAG Odoo MCP Server (stored as
# ir.config_parameter and also as group_crm_manager membership for UI hiding).
# When OFF, the controller hides MCP_CRM_MANAGER_TOOLS from tools/list and
# refuses them on tools/call.
MCP_CRM_MANAGER_ENABLED_PARAM = "rag_odoo_mcp_server.crm_manager_enabled"

MCP_CRM_MANAGER_TOOLS = frozenset({
    # Lead-gen + CRM
    "lead_gen_get_brief",
    "crm_lead_create", "crm_lead_update", "crm_lead_search",
    # Mailing brief / discovery / read
    "mailing_help",
    "mailing_get_campaign_brief",
    "mailing_reference",
    "mailing_search", "mailing_get",
    # Mailing write
    "mailing_create", "mailing_update",
    "mailing_for_product",
    "mailing_list_create",
    "mailing_contact_create", "mailing_contact_search",
})

_CRM_MANAGER_HINT = (
    "Enable Settings → RAG Odoo MCP Server → CRM Manager to use the lead-generation "
    "and mailing-campaign brief features."
)


def is_crm_manager_enabled(env):
    """Read the CRM Manager feature-flag from ir.config_parameter."""
    try:
        val = env["ir.config_parameter"].sudo().get_param(MCP_CRM_MANAGER_ENABLED_PARAM)
    except Exception:
        return False
    return str(val or "").strip().lower() in ("true", "1", "yes")


# Feature-flag for the Access Manager tools. Toggled by the "Access Manager"
# checkbox in Settings → RAG Odoo MCP Server. When OFF (default), the controller
# hides MCP_ACCESS_MANAGER_TOOLS from tools/list and refuses them on tools/call,
# so the connected LLM keeps all its normal capabilities but cannot touch access
# rules. When ON, the access-rules tools become available in addition.
MCP_ACCESS_MANAGER_ENABLED_PARAM = "rag_odoo_mcp_server.access_manager_enabled"

_ACCESS_MANAGER_HINT = (
    "Enable Settings → RAG Odoo MCP Server → Access Manager to let the assistant "
    "manage user access rules (hide menus, restrict models/fields, block apps, etc.)."
)


def is_access_manager_enabled(env):
    """Read the Access Manager feature-flag from ir.config_parameter."""
    try:
        val = env["ir.config_parameter"].sudo().get_param(MCP_ACCESS_MANAGER_ENABLED_PARAM)
    except Exception:
        return False
    return str(val or "").strip().lower() in ("true", "1", "yes")


# Feature-flag for the SEO Manager tools. Toggled by the "SEO Manager" checkbox
# in Settings → RAG Odoo MCP Server. When OFF (default), the controller hides
# MCP_SEO_MANAGER_TOOLS from tools/list and refuses them on tools/call. When ON,
# the assistant can audit and improve the Odoo Website's on-site SEO in addition
# to its normal capabilities. The `website` module is NOT a dependency: the tools
# themselves report a readable "install the Website app" message when it is absent.
MCP_SEO_MANAGER_ENABLED_PARAM = "rag_odoo_mcp_server.seo_manager_enabled"

_SEO_MANAGER_HINT = (
    "Enable Settings → RAG Odoo MCP Server → SEO Manager to let the assistant audit and "
    "improve the website's SEO (meta tags, URLs, redirects, robots.txt, sitemap)."
)


def is_seo_manager_enabled(env):
    """Read the SEO Manager feature-flag from ir.config_parameter."""
    try:
        val = env["ir.config_parameter"].sudo().get_param(MCP_SEO_MANAGER_ENABLED_PARAM)
    except Exception:
        return False
    return str(val or "").strip().lower() in ("true", "1", "yes")


def _require_model(env, model_name, feature):
    """Return env[model_name] or raise a clear error if the model is not in the registry."""
    model = env.get(model_name)
    if model is None:
        raise ValueError(
            "%s requires the '%s' model, which is not installed. %s"
            % (feature, model_name, _CRM_MANAGER_HINT)
        )
    return model


def mailing_help(cr, env):
    """Static email campaign guide for the LLM (no DB)."""
    text = """== Email Campaign — RULES (read every time) ==

YOU ARE connected to the Odoo MCP server — email campaigns AND lead generation.
This server manages mailing.mailing records (email campaigns) and CRM lead generation.

## TOOL LIST

### Lead generation & CRM tools
  lead_gen_get_brief  <- CALL FIRST when user asks to generate leads.
                         Returns the brief saved in Odoo (CRM > Leads > 'Claude Lead Brief' button):
                         targeting criteria, industries, countries, buyer persona, defaults.
  crm_lead_create     <- Create one CRM lead with dedup and country resolution.
                         Call once per lead after reading the brief.
  crm_lead_update     <- Update existing leads (stage, salesperson, notes, revenue, etc.).
  crm_lead_search     <- Search/filter existing leads and opportunities.

### Mailing list & contact tools
  mailing_list_create    <- Create a mailing.list (diffusion list).
  mailing_contact_create <- Create a mailing.contact and subscribe to lists.
  mailing_contact_search <- Search existing mailing contacts.

### Email campaign tools
  mailing_get_campaign_brief <- CALL FIRST when user asks to generate a campaign.
                                Returns the brief saved in Odoo (products, tone, audience,
                                custom images, schedule). Contains everything needed to
                                generate one or more campaigns without asking the user.
  mailing_reference   <- company info (name, logo_url, website, email, phone, base_url),
                         mailing lists, recipient model ids, UTM campaigns.
  mailing_search      <- query existing campaigns
  mailing_get         <- read one campaign (including body_arch HTML)
  mailing_create      <- create a new mailing.mailing record
  mailing_update      <- edit subject, body, schedule, state
  mailing_for_product <- look up a product and get campaign generation instructions
                         (already embeds product image + company logo in the HTML skeleton)

## When the user asks to generate campaign(s) — STANDARD WORKFLOW:
  STEP 1 -> mailing_get_campaign_brief
    Reads the saved brief: products list, tone, goal, custom_images URLs, mailing_lists, etc.
    If saved=false: tell user -> Email Marketing -> "Claude brief" button -> fill form -> Save.
  STEP 2 -> For EACH product in brief.products:
    call mailing_for_product(product_id=<id>, extra_instructions=<tone+goal+cta from brief>)
    to get the HTML skeleton, then fill slots using brief product description.
    If brief.custom_images is non-empty, embed them as <img src="url"> in appropriate slots.
  STEP 3 -> mailing_create for each product — use contact_list_ids from brief.
  STEP 4 -> Report all created mailing ids and subjects.
  PROHIBITIONS: NEVER ask user for product details — everything is in the brief.

## When the user asks to create a campaign for a product:
  STEP 1 -> mailing_for_product (product_id OR product_name OR internal ref like "E-COM11", extra_instructions)
    Returns: email_skeleton (HTML with {{SLOT}} placeholders), product_data (incl. description_sale),
             mailing_lists, and next_steps with slot-filling instructions.
  STEP 2 -> Read product_data.description_sale / product_data.description.
    From that text, craft original marketing copy — do NOT paste it verbatim:
      {{HERO_HEADLINE}}  — 6-10 word benefit headline
      {{OPENING_HOOK}}   — 2-3 sentences on customer pain/solution
      {{BENEFIT_1/2/3}}  — 3 key selling points extracted from description
      {{CLOSING_LINE}}   — urgency or guarantee sentence
      {{CTA_LABEL}}      — button text
    Also write a subject (under 60 chars) and preview (under 100 chars).
  STEP 3 -> mailing_create with the filled skeleton as body_arch — DO NOT ask the user for any info.
  STEP 4 -> Report: mailing id, subject, and a brief preview of the copy you wrote.

## body_arch FORMAT — CRITICAL (emails break in the editor if you ignore this)
  The skeleton returned by mailing_for_product already uses the correct format.
  If you build body_arch from scratch (generic campaign), wrap it like this:

  <div class="o_layout oe_unremovable oe_unmovable" data-name="Mailing">
    <div class="container o_mail_wrapper oe_unremovable oe_unmovable" style="border-collapse:collapse;">
      <div class="row">
        <div class="col o_mail_no_options o_mail_wrapper_td bg-white oe_structure o_editable" style="text-align:left;width:100%;">
          <!-- blocks go here -->
        </div>
      </div>
    </div>
  </div>

  Each block MUST be a <div> with data-snippet and o_mail_snippet_general class:
    <div class="s_text_block o_mail_snippet_general pt24 pb24" data-snippet="s_text_block" data-name="Text">
      <div class="container s_allow_columns"> <p>Your text</p> </div>
    </div>

  Available snippet types: s_title, s_text_block, s_picture, s_image_text,
    s_text_image, s_call_to_action, s_cover, s_three_columns, s_hr.
  Buttons: <a href="..." role="button" class="btn btn-primary">Label</a>
  Images: <img src="..." class="img-fluid" alt="..."/>
  Unsubscribe link: <a href="/unsubscribe_from_list">Unsubscribe</a>
  NEVER use raw <table> elements — Odoo converts divs to tables on send.
"""
    return text


def mailing_get_campaign_brief(cr, env, company_id=None):
    """Return the campaign brief saved from the Odoo UI."""
    env = _apply_company_context(env, company_id)

    Brief = _resolve_campaign_brief_model(env)
    if Brief is None:
        return {
            "saved": False,
            "message": "Campaign brief model not found. " + _CRM_MANAGER_HINT,
        }
    active_brief = Brief.search([("active", "=", True)], limit=1)
    if not active_brief:
        return {
            "saved": False,
            "message": (
                "No active campaign brief found. In Odoo go to "
                "Email Marketing -> Configuration -> Claude Briefs and activate one, "
                "or create a new one via Email Marketing -> Mailings -> 'Claude brief' button."
            ),
        }
    active_brief._compute_brief_json()
    try:
        brief = json.loads(active_brief.brief_json or "{}")
    except json.JSONDecodeError:
        return {"saved": False, "parse_error": True}

    products = brief.get("products") or []
    goal = brief.get("campaign_goal") or "conversion"
    tone = brief.get("campaign_tone") or "professional"
    cta = brief.get("cta_text") or ""
    custom_images = brief.get("custom_images") or []
    schedule_type = brief.get("schedule_type") or "now"
    schedule_date = brief.get("schedule_date") or ""
    extra_instructions = brief.get("extra_instructions") or ""
    target_audience = brief.get("target_audience") or ""
    list_ids = brief.get("contact_list_ids") or []
    list_hint = str(list_ids[0]) if list_ids else "null"

    product_count = len(products)
    product_names = ", ".join(p["name"] for p in products) if products else "(none)"
    image_hint = (
        "  - " + "\n  - ".join(
            "%s -> %s" % (img.get("description") or img.get("filename") or "image", img["url"])
            for img in custom_images
        )
        if custom_images else "  (none)"
    )

    next_steps = (
        "=== CAMPAIGN BRIEF LOADED — GENERATE NOW, NO USER INPUT NEEDED ===\n"
        "\n"
        "Brief: '{title}' | Goal: {goal} | Tone: {tone}\n"
        "Products: {product_names}\n"
        "Target: {target_audience}\n"
        "\n"
        "## CUSTOM IMAGES (embed these in the campaign HTML where relevant)\n"
        "{image_hint}\n"
        "\n"
        "## FOR EACH PRODUCT, DO THE FOLLOWING:\n"
        "\n"
        "STEP A -> call mailing_for_product with:\n"
        '  product_id = <id from brief.products>\n'
        '  extra_instructions = "Goal: {goal}. Tone: {tone}. CTA: {cta}. {extra_instructions}"\n'
        "\n"
        "STEP B -> Fill ALL {{SLOT}} placeholders in the returned email_skeleton.\n"
        "\n"
        "STEP C -> call mailing_create with the completed HTML:\n"
        "  subject     : crafted subject (<60 chars, {tone} tone)\n"
        "  preview     : crafted preview (<100 chars)\n"
        "  body_arch   : filled skeleton — ZERO {{SLOT}} placeholders remaining\n"
        "  mailing_model_id : 'mailing.list'\n"
        "  contact_list_ids : [{list_hint}]\n"
        "  schedule_type    : '{schedule_type}'\n"
        + ("  schedule_date    : '{schedule_date}'\n" if schedule_date else "") +
        "\n"
        "Repeat STEP A-C for all {product_count} product(s).\n"
    ).format(
        title=brief.get("brief_title") or "",
        goal=goal,
        tone=tone,
        cta=cta or "(not specified)",
        product_names=product_names,
        product_count=product_count,
        target_audience=target_audience or "(not specified)",
        image_hint=image_hint,
        extra_instructions=extra_instructions,
        list_hint=list_hint,
        schedule_type=schedule_type,
        schedule_date=schedule_date,
    )

    return {"saved": True, "brief": brief, "next_steps": next_steps}


def mailing_reference(cr, env, company_id=None):
    """Return reference data needed to create mailing.mailing records."""
    env = _apply_company_context(env, company_id)
    out = {}

    icp = env["ir.config_parameter"].sudo()
    base_url = (icp.get_param("web.base.url") or "").rstrip("/")
    company = env.company
    out["company"] = {
        "id": company.id,
        "name": company.name or "",
        "logo_url": "%s/web/image/res.company/%d/logo" % (base_url, company.id),
        "website": company.website or "",
        "email": company.email or "",
        "phone": company.phone or "",
        "street": company.street or "",
        "city": company.city or "",
        "country": company.country_id.name if company.country_id else "",
        "base_url": base_url,
        "note": (
            "Use logo_url in <img> tags and company details in email footers. "
            "Product images: %s/web/image/product.template/{id}/image_1920" % base_url
        ),
    }

    MailingList = _require_model(env, "mailing.list", "mailing_reference")
    lists = MailingList.search_read([], ["name", "contact_count"], order="name", limit=100)
    out["mailing_lists"] = lists

    models = env["ir.model"].search_read(
        [("is_mailing_enabled", "=", True)],
        ["name", "model"],
        order="name",
        limit=100,
    )
    out["mailing_models"] = models

    UtmCampaign = _require_model(env, "utm.campaign", "mailing_reference")
    campaigns = UtmCampaign.search_read([], ["name"], order="name", limit=100)
    out["utm_campaigns"] = campaigns

    return out


def mailing_search(cr, env, domain=None, limit=40, company_id=None):
    """Search mailing.mailing records (email campaigns)."""
    env = _apply_company_context(env, company_id)
    Mailing = _require_model(env, MAILING_MODEL, "mailing_search")
    domain = _parse_domain(domain)
    limit = min(int(limit or 40), 200)
    fields = [
        "id", "subject", "preview", "state", "email_from", "schedule_type",
        "schedule_date", "sent_date", "mailing_model_name", "campaign_id",
        "user_id", "contact_list_ids", "sent", "opened", "total",
    ]
    rows = Mailing.search_read(domain, fields, limit=limit, order="id desc")
    for r in rows:
        for k, v in list(r.items()):
            r[k] = _serialize_value(v)
    return {"model": MAILING_MODEL, "count": len(rows), "records": rows}


def mailing_get(cr, env, mailing_id, company_id=None):
    """Read one mailing.mailing by id."""
    env = _apply_company_context(env, company_id)
    Mailing = _require_model(env, MAILING_MODEL, "mailing_get")
    mid = int(mailing_id)
    fields = [
        "id", "subject", "preview", "state", "email_from", "body_arch",
        "schedule_type", "schedule_date", "sent_date", "mailing_model_id",
        "mailing_model_name", "mailing_domain", "campaign_id", "user_id",
        "contact_list_ids", "reply_to_mode", "reply_to",
        "sent", "delivered", "opened", "total",
    ]
    rows = Mailing.search_read([("id", "=", mid)], fields, limit=1)
    if not rows:
        raise ValueError("mailing.mailing id=%s not found." % mid)
    r = rows[0]
    for k, v in list(r.items()):
        r[k] = _serialize_value(v)
    return r


def _ensure_mailing_layout(html):
    """Wrap bare HTML in the ``o_layout`` structure required by the mass_mailing editor."""
    if not html:
        return html
    if "o_layout" in html:
        if 'id="design-element"' not in html:
            idx = html.find('>', html.find('o_layout'))
            if idx != -1:
                html = html[:idx+1] + '\n  <style id="design-element"></style>' + html[idx+1:]
        if "oe_structure" in html and "o_editable" not in html:
            html = html.replace("oe_structure", "oe_structure o_editable", 1)
        return html
    if "o_mail_snippet_general" not in html:
        html = (
            '<div class="s_text_block o_mail_snippet_general pt24 pb24"'
            ' data-snippet="s_text_block" data-name="Text"'
            ' style="padding-left:15px;padding-right:15px;">\n'
            '  <div class="container s_allow_columns">\n'
            + html
            + '\n  </div>\n'
            '</div>\n'
        )
    return (
        '<div class="o_layout oe_unremovable oe_unmovable" data-name="Mailing">\n'
        '  <style id="design-element"></style>\n'
        '  <div class="container o_mail_wrapper o_mail_regular oe_unremovable"'
        ' style="border-collapse:collapse;">\n'
        '    <div class="row">\n'
        '      <div class="col o_mail_no_options o_mail_wrapper_td bg-white'
        ' oe_structure o_editable" style="text-align:left;width:100%;">\n'
        + html
        + '\n      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>'
    )


def mailing_create(cr, env, values, company_id=None):
    """Create a mailing.mailing (email campaign) record."""
    env = _apply_company_context(env, company_id)
    Mailing = _require_model(env, MAILING_MODEL, "mailing_create")
    vals = _coerce_m2m(_parse_values(values), MAILING_M2M_FIELDS)

    if not vals.get("subject"):
        raise ValueError("values must include 'subject' for the mailing subject line.")

    if vals.get("body_arch"):
        vals["body_arch"] = _ensure_mailing_layout(vals["body_arch"])

    model_id_val = vals.get("mailing_model_id")
    if isinstance(model_id_val, str):
        ir_model = env["ir.model"].search([("model", "=", model_id_val)], limit=1)
        if not ir_model:
            raise ValueError(
                "No ir.model found for model name '%s'. Use mailing_reference to get valid ids." % model_id_val
            )
        vals["mailing_model_id"] = ir_model.id
    elif not model_id_val:
        ir_model = env["ir.model"].search([("model", "=", "mailing.list")], limit=1)
        if ir_model:
            vals["mailing_model_id"] = ir_model.id

    rec = Mailing.create(vals)
    return {"id": rec.id, "subject": rec.subject, "state": rec.state}


def mailing_update(cr, env, mailing_ids, values, company_id=None):
    """Update one or more mailing.mailing records."""
    env = _apply_company_context(env, company_id)
    Mailing = _require_model(env, MAILING_MODEL, "mailing_update")
    ids = _parse_ids(mailing_ids)
    if not ids:
        raise ValueError("mailing_ids required")
    vals = _coerce_m2m(_parse_values(values), MAILING_M2M_FIELDS)
    if not vals:
        raise ValueError("values required")

    if vals.get("body_arch"):
        vals["body_arch"] = _ensure_mailing_layout(vals["body_arch"])

    model_id_val = vals.get("mailing_model_id")
    if isinstance(model_id_val, str):
        ir_model = env["ir.model"].search([("model", "=", model_id_val)], limit=1)
        if not ir_model:
            raise ValueError("No ir.model found for model name '%s'." % model_id_val)
        vals["mailing_model_id"] = ir_model.id

    recs = Mailing.browse(ids)
    recs.write(vals)
    return {"updated": len(recs), "ids": ids}


def _image_to_public_url(env, image_data, name_suffix, base_url, res_id=0):
    """Convert an Odoo binary field value to a publicly-accessible attachment URL."""
    if not image_data:
        return ""
    b64 = image_data if isinstance(image_data, str) else image_data.decode()
    IrAttachment = env["ir.attachment"]
    attach = IrAttachment.create({
        "name": "mailing_img_%s" % name_suffix,
        "datas": b64,
        "type": "binary",
        "public": True,
        "res_model": "mailing.mailing",
        "res_id": res_id,
    })
    attach.generate_access_token()
    return "%s/web/image/%s?access_token=%s" % (
        (base_url or "").rstrip("/"), attach.id, attach.access_token,
    )


def _build_product_email_skeleton(tmpl, base_url="", company=None):
    """Build an HTML email skeleton with {{SLOT}} placeholders using the mass_mailing snippet structure."""
    name = tmpl.name or ""
    currency = tmpl.currency_id.name if tmpl.currency_id else ""
    price = tmpl.list_price
    price_str_val = ("%s %.2f" % (currency, price)) if price else ""
    default_code = getattr(tmpl, "default_code", "") or ""
    categ = tmpl.categ_id.name if tmpl.categ_id else ""
    base = (base_url or "").rstrip("/")

    meta_parts = []
    if default_code:
        meta_parts.append("Ref: %s" % default_code)
    if categ:
        meta_parts.append(categ)
    meta_line = (" — " + " · ".join(meta_parts)) if meta_parts else ""

    product_img_url = _image_to_public_url(tmpl.env, tmpl.image_1920, "product_%d" % tmpl.id, base, tmpl.id)
    if not product_img_url:
        product_img_url = "%s/web/image/product.template/%d/image_1920/600x400" % (base, tmpl.id)

    company_name = (company.name if company else "") or ""
    if company and company.logo:
        company_logo_url = _image_to_public_url(company.env, company.logo, "logo_%d" % company.id, base, company.id)
    else:
        company_logo_url = ""
    if not company_logo_url and company:
        company_logo_url = "%s/web/image/res.company/%d/logo/160x60" % (base, company.id)
    company_website = (company.website if company else "") or "#"
    company_email = (company.email if company else "") or ""
    company_phone = (company.phone if company else "") or ""

    logo_img = ""
    if company_logo_url:
        logo_img = (
            '<img src="%s" alt="%s" style="height:auto;max-width:160px;" class="img-fluid"/>'
            '<br/>'
        ) % (company_logo_url, company_name)

    variant_block = ""
    variants = tmpl.product_variant_ids
    if len(variants) > 1:
        items = "".join(
            '<li>%s%s</li>' % (
                v.display_name,
                (' <small style="color:#888;">(%s)</small>' % v.default_code) if v.default_code else "",
            )
            for v in variants[:6]
        )
        variant_block = (
            '<p style="font-weight:bold;color:#555;">Available options:</p>'
            '<ul>%s</ul>' % items
        )

    price_block = ""
    if price_str_val:
        price_block = (
            '<div style="background:#f0f4ff;border-left:4px solid #2c3e8c;'
            'padding:14px 20px;margin:24px 0;border-radius:0 6px 6px 0;">'
            '<span style="font-size:13px;color:#555;display:block;margin-bottom:2px;">Price</span>'
            '<span style="font-size:24px;font-weight:bold;color:#2c3e8c;">%s</span>'
            '</div>' % price_str_val
        )

    footer_parts = []
    if company_website and company_website != "#":
        footer_parts.append('<a href="%s" style="color:#888888;">%s</a>' % (company_website, company_website))
    if company_email:
        footer_parts.append('<a href="mailto:%s" style="color:#888888;">%s</a>' % (company_email, company_email))
    if company_phone:
        footer_parts.append(company_phone)
    footer_contact = " · ".join(footer_parts)

    skeleton = (
        '<div class="o_layout oe_unremovable oe_unmovable" data-name="Mailing">\n'
        '  <style id="design-element"></style>\n'
        '  <div class="container o_mail_wrapper o_mail_regular oe_unremovable" style="border-collapse:collapse;">\n'
        '    <div class="row">\n'
        '      <div class="col o_mail_no_options o_mail_wrapper_td bg-white oe_structure o_editable"'
        ' style="text-align:left;width:100%%;">\n'
        '\n'
        '        <div class="s_cover o_mail_snippet_general" data-snippet="s_cover" data-name="Cover">\n'
        '          <div class="container">\n'
        '            <div class="row">\n'
        '              <div class="col-lg-12 pt48 pb32" style="background-color:#2c3e8c;text-align:center;">\n'
        '                %(logo_img)s\n'
        '                <h1 style="color:#ffffff;font-size:26px;">{{HERO_HEADLINE}}</h1>\n'
        '                <p style="color:#b8c8f0;font-size:13px;">%(name)s%(meta_line)s</p>\n'
        '              </div>\n'
        '            </div>\n'
        '          </div>\n'
        '        </div>\n'
        '\n'
        '        <div class="s_picture o_mail_snippet_general pt0 pb0" data-snippet="s_picture" data-name="Picture">\n'
        '          <div class="container s_allow_columns" style="text-align:center;">\n'
        '            <img src="%(product_img_url)s" alt="%(name)s"'
        ' class="img-fluid mx-auto d-block" style="width:100%%;max-width:600px;" width="600"/>\n'
        '          </div>\n'
        '        </div>\n'
        '\n'
        '        <div class="s_text_block o_mail_snippet_general pt32 pb24"'
        ' data-snippet="s_text_block" data-name="Text"'
        ' style="padding-left:15px;padding-right:15px;">\n'
        '          <div class="container s_allow_columns">\n'
        '            <p style="font-size:16px;line-height:1.8;">{{OPENING_HOOK}}</p>\n'
        '            <p><span style="color:#2c3e8c;font-weight:bold;">&#10003;</span> {{BENEFIT_1}}</p>\n'
        '            <p><span style="color:#2c3e8c;font-weight:bold;">&#10003;</span> {{BENEFIT_2}}</p>\n'
        '            <p><span style="color:#2c3e8c;font-weight:bold;">&#10003;</span> {{BENEFIT_3}}</p>\n'
        '            %(variant_block)s\n'
        '            %(price_block)s\n'
        '            <p style="font-style:italic;color:#555555;">{{CLOSING_LINE}}</p>\n'
        '          </div>\n'
        '        </div>\n'
        '\n'
        '        <div class="s_call_to_action o_mail_snippet_general o_cc o_cc3 pt24 pb32"'
        ' data-snippet="s_call_to_action" data-name="Call to Action">\n'
        '          <div class="container">\n'
        '            <div class="row">\n'
        '              <div class="col-lg-12" style="text-align:center;">\n'
        '                <a href="%(website)s" role="button" class="btn btn-primary btn-lg">'
        '{{CTA_LABEL}}</a>\n'
        '              </div>\n'
        '            </div>\n'
        '          </div>\n'
        '        </div>\n'
        '\n'
        '        <div class="s_text_block o_mail_snippet_general bg-200 pt16 pb16"'
        ' data-snippet="s_text_block" data-name="Footer">\n'
        '          <div class="container s_allow_columns" style="text-align:center;">\n'
        + (
            '            <p style="font-size:13px;color:#555555;font-weight:bold;">%(company_name)s</p>\n'
            if company_name else ''
        )
        + (
            '            <p style="font-size:11px;color:#888888;">%(footer_contact)s</p>\n'
            if footer_contact else ''
        ) +
        '            <p style="font-size:11px;color:#aaaaaa;">\n'
        '              You receive this because you subscribed to our newsletter.\n'
        '              <a href="/unsubscribe_from_list" style="color:#aaaaaa;">Unsubscribe</a>\n'
        '            </p>\n'
        '          </div>\n'
        '        </div>\n'
        '\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>'
    ) % {
        "logo_img": logo_img,
        "name": name,
        "meta_line": meta_line,
        "product_img_url": product_img_url,
        "variant_block": variant_block,
        "price_block": price_block,
        "website": company_website,
        "company_name": company_name,
        "footer_contact": footer_contact,
    }

    return skeleton


def mailing_for_product(cr, env, product_id=None, product_name=None, extra_instructions=None, company_id=None):
    """Look up a product and return a ready-to-fill HTML email skeleton."""
    env = _apply_company_context(env, company_id)

    ProductTemplate = _require_model(env, "product.template", "mailing_for_product")
    ProductProduct = _require_model(env, "product.product", "mailing_for_product")
    MailingList = _require_model(env, "mailing.list", "mailing_for_product")

    tmpl = None

    if product_id:
        tmpl = ProductTemplate.browse(int(product_id))
        if not tmpl.exists():
            tmpl = None

    if not tmpl and product_name:
        query = (product_name or "").strip()
        tmpl = ProductTemplate.search([("name", "ilike", query)], limit=1)
        if not tmpl:
            tmpl = ProductTemplate.search([("default_code", "ilike", query)], limit=1)
        if not tmpl:
            variant = ProductProduct.search([("default_code", "ilike", query)], limit=1)
            if variant:
                tmpl = variant.product_tmpl_id
        if not tmpl:
            tmpl = ProductTemplate.search(
                ["|", ("name", "ilike", query), ("description_sale", "ilike", query)], limit=1
            )

    if not tmpl:
        available = ProductTemplate.search_read(
            [], ["id", "name", "default_code", "list_price"], limit=30, order="name"
        )
        return {
            "error": "Product not found for '%s'. Pick an id from available_products and retry." % product_name,
            "available_products": available,
        }

    default_code = getattr(tmpl, "default_code", "") or ""
    variants = tmpl.product_variant_ids
    variant_refs = [v.default_code for v in variants if v.default_code]
    desc_sale = (tmpl.description_sale or "").strip()
    desc = (tmpl.description or "").strip()
    price = tmpl.list_price
    currency = tmpl.currency_id.name if tmpl.currency_id else ""
    price_str = ("%s %.2f" % (currency, price)) if price else ""

    product_data = {
        "id": tmpl.id,
        "name": tmpl.name,
        "default_code": default_code,
        "variant_refs": variant_refs,
        "description_sale": desc_sale,
        "description": desc,
        "list_price": price,
        "price_formatted": price_str,
        "currency": currency,
        "categ": tmpl.categ_id.name if tmpl.categ_id else "",
        "type": tmpl.type,
        "tags": [t.name for t in getattr(tmpl, "tag_ids", [])],
        "variants_count": len(variants),
    }

    icp = env["ir.config_parameter"].sudo()
    base_url = (icp.get_param("web.base.url") or "").rstrip("/")
    company = env.company

    company_data = {
        "id": company.id,
        "name": company.name or "",
        "logo_url": "%s/web/image/res.company/%d/logo/160x60" % (base_url, company.id),
        "website": company.website or "",
        "email": company.email or "",
        "phone": company.phone or "",
    }
    product_data["image_url"] = "%s/web/image/product.template/%d/image_1920/600x400" % (base_url, tmpl.id)

    email_skeleton = _build_product_email_skeleton(tmpl, base_url=base_url, company=company)

    mailing_lists = MailingList.search_read(
        [], ["id", "name", "contact_count"], order="name", limit=20
    )
    list_hint = str(mailing_lists[0]["id"]) if mailing_lists else "null"

    copy_source = desc_sale or desc or ("A quality product from %s." % (tmpl.categ_id.name or "our catalog"))
    extra_line = ("User instructions: %s\n" % extra_instructions) if extra_instructions else ""

    next_steps = (
        "=== BUILD EMAIL CAMPAIGN — EXECUTE NOW, NO USER INPUT NEEDED ===\n"
        "\n"
        "Product found: '{name}' (ref: {ref}) | Company: {company_name}\n"
        "\n"
        "## PRODUCT COPY SOURCE — read this to craft the email text\n"
        "---\n"
        "{copy_source}\n"
        "---\n"
        "{extra_line}"
        "\n"
        "## HOW TO FILL EACH {{SLOT}}\n"
        "{{HERO_HEADLINE}}  — punchy 6-10 word benefit headline.\n"
        "{{OPENING_HOOK}}   — 2-3 sentences framing pain/aspiration then product as solution.\n"
        "{{BENEFIT_1}}      — 1st key selling point.\n"
        "{{BENEFIT_2}}      — 2nd selling point — different angle.\n"
        "{{BENEFIT_3}}      — 3rd selling point or unique differentiator.\n"
        "{{CLOSING_LINE}}   — 1 sentence: urgency, guarantee, or free shipping.\n"
        "{{CTA_LABEL}}      — Button label, e.g. 'Shop Now', 'Get Yours'.\n"
        "\n"
        "## CALL mailing_create WITH\n"
        "{{\n"
        '  "subject": "<your crafted subject>",\n'
        '  "preview": "<your crafted preview>",\n'
        '  "body_arch": "<email_skeleton with every {{SLOT}} replaced>",\n'
        '  "mailing_model_id": "mailing.list",\n'
        '  "contact_list_ids": [{list_hint}],\n'
        '  "schedule_type": "now"\n'
        "}}\n"
    ).format(
        name=tmpl.name,
        ref=default_code or str(tmpl.id),
        company_name=company.name or "",
        copy_source=copy_source,
        extra_line=extra_line,
        list_hint=list_hint,
    )

    return {
        "product_data": product_data,
        "company_data": company_data,
        "email_skeleton": email_skeleton,
        "mailing_lists": mailing_lists,
        "next_steps": next_steps,
    }


def mailing_list_create(cr, env, name, is_public=False, company_id=None):
    """Create a mailing.list (diffusion list)."""
    env = _apply_company_context(env, company_id)
    MailList = _require_model(env, "mailing.list", "mailing_list_create")
    if not name:
        raise ValueError("name is required")
    vals = {"name": name}
    if is_public:
        vals["is_public"] = True
    rec = MailList.create(vals)
    return {"id": rec.id, "name": rec.name}


def mailing_contact_create(cr, env, email, list_ids=None, name=None,
                           first_name=None, last_name=None, company_name=None,
                           country=None, title_id=None, tag_ids=None,
                           company_id=None):
    """Create a mailing.contact and subscribe it to mailing lists."""
    env = _apply_company_context(env, company_id)
    Contact = _require_model(env, "mailing.contact", "mailing_contact_create")
    if not email:
        raise ValueError("email is required")

    vals = {"email": email}
    if name:
        vals["name"] = name
    if first_name:
        vals["first_name"] = first_name
    if last_name:
        vals["last_name"] = last_name
    if company_name:
        vals["company_name"] = company_name
    if title_id is not None:
        vals["title_id"] = int(title_id)

    if country:
        Country = env["res.country"]
        match = Country.search([("name", "ilike", country)], limit=1)
        if not match:
            match = Country.search([("code", "=ilike", country)], limit=1)
        if match:
            vals["country_id"] = match.id

    if list_ids is not None:
        if isinstance(list_ids, str):
            list_ids = json.loads(list_ids)
        if isinstance(list_ids, list) and list_ids:
            vals["list_ids"] = [(6, 0, [int(x) for x in list_ids])]

    if tag_ids is not None:
        if isinstance(tag_ids, str):
            tag_ids = json.loads(tag_ids)
        if isinstance(tag_ids, list) and tag_ids:
            vals["tag_ids"] = [(6, 0, [int(t) for t in tag_ids])]

    rec = Contact.create(vals)
    return {
        "id": rec.id,
        "name": rec.name,
        "email": rec.email,
        "list_ids": rec.list_ids.ids,
    }


def mailing_contact_search(cr, env, domain=None, limit=100, company_id=None):
    """Search mailing contacts."""
    env = _apply_company_context(env, company_id)
    Contact = _require_model(env, "mailing.contact", "mailing_contact_search")
    domain = _parse_domain(domain)
    limit = min(int(limit), 500) if limit else 100
    records = Contact.search_read(
        domain,
        ["name", "email", "company_name", "country_id", "list_ids", "tag_ids"],
        limit=limit,
    )
    out = []
    for r in records:
        row = {}
        for k, v in r.items():
            row[k] = _serialize_value(v)
        out.append(row)
    return {"model": "mailing.contact", "count": len(out), "records": out}


def _format_help(r):
    return r if isinstance(r, str) else str(r)


def _format_mailing_list_create(result):
    return "Created mailing.list id=%s name='%s'" % (result.get("id"), result.get("name"))


def _format_mailing_contact_create(result):
    return "Created mailing.contact id=%s name='%s' email='%s' lists=%s" % (
        result.get("id"), result.get("name"), result.get("email"), result.get("list_ids"))


def _format_mailing_contact_search(result):
    lines = ["mailing.contact | Records: %s" % result.get("count", 0), ""]
    for r in result.get("records", [])[:50]:
        lines.append("  " + str(r))
    if result.get("count", 0) > 50:
        lines.append("  ... and %s more" % (result["count"] - 50))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {"name": "list_tables", "description": "List all tables in the PostgreSQL schema (default: public). Returns table names and approximate size. Use this to discover Odoo tables.", "inputSchema": {"type": "object", "properties": {"schema": {"type": "string", "default": "public", "description": "Schema name (default: public)"}}}},
    {"name": "describe_table", "description": "Get column definitions for a table: column name, data type, nullable, default. Use after list_tables to inspect a specific table.", "inputSchema": {"type": "object", "properties": {"table_name": {"type": "string", "description": "Table name (e.g. res_partner, sale_order)"}, "schema": {"type": "string", "default": "public"}}, "required": ["table_name"]}},
    {"name": "get_table_row_count", "description": "Get the exact row count for a table. Useful to know table size before querying.", "inputSchema": {"type": "object", "properties": {"table_name": {"type": "string"}, "schema": {"type": "string", "default": "public"}}, "required": ["table_name"]}},
    {"name": "run_readonly_query", "description": "Run a read-only SQL query (SELECT only) against the Odoo PostgreSQL database. Use describe_table and list_tables first to build correct queries. Returns up to max_rows rows.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "Single SELECT SQL statement"}, "max_rows": {"type": "integer", "default": 500, "maximum": 2000}}, "required": ["query"]}},
    {"name": "get_odoo_models_info", "description": "List Odoo ORM models from ir_model (model name, description). Helps map Odoo models to database tables (e.g. res.partner -> res_partner).", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_table_schema_pg", "description": "Get full table schema: columns and indexes. Use for detailed inspection of a table.", "inputSchema": {"type": "object", "properties": {"table_name": {"type": "string"}, "schema": {"type": "string", "default": "public"}}, "required": ["table_name"]}},
    # Data retrieval (ORM)
    {"name": "odoo_search_read", "description": "Search and read records from an Odoo model using domain and optional fields. Use for: 'customers from Spain' (res.partner, country_id.code=ES), 'products with stock below 10', 'today's sales orders over 1000', 'unpaid invoices'. Domain: list of [field, operator, value], e.g. [[\"country_id.code\", \"=\", \"ES\"]]. Fields: list of field names or empty for all.", "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "description": "Odoo model technical name (e.g. res.partner, product.product, sale.order, account.move)"}, "domain": {"type": "string", "description": "JSON array of conditions, e.g. [[\"country_id.code\", \"=\", \"ES\"]] or [] for all"}, "fields": {"type": "string", "description": "JSON array of field names to return, e.g. [\"name\", \"email\"] or leave empty for all"}, "limit": {"type": "integer", "default": 100, "description": "Max records to return (cap 500)"}, "order": {"type": "string", "description": "Sort order, e.g. \"name asc\", \"date_order desc\""}}, "required": ["model"]}},
    # Data management (write) — create, edit, delete sale orders, purchase orders, invoices
    {"name": "odoo_create", "description": "Create one record in an Odoo model. Persists to DB. Use for: Sale orders (sale.order, required: partner_id; optional: order_line), Purchase orders (purchase.order), Invoices (account.move), Customers (res.partner), Products (product.template or product.product). Workflow: Prefer creating the sale order first with order_line using existing product IDs (from product.product); only create missing products when needed. Do not create many products one-by-one before creating the sale order — create the sale order with existing products, or create few products then the order. product.template: type field must be a valid selection value. Odoo 18 often uses 'consu' (consumable/goods) and 'service'; 'product' (storable) may not exist in all DBs. If you get 'Wrong value for product.template.type', run odoo_search_read(model='product.template', fields=['type'], limit=5) and use one of the type values returned (e.g. consu, service). order_line tax_id: set tax_id: [[6,0,[tax_ids]]] for taxed lines, tax_id: false for no tax; use odoo_search_read(account.tax) to find tax IDs.", "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "description": "Odoo model: sale.order, purchase.order, account.move, res.partner, product.template, product.product, etc."}, "values": {"type": "string", "description": "JSON object of fields. For product.template use type: 'consu' or 'service' (check existing products if error). For order_line include tax_id."}}, "required": ["model", "values"]}},
    {"name": "odoo_write", "description": "Update existing record(s). Persists to DB. Use for: Edit sale order (sale.order), purchase order (purchase.order), invoice (account.move), customer (res.partner), or order lines (sale.order.line, purchase.order.line, account.move.line). ids: single id or JSON array; values: JSON object of field: value. For order/invoice lines: always set tax_id explicitly — tax_id: [[6, 0, [tax_ids]]] for lines with taxes, tax_id: false for lines without taxes. Use get_odoo_models_info or odoo_search_read(account.tax) to find tax IDs.", "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "description": "Odoo model (e.g. sale.order, purchase.order, account.move, res.partner, sale.order.line, account.move.line)"}, "ids": {"type": "string", "description": "Record id(s): integer or JSON array, e.g. 42 or [1,2,3]"}, "values": {"type": "string", "description": "JSON object of field: value. For lines include tax_id when changing taxes."}}, "required": ["model", "ids", "values"]}},
    {"name": "odoo_unlink", "description": "Delete record(s) from an Odoo model. Persists to DB. Use for: Delete/cancel sale order (sale.order), purchase order (purchase.order), invoice (account.move), or any record. ids: single id or JSON array. Prefer cancelling orders/invoices via odoo_execute (action_cancel) when applicable.", "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "description": "Odoo model (e.g. sale.order, purchase.order, account.move)"}, "ids": {"type": "string", "description": "Record id(s): integer or JSON array"}}, "required": ["model", "ids"]}},
    {"name": "odoo_execute", "description": "Call a method on record(s). Persists to DB. Use for: Confirm sale order (model=sale.order, method_name=action_confirm), confirm purchase (purchase.order, action_confirm), confirm/send invoice (account.move, action_post), cancel (action_cancel), create invoice from sale (sale.order, action_create_invoice). method_name: action_confirm, action_cancel, action_post, action_create_invoice, etc.", "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "description": "Odoo model (e.g. sale.order, purchase.order, account.move)"}, "ids": {"type": "string", "description": "Record id(s): integer or JSON array"}, "method_name": {"type": "string", "description": "Method: action_confirm, action_cancel, action_post, action_create_invoice"}, "args": {"type": "string", "description": "Optional JSON array of positional arguments"}, "kwargs": {"type": "string", "description": "Optional JSON object of keyword arguments"}}, "required": ["model", "ids", "method_name"]}},
    # Claude Dashboards
    {"name": "dashboard_list", "description": "List Claude Dashboards visible to the user. Use this before dashboard_get to find an id.", "inputSchema": {"type": "object", "properties": {"mine_only": {"type": "boolean", "default": False, "description": "Only show dashboards owned by the current user"}, "company_id": {"type": "integer", "description": "Optional company filter"}}}},
    {"name": "dashboard_get", "description": "Read one dashboard with all its widgets. Returns the JSON spec used by the OWL renderer.", "inputSchema": {"type": "object", "properties": {"dashboard_id": {"type": "integer"}, "company_id": {"type": "integer"}}, "required": ["dashboard_id"]}},
    {"name": "dashboard_get_schema_help", "description": "Return numeric, groupable, and date fields for an Odoo model. Use this BEFORE dashboard_create or dashboard_add_widget to pick valid measure_field / group_by / list_fields. Date fields support :day :week :month :quarter :year (e.g. date_order:month).", "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "description": "Odoo model technical name, e.g. sale.order, account.move, res.partner"}, "company_id": {"type": "integer"}}, "required": ["model"]}},
    {"name": "dashboard_create", "description": "Create a new Claude Dashboard with one or more widgets in a single call. Each widget has: title, widget_type (kpi|bar|line|pie|donut|table|pivot), model, optional domain (JSON list), measure_field, measure_aggregator (count|sum|avg|min|max), group_by (list of field names; date fields support :month etc), list_fields (for table/pivot), record_limit, and layout {x,y,w,h} on a 12-col grid. Use dashboard_get_schema_help first to find valid fields. Marks the dashboard as created_by_claude=True.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "is_shared": {"type": "boolean", "default": False}, "company_id": {"type": "integer"}, "widgets": {"type": "string", "description": "JSON array of widget specs. Each spec: {title, widget_type, model, domain (optional JSON list), measure_field, measure_aggregator, group_by (list), list_fields (list), record_limit, layout: {x,y,w,h}, options}"}}, "required": ["name", "widgets"]}},
    {"name": "dashboard_update", "description": "Update header fields of a dashboard (name, description, is_shared). Pass only the fields you want to change.", "inputSchema": {"type": "object", "properties": {"dashboard_id": {"type": "integer"}, "name": {"type": "string"}, "description": {"type": "string"}, "is_shared": {"type": "boolean"}}, "required": ["dashboard_id"]}},
    {"name": "dashboard_add_widget", "description": "Append one widget to an existing dashboard. The widget object has the same shape as in dashboard_create.", "inputSchema": {"type": "object", "properties": {"dashboard_id": {"type": "integer"}, "company_id": {"type": "integer"}, "widget": {"type": "string", "description": "JSON widget spec (see dashboard_create)"}}, "required": ["dashboard_id", "widget"]}},
    {"name": "dashboard_remove_widget", "description": "Delete one widget by its id. Use dashboard_get to find widget ids.", "inputSchema": {"type": "object", "properties": {"widget_id": {"type": "integer"}, "company_id": {"type": "integer"}}, "required": ["widget_id"]}},
    {"name": "dashboard_delete", "description": "Delete a dashboard (cascades to its widgets). Cannot be undone.", "inputSchema": {"type": "object", "properties": {"dashboard_id": {"type": "integer"}, "company_id": {"type": "integer"}}, "required": ["dashboard_id"]}},
    # Lead generation & CRM (require CRM Manager feature flag — hidden from tools/list when off)
    {"name": "lead_gen_get_brief", "description": "CALL THIS FIRST before generating leads. Returns the lead generation brief saved by the user in Odoo (CRM > Leads > 'Claude Lead Brief' button). The brief contains targeting criteria: industries, countries, buyer persona, product/service fit, keywords, and more. Also returns defaults (team_id, user_id, tag_ids, UTM) to pass to crm_lead_create. If no brief is saved, returns instructions for the user.", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "integer", "description": "Optional company context."}}}},
    {"name": "crm_lead_create", "description": "Create one CRM lead with automatic deduplication and country resolution. Designed for AI-assisted lead generation: call lead_gen_get_brief first to get targeting criteria and defaults, then call this tool once per lead. Duplicates are detected by website domain, email, or company name+location and automatically skipped. Country names are resolved to Odoo country IDs. IMPORTANT: Only use REAL, EXISTING companies. Do NOT invent or hallucinate companies.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "description": "Lead title"}, "partner_name": {"type": "string", "description": "Company legal/trading name (required)"}, "contact_name": {"type": "string"}, "email_from": {"type": "string"}, "phone": {"type": "string"}, "function": {"type": "string"}, "description": {"type": "string"}, "website": {"type": "string"}, "street": {"type": "string"}, "city": {"type": "string"}, "country": {"type": "string", "description": "Country name or ISO code (resolved to country_id)"}, "lead_type": {"type": "string", "enum": ["lead", "opportunity"]}, "team_id": {"type": "integer"}, "user_id": {"type": "integer"}, "tag_ids": {"type": "string", "description": "JSON array of tag IDs, e.g. [1, 2]"}, "campaign_id": {"type": "integer"}, "medium_id": {"type": "integer"}, "source_id": {"type": "integer"}, "expected_revenue": {"type": "number"}, "company_id": {"type": "integer"}}, "required": ["partner_name"]}},
    {"name": "crm_lead_update", "description": "Update one or more existing CRM leads. Use to set stage, assign salesperson, add notes, update contact info, expected revenue, or any crm.lead field. Accepts 'country' as a name (resolved automatically) and 'tag_ids' as a JSON array.", "inputSchema": {"type": "object", "properties": {"lead_ids": {"type": "string", "description": "Single lead id or JSON array of ids"}, "values": {"type": "string", "description": "JSON object of fields to update"}, "company_id": {"type": "integer"}}, "required": ["lead_ids", "values"]}},
    {"name": "crm_lead_search", "description": "Search CRM leads/opportunities with filters. Returns lead details including stage, team, salesperson, contact info, revenue, tags.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string", "description": "JSON Odoo domain"}, "fields": {"type": "string", "description": "JSON array of field names, or empty for defaults"}, "limit": {"type": "integer", "default": 50}, "order": {"type": "string"}, "company_id": {"type": "integer"}}}},
    # Email campaigns (mailing.mailing) — also gated by CRM Manager feature flag
    {"name": "mailing_help", "description": "Returns operating rules for the email campaign assistant: tool list, product campaign workflow, generic campaign workflow, and mailing.mailing field reference. Call before generating campaigns.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "mailing_get_campaign_brief", "description": "STEP 1 of campaign generation. Returns the brief saved by the user in Odoo (Email Marketing -> Mailings -> 'Claude brief' button): products to promote, campaign goal, tone, CTA preference, target mailing lists, custom image URLs, schedule, and step-by-step instructions. Call this BEFORE mailing_for_product.", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "integer"}}}},
    {"name": "mailing_reference", "description": "Load all reference data needed for email campaigns in one call: company info (name, logo_url, website, email, phone), available mailing lists with contact counts, recipient model ids, and UTM campaigns. Always call this before mailing_create.", "inputSchema": {"type": "object", "properties": {"company_id": {"type": "integer"}}}},
    {"name": "mailing_search", "description": "Search existing mailing.mailing (email campaign) records.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string", "description": "JSON Odoo domain"}, "limit": {"type": "integer", "default": 40}, "company_id": {"type": "integer"}}}},
    {"name": "mailing_get", "description": "Read one mailing.mailing record by id, including body_arch.", "inputSchema": {"type": "object", "properties": {"mailing_id": {"type": "integer"}, "company_id": {"type": "integer"}}, "required": ["mailing_id"]}},
    {"name": "mailing_create", "description": "Create a mailing.mailing email campaign record. Required: subject. Common fields: preview, body_arch (HTML), email_from, mailing_model_id (ir.model id or technical name like 'mailing.list'), contact_list_ids ([id,...]), mailing_domain, campaign_id, schedule_type ('now'|'scheduled'), schedule_date.", "inputSchema": {"type": "object", "properties": {"values": {"type": "string", "description": "JSON object of field values"}, "company_id": {"type": "integer"}}, "required": ["values"]}},
    {"name": "mailing_update", "description": "Update one or more mailing.mailing records (subject, body_arch, schedule_date, state, etc.).", "inputSchema": {"type": "object", "properties": {"mailing_ids": {"type": "string"}, "values": {"type": "string"}, "company_id": {"type": "integer"}}, "required": ["mailing_ids", "values"]}},
    {"name": "mailing_for_product", "description": "Look up a product by id, name, or internal reference (default_code). Returns a complete ready-to-use email HTML skeleton with {{SLOT}} placeholders, product_data, mailing_lists, and next_steps. NEVER ask the user for product details after calling this.", "inputSchema": {"type": "object", "properties": {"product_id": {"type": "integer"}, "product_name": {"type": "string"}, "extra_instructions": {"type": "string"}, "company_id": {"type": "integer"}}}},
    {"name": "mailing_list_create", "description": "Create a mailing.list (diffusion/distribution list).", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "is_public": {"type": "boolean", "default": False}, "company_id": {"type": "integer"}}, "required": ["name"]}},
    {"name": "mailing_contact_create", "description": "Create a mailing.contact and optionally subscribe it to mailing lists. Country names are resolved automatically.", "inputSchema": {"type": "object", "properties": {"email": {"type": "string"}, "name": {"type": "string"}, "first_name": {"type": "string"}, "last_name": {"type": "string"}, "company_name": {"type": "string"}, "country": {"type": "string"}, "title_id": {"type": "integer"}, "list_ids": {"type": "string", "description": "JSON array of mailing.list IDs"}, "tag_ids": {"type": "string"}, "company_id": {"type": "integer"}}, "required": ["email"]}},
    {"name": "mailing_contact_search", "description": "Search mailing contacts. Returns name, email, company, country, lists, tags.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}, "limit": {"type": "integer", "default": 100}, "company_id": {"type": "integer"}}}},
]

# Tools that modify data; we must commit after success so changes persist.
MCP_WRITE_TOOLS = frozenset({
    "odoo_create", "odoo_write", "odoo_unlink", "odoo_execute",
    "dashboard_create", "dashboard_update", "dashboard_add_widget",
    "dashboard_remove_widget", "dashboard_delete",
    "crm_lead_create", "crm_lead_update",
    "mailing_create", "mailing_update",
    "mailing_list_create", "mailing_contact_create",
})

DISPATCH = {
    "list_tables": (list_tables, _format_list_tables),
    "describe_table": (describe_table, _format_describe),
    "get_table_row_count": (get_table_row_count, lambda x: "Row count: %s" % x),
    "run_readonly_query": (run_readonly_query, _format_run_query),
    "get_odoo_models_info": (get_odoo_models_info, _format_odoo_models),
    "get_table_schema_pg": (get_table_schema_pg, _format_schema_pg),
    "odoo_search_read": (odoo_search_read, _format_search_read),
    "odoo_create": (odoo_create, _format_create),
    "odoo_write": (odoo_write, _format_write),
    "odoo_unlink": (odoo_unlink, _format_unlink),
    "odoo_execute": (odoo_execute, _format_execute),
    # Claude Dashboards
    "dashboard_list": (dashboard_list, _format_dashboard_list),
    "dashboard_get": (dashboard_get, _format_dashboard_get),
    "dashboard_get_schema_help": (dashboard_get_schema_help, _format_dashboard_schema),
    "dashboard_create": (dashboard_create, _format_dashboard_create),
    "dashboard_update": (dashboard_update, _format_dashboard_update),
    "dashboard_add_widget": (dashboard_add_widget, _format_dashboard_add_widget),
    "dashboard_remove_widget": (dashboard_remove_widget, _format_dashboard_remove_widget),
    "dashboard_delete": (dashboard_delete, _format_dashboard_delete),
    # Lead generation & CRM
    "lead_gen_get_brief": (lead_gen_get_brief, _format_lead_gen_brief),
    "crm_lead_create": (crm_lead_create, _format_crm_lead_create),
    "crm_lead_update": (crm_lead_update, _format_crm_lead_update),
    "crm_lead_search": (crm_lead_search, _format_crm_lead_search),
    # Email campaign (mailing.mailing) tools
    "mailing_help": (mailing_help, _format_help),
    "mailing_get_campaign_brief": (
        mailing_get_campaign_brief,
        lambda r: (
            r.get("next_steps", "") + "\n\n" + _format_json(r)
            if r.get("saved") and r.get("next_steps")
            else _format_json(r)
        ),
    ),
    "mailing_reference": (mailing_reference, _format_json),
    "mailing_search": (mailing_search, _format_json),
    "mailing_get": (mailing_get, _format_json),
    "mailing_create": (
        mailing_create,
        lambda r: "Created mailing.mailing id=%s subject='%s' state=%s" % (r["id"], r["subject"], r["state"]),
    ),
    "mailing_update": (
        mailing_update,
        lambda r: "Updated %s mailing(s) ids=%s" % (r["updated"], r["ids"]),
    ),
    "mailing_for_product": (
        mailing_for_product,
        lambda r: (
            r.get("next_steps", "") + "\n\n"
            + "=== email_skeleton (fill {{SLOT}} placeholders, use as body_arch) ===\n"
            + r.get("email_skeleton", "") + "\n\n"
            + _format_json({
                "product_data": r.get("product_data"),
                "company_data": r.get("company_data"),
                "mailing_lists": r.get("mailing_lists"),
            })
            if r.get("next_steps")
            else _format_json(r)
        ),
    ),
    "mailing_list_create": (mailing_list_create, _format_mailing_list_create),
    "mailing_contact_create": (mailing_contact_create, _format_mailing_contact_create),
    "mailing_contact_search": (mailing_contact_search, _format_mailing_contact_search),
}


# ---------------------------------------------------------------------------
# Access Manager (optional feature) — merge the ported access-rules tools.
# ---------------------------------------------------------------------------
# Tool names gated behind the Access Manager feature flag. Hidden from
# tools/list and refused on tools/call when the flag is off.
MCP_ACCESS_MANAGER_TOOLS = frozenset(access_management_tools.ACCESS_DISPATCH.keys())

# Expose the access tools in discovery and make them callable.
TOOL_DEFINITIONS = TOOL_DEFINITIONS + access_management_tools.ACCESS_TOOL_DEFINITIONS
DISPATCH.update(access_management_tools.ACCESS_DISPATCH)

# The access write tools must commit like the other write tools.
MCP_WRITE_TOOLS = MCP_WRITE_TOOLS | access_management_tools.ACCESS_WRITE_TOOLS

# ---------------------------------------------------------------------------
# SEO Manager (optional feature) — merge the website SEO tools.
# ---------------------------------------------------------------------------
# Tool names gated behind the SEO Manager feature flag. Hidden from tools/list
# and refused on tools/call when the flag is off.
MCP_SEO_MANAGER_TOOLS = frozenset(seo_tools.SEO_DISPATCH.keys())

# Expose the SEO tools in discovery and make them callable.
TOOL_DEFINITIONS = TOOL_DEFINITIONS + seo_tools.SEO_TOOL_DEFINITIONS
DISPATCH.update(seo_tools.SEO_DISPATCH)

# The SEO write tools must commit like the other write tools.
MCP_WRITE_TOOLS = MCP_WRITE_TOOLS | seo_tools.SEO_WRITE_TOOLS
