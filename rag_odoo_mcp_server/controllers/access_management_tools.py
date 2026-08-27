# -*- coding: utf-8 -*-
"""
MCP tools for managing user access rules via the simplify_access_management module.
Provides high-level, LLM-friendly tools for controlling what users can see and do in Odoo.
"""
import json
import logging

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_list(value, param_name):
    """Coerce an LLM-supplied argument into a Python list.

    Accepts: None, list, int, or string (JSON array, or a bare scalar).
    Raises a readable ValueError if a string looks like JSON but is malformed,
    so tool callers get a clear message instead of an uncaught JSONDecodeError.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Invalid JSON array for '%s': %s. Example: '[\"foo\", 2]'" % (param_name, exc)
                )
            if not isinstance(parsed, list):
                raise ValueError("'%s' must be a JSON array, got %s" % (param_name, type(parsed).__name__))
            return parsed
        return [stripped]
    raise ValueError("'%s' must be a list or string, got %s" % (param_name, type(value).__name__))


def _parse_json_domain(value, param_name="domain"):
    """Coerce an LLM-supplied argument into an Odoo domain (list of tuples/strings)."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Invalid JSON for '%s': %s. Example: '[[\"user_id\", \"=\", 0]]'" % (param_name, exc)
            )
        if not isinstance(parsed, list):
            raise ValueError("'%s' must decode to a JSON array" % param_name)
        return parsed
    raise ValueError("'%s' must be a list or JSON string" % param_name)




def _find_users(env, identifier):
    """Find res.users by id, login, or name fragment. Returns recordset."""
    User = env["res.users"]
    if isinstance(identifier, int):
        return User.browse(identifier).exists()
    if isinstance(identifier, str):
        if identifier.isdigit():
            return User.browse(int(identifier)).exists()
        # Try exact login first
        users = User.search([("login", "=", identifier)], limit=5)
        if users:
            return users
        # Then name ilike
        users = User.search([("name", "ilike", identifier)], limit=10)
        return users
    if isinstance(identifier, list):
        result = User.browse()
        for item in identifier:
            result |= _find_users(env, item)
        return result
    return User.browse()


def _find_menus(env, identifier):
    """Find ir.ui.menu by id, name, or xml_id fragment. Returns recordset."""
    Menu = env["ir.ui.menu"]
    if isinstance(identifier, int):
        return Menu.browse(identifier).exists()
    if isinstance(identifier, str):
        if identifier.isdigit():
            return Menu.browse(int(identifier)).exists()
        menus = Menu.search([("name", "ilike", identifier)], limit=20)
        return menus
    if isinstance(identifier, list):
        result = Menu.browse()
        for item in identifier:
            result |= _find_menus(env, item)
        return result
    return Menu.browse()


def _find_model(env, identifier):
    """Find ir.model by id, technical name, or name fragment. Returns recordset."""
    IrModel = env["ir.model"]
    if isinstance(identifier, int):
        return IrModel.browse(identifier).exists()
    if isinstance(identifier, str):
        if identifier.isdigit():
            return IrModel.browse(int(identifier)).exists()
        # Try exact technical name
        model = IrModel.search([("model", "=", identifier)], limit=1)
        if model:
            return model
        # Then name ilike
        model = IrModel.search([("name", "ilike", identifier)], limit=5)
        return model
    return IrModel.browse()


def _find_rule(env, identifier):
    """Find rag.mcp.access.management by id or name."""
    Rule = env["rag.mcp.access.management"]
    if isinstance(identifier, int):
        return Rule.browse(identifier).exists()
    if isinstance(identifier, str):
        if identifier.isdigit():
            return Rule.browse(int(identifier)).exists()
        return Rule.search([("name", "ilike", identifier)], limit=5)
    return Rule.browse()


def _get_or_create_rule(env, rule_id=None, rule_name=None, user_ids=None):
    """Get existing rule or create a new one. Returns single record."""
    Rule = env["rag.mcp.access.management"]
    if rule_id:
        rule = Rule.browse(int(rule_id)).exists()
        if not rule:
            raise ValueError("Access rule with id %s not found" % rule_id)
        return rule
    if rule_name:
        rule = Rule.search([("name", "=", rule_name)], limit=1)
        if rule:
            return rule
    # Create new rule
    name = rule_name or "MCP Access Rule"
    vals = {"name": name}
    if user_ids:
        vals["user_ids"] = [(6, 0, user_ids)]
    return Rule.create(vals)


def _menu_item_ids_for_menus(env, menu_ids):
    """Get rag.mcp.menu.item record ids matching ir.ui.menu ids (creating missing ones).

    Batch-optimized: one search + one create for the whole list, so
    whitelist operations that touch hundreds of menus don't issue N queries.

    NOTE: rag.mcp.menu.item.menu_id is a plain Integer field (see models/menu_item.py),
    NOT a Many2one — so we read `mi.menu_id` as an int, never `mi.menu_id.id`.
    """
    if not menu_ids:
        return []
    menu_ids = list(dict.fromkeys(menu_ids))  # de-dup, preserve order
    MenuItem = env["rag.mcp.menu.item"]
    existing = MenuItem.search([("menu_id", "in", menu_ids)])
    existing_map = {mi.menu_id: mi.id for mi in existing}
    missing = [mid for mid in menu_ids if mid not in existing_map]
    if missing:
        Menu = env["ir.ui.menu"].sudo()
        vals_list = []
        for m in Menu.browse(missing).exists():
            vals_list.append({"menu_id": m.id, "name": m.complete_name or m.name})
        if vals_list:
            for new_item in MenuItem.create(vals_list):
                existing_map[new_item.menu_id] = new_item.id
    return [existing_map[mid] for mid in menu_ids if mid in existing_map]


def _resolve_menu_path(env, path):
    """Resolve a slash-separated menu path like 'Inventory/Operations/Transfers'
    to a single ir.ui.menu record. Empty recordset on miss.

    Walks from the root match segment-by-segment using case-insensitive exact
    name match. Path form is the only unambiguous way to target a nested menu
    when multiple apps use the same sub-menu name (e.g. 'Configuration').
    """
    Menu = env["ir.ui.menu"].sudo()
    segments = [s.strip() for s in (path or "").split("/") if s.strip()]
    if not segments:
        return Menu.browse()
    current = Menu.search(
        [("parent_id", "=", False), ("name", "=ilike", segments[0])],
        limit=1,
    )
    if not current:
        return Menu.browse()
    for seg in segments[1:]:
        nxt = Menu.search(
            [("parent_id", "=", current.id), ("name", "=ilike", seg)],
            limit=1,
        )
        if not nxt:
            return Menu.browse()
        current = nxt
    return current


def _expand_menu_ancestors(env, menu_recs):
    """Return `menu_recs` plus every ancestor menu, so a whitelisted leaf
    stays reachable from the top nav bar."""
    if not menu_recs:
        return menu_recs
    Menu = env["ir.ui.menu"].sudo()
    ancestor_ids = set()
    for m in menu_recs:
        if not m.parent_path:
            continue
        for part in m.parent_path.strip("/").split("/"):
            if part.isdigit():
                ancestor_ids.add(int(part))
    return menu_recs | Menu.browse(list(ancestor_ids))


def _expand_menu_descendants(env, menu_recs):
    """Return a recordset containing `menu_recs` plus ALL descendant menus
    (children, grand-children, ...). Uses the parent_path computed field
    provided by ir.ui.menu for efficient recursive lookup."""
    if not menu_recs:
        return menu_recs
    Menu = env["ir.ui.menu"].sudo()
    all_menus = Menu.browse()
    for m in menu_recs:
        all_menus |= m
        # children recursively via parent_path LIKE 'parent_path/%'
        if m.parent_path:
            descendants = Menu.search([("parent_path", "=like", "%s%%" % m.parent_path)])
            all_menus |= descendants
    return all_menus


def _serialize_rule(rule):
    """Serialize an rag.mcp.access.management record for output."""
    return {
        "id": rule.id,
        "name": rule.name,
        "active": rule.active,
        "users": [{"id": u.id, "name": u.name, "login": u.login} for u in rule.user_ids],
        "hidden_menus": len(rule.hide_menu_ids),
        "model_restrictions": len(rule.remove_action_ids),
        "field_restrictions": len(rule.hide_field_ids),
        "domain_rules": len(rule.access_domain_ah_ids),
        "hidden_buttons_tabs": len(rule.hide_view_nodes_ids),
        "hidden_filters_groups": len(rule.hide_filters_groups_ids),
        "chatter_rules": len(rule.hide_chatter_ids),
        "readonly": rule.readonly,
        "disable_login": rule.disable_login,
        "disable_debug_mode": rule.disable_debug_mode,
        "hide_export": rule.hide_export,
        "hide_import": rule.hide_import,
        "total_rules": rule.total_rules,
    }


# ---------------------------------------------------------------------------
# Tool: list_access_rules
# ---------------------------------------------------------------------------

def list_access_rules(cr, env):
    """List all access management rules with summary."""
    rules = env["rag.mcp.access.management"].search([], order="name")
    return {"count": len(rules), "rules": [_serialize_rule(r) for r in rules]}


def _format_list_access_rules(result):
    lines = ["Access Management Rules (%s total):" % result["count"], ""]
    for r in result["rules"]:
        users = ", ".join(u["name"] for u in r["users"][:5])
        if len(r["users"]) > 5:
            users += " +%d more" % (len(r["users"]) - 5)
        status = "ACTIVE" if r["active"] else "INACTIVE"
        lines.append("  [%s] id=%s '%s' | Users: %s | Menu:%s Model:%s Field:%s Domain:%s | %s" % (
            status, r["id"], r["name"], users or "none",
            r["hidden_menus"], r["model_restrictions"],
            r["field_restrictions"], r["domain_rules"],
            "readonly" if r["readonly"] else ""
        ))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_user_access_summary
# ---------------------------------------------------------------------------

def get_user_access_summary(cr, env, user):
    """Get all access restrictions applied to a specific user."""
    users = _find_users(env, user)
    if not users:
        raise ValueError("User not found: %s. Use search_users to find the correct user." % user)
    if len(users) > 1:
        return {
            "error": "Multiple users found. Please be more specific.",
            "matches": [{"id": u.id, "name": u.name, "login": u.login} for u in users],
        }
    user_rec = users[0]
    rules = env["rag.mcp.access.management"].search([
        ("user_ids", "in", [user_rec.id]),
        ("active", "=", True),
    ])
    result = {
        "user": {"id": user_rec.id, "name": user_rec.name, "login": user_rec.login},
        "rules_count": len(rules),
        "rules": [],
    }
    for rule in rules:
        rule_data = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "readonly": rule.readonly,
            "disable_login": rule.disable_login,
            "disable_debug_mode": rule.disable_debug_mode,
            "global_hide_export": rule.hide_export,
            "global_hide_import": rule.hide_import,
            "hidden_menus": [],
            "model_restrictions": [],
            "field_restrictions": [],
            "domain_rules": [],
            "hidden_buttons_tabs": [],
            "chatter_rules": [],
        }
        for mi in rule.hide_menu_ids:
            menu = env["ir.ui.menu"].search([("id", "=", mi.menu_id)], limit=1)
            rule_data["hidden_menus"].append({
                "menu_item_id": mi.id,
                "name": mi.name,
                "menu_id": mi.menu_id,
            })
        for ra in rule.remove_action_ids:
            rule_data["model_restrictions"].append({
                "model": ra.model_id.model if ra.model_id else "",
                "model_name": ra.model_id.name if ra.model_id else "",
                "restrict_create": ra.restrict_create,
                "restrict_edit": ra.restrict_edit,
                "restrict_delete": ra.restrict_delete,
                "restrict_archive": ra.restrict_archive_unarchive,
                "restrict_duplicate": ra.restrict_duplicate,
                "restrict_export": ra.restrict_export,
                "restrict_import": ra.restrict_import,
                "readonly": ra.readonly,
                "hidden_views": [{"name": v.name, "techname": v.techname} for v in ra.view_data_ids],
            })
        for hf in rule.hide_field_ids:
            rule_data["field_restrictions"].append({
                "model": hf.model_id.model if hf.model_id else "",
                "fields": [{"name": f.name, "label": f.field_description} for f in hf.field_id],
                "invisible": hf.invisible,
                "readonly": hf.readonly,
                "required": hf.required,
            })
        for da in rule.access_domain_ah_ids:
            rule_data["domain_rules"].append({
                "model": da.model_id.model if da.model_id else "",
                "domain": da.domain,
                "read": da.read_right,
                "create": da.create_right,
                "write": da.write_right,
                "delete": da.delete_right,
            })
        for hvn in rule.hide_view_nodes_ids:
            buttons = [{"name": b.attribute_name, "label": b.attribute_string} for b in hvn.btn_store_model_nodes_ids]
            tabs = [{"name": p.attribute_name, "label": p.attribute_string} for p in hvn.page_store_model_nodes_ids]
            rule_data["hidden_buttons_tabs"].append({
                "model": hvn.model_id.model if hvn.model_id else "",
                "hidden_buttons": buttons,
                "hidden_tabs": tabs,
            })
        for hc in rule.hide_chatter_ids:
            rule_data["chatter_rules"].append({
                "model": hc.model_id.model if hc.model_id else "",
                "hide_chatter": hc.hide_chatter,
                "hide_send_mail": hc.hide_send_mail,
                "hide_log_notes": hc.hide_log_notes,
                "hide_schedule_activity": hc.hide_schedule_activity,
            })
        result["rules"].append(rule_data)
    return result


def _format_user_access_summary(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - id=%s login=%s name=%s" % (m["id"], m["login"], m["name"]))
        return "\n".join(lines)

    u = result["user"]
    lines = ["Access summary for %s (login=%s, id=%s):" % (u["name"], u["login"], u["id"]),
             "Rules applied: %s" % result["rules_count"], ""]
    for rule in result["rules"]:
        lines.append("--- Rule: '%s' (id=%s) ---" % (rule["rule_name"], rule["rule_id"]))
        if rule["readonly"]:
            lines.append("  ** USER IS READ-ONLY **")
        if rule["disable_login"]:
            lines.append("  ** LOGIN DISABLED **")
        if rule["global_hide_export"]:
            lines.append("  Global: export hidden")
        if rule["global_hide_import"]:
            lines.append("  Global: import hidden")
        if rule["hidden_menus"]:
            lines.append("  Hidden menus:")
            for m in rule["hidden_menus"]:
                lines.append("    - %s" % m["name"])
        if rule["model_restrictions"]:
            lines.append("  Model restrictions:")
            for mr in rule["model_restrictions"]:
                restrictions = []
                if mr["restrict_create"]:
                    restrictions.append("no-create")
                if mr["restrict_edit"]:
                    restrictions.append("no-edit")
                if mr["restrict_delete"]:
                    restrictions.append("no-delete")
                if mr["restrict_archive"]:
                    restrictions.append("no-archive")
                if mr["restrict_duplicate"]:
                    restrictions.append("no-duplicate")
                if mr["restrict_export"]:
                    restrictions.append("no-export")
                if mr["restrict_import"]:
                    restrictions.append("no-import")
                if mr["readonly"]:
                    restrictions.append("readonly")
                lines.append("    - %s (%s): %s" % (mr["model_name"], mr["model"], ", ".join(restrictions) or "view restrictions only"))
                if mr["hidden_views"]:
                    lines.append("      Hidden views: %s" % ", ".join(v["name"] for v in mr["hidden_views"]))
        if rule["field_restrictions"]:
            lines.append("  Field restrictions:")
            for fr in rule["field_restrictions"]:
                flags = []
                if fr["invisible"]:
                    flags.append("hidden")
                if fr["readonly"]:
                    flags.append("readonly")
                if fr["required"]:
                    flags.append("required")
                fields_str = ", ".join(f["name"] for f in fr["fields"][:10])
                lines.append("    - %s [%s]: %s" % (fr["model"], ", ".join(flags), fields_str))
        if rule["domain_rules"]:
            lines.append("  Domain (record-level) rules:")
            for dr in rule["domain_rules"]:
                rights = []
                if dr["read"]:
                    rights.append("read")
                if dr["create"]:
                    rights.append("create")
                if dr["write"]:
                    rights.append("write")
                if dr["delete"]:
                    rights.append("delete")
                lines.append("    - %s domain=%s rights=%s" % (dr["model"], dr["domain"], ",".join(rights)))
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: search_users
# ---------------------------------------------------------------------------

def search_users(cr, env, query="", limit=20):
    """Search Odoo users by name or login."""
    User = env["res.users"]
    domain = []
    if query:
        domain = ["|", ("name", "ilike", query), ("login", "ilike", query)]
    limit = min(int(limit) if limit else 20, 100)
    users = User.search(domain, limit=limit, order="name")
    return {
        "count": len(users),
        "users": [{"id": u.id, "name": u.name, "login": u.login, "active": u.active} for u in users],
    }


def _format_search_users(result):
    lines = ["Users found: %s" % result["count"], ""]
    for u in result["users"]:
        status = "" if u["active"] else " [INACTIVE]"
        lines.append("  id=%s | %s (%s)%s" % (u["id"], u["name"], u["login"], status))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: search_menus
# ---------------------------------------------------------------------------

def search_menus(cr, env, query="", parent_only=True):
    """Search Odoo menus. Use parent_only=true to get top-level app menus."""
    Menu = env["ir.ui.menu"]
    domain = []
    if query:
        domain.append(("name", "ilike", query))
    if parent_only:
        domain.append(("parent_id", "=", False))
    menus = Menu.search(domain, limit=50, order="sequence,name")
    return {
        "count": len(menus),
        "menus": [{"id": m.id, "name": m.name, "complete_name": m.complete_name, "parent_id": m.parent_id.id if m.parent_id else False} for m in menus],
    }


def _format_search_menus(result):
    lines = ["Menus found: %s" % result["count"], ""]
    for m in result["menus"]:
        lines.append("  id=%s | %s" % (m["id"], m["complete_name"] or m["name"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: create_access_rule
# ---------------------------------------------------------------------------

def create_access_rule(cr, env, name, users=None):
    """Create a new access management rule and optionally assign users."""
    Rule = env["rag.mcp.access.management"]
    vals = {"name": name}
    if users:
        users = _parse_json_list(users, "users")
        if users:
            found = _find_users(env, users)
            if not found:
                raise ValueError("No users found matching: %s" % users)
            vals["user_ids"] = [(6, 0, found.ids)]
    rule = Rule.create(vals)
    return _serialize_rule(rule)


def _format_create_access_rule(result):
    users = ", ".join(u["name"] for u in result.get("users", []))
    return "Created access rule '%s' (id=%s) for users: %s" % (result["name"], result["id"], users or "none")


# ---------------------------------------------------------------------------
# Tool: delete_access_rule
# ---------------------------------------------------------------------------

def delete_access_rule(cr, env, rule_id):
    """Delete an access management rule by id."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)
    name = rule.name
    rule.unlink()
    return {"deleted": True, "id": int(rule_id), "name": name}


def _format_delete_access_rule(result):
    return "Deleted access rule '%s' (id=%s)" % (result["name"], result["id"])


# ---------------------------------------------------------------------------
# Tool: assign_users_to_rule
# ---------------------------------------------------------------------------

def assign_users_to_rule(cr, env, rule_id, users, action="add"):
    """Add or remove users from an access rule. action: 'add', 'remove', or 'set'."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)
    users = _parse_json_list(users, "users")
    if not users:
        raise ValueError("'users' cannot be empty")
    found = _find_users(env, users)
    if not found:
        raise ValueError("No users found matching: %s" % users)

    if action == "add":
        rule.write({"user_ids": [(4, uid) for uid in found.ids]})
    elif action == "remove":
        rule.write({"user_ids": [(3, uid) for uid in found.ids]})
    elif action == "set":
        rule.write({"user_ids": [(6, 0, found.ids)]})
    else:
        raise ValueError("action must be 'add', 'remove', or 'set'")

    return _serialize_rule(rule)


def _format_assign_users(result):
    users = ", ".join(u["name"] for u in result.get("users", []))
    return "Rule '%s' (id=%s) now has users: %s" % (result["name"], result["id"], users or "none")


# ---------------------------------------------------------------------------
# Tool: hide_menus
# ---------------------------------------------------------------------------

def hide_menus(cr, env, rule_id, menus, action="add", include_submenus=True):
    """Hide or unhide menus for users in a rule. menus: list of menu names or ids. action: 'add' or 'remove'.
    When include_submenus is true (default), every descendant (submenu, sub-submenu ...) is also hidden."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)
    menus = _parse_json_list(menus, "menus")
    if not menus:
        raise ValueError("'menus' cannot be empty")

    found_menus = _find_menus(env, menus)
    if not found_menus:
        raise ValueError("No menus found matching: %s. Use search_menus to find available menus." % menus)

    if _to_bool(include_submenus):
        found_menus = _expand_menu_descendants(env, found_menus)

    menu_item_ids = _menu_item_ids_for_menus(env, found_menus.ids)
    if not menu_item_ids:
        raise ValueError("Could not map menus to rag.mcp.menu.item records.")

    if action == "add":
        rule.write({"hide_menu_ids": [(4, mid) for mid in menu_item_ids]})
    elif action == "remove":
        rule.write({"hide_menu_ids": [(3, mid) for mid in menu_item_ids]})
    else:
        raise ValueError("action must be 'add' or 'remove'")

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "action": action,
        "menus_affected": [{"id": m.id, "name": m.complete_name or m.name} for m in found_menus],
        "total_hidden_menus": len(rule.hide_menu_ids),
    }


def _format_hide_menus(result):
    menus = ", ".join(m["name"] for m in result["menus_affected"])
    verb = "Hidden" if result["action"] == "add" else "Unhidden"
    return "%s menus for rule '%s': %s (total hidden: %s)" % (verb, result["rule_name"], menus, result["total_hidden_menus"])


# ---------------------------------------------------------------------------
# Tool: clear_menu_hides  (reset — make all menus visible again)
# ---------------------------------------------------------------------------

def clear_menu_hides(cr, env, rule_id):
    """Empty the rule's hide_menu_ids so every menu becomes visible again
    for the users attached to this rule. Use this for 'user X should see
    all menus again' / 'reset menu restrictions for this rule' requests.

    Leaves the rule itself, its user assignments, and any non-menu
    restrictions untouched — only the menu-hiding list is wiped.
    """
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    previous_count = len(rule.hide_menu_ids)
    if previous_count:
        rule.write({"hide_menu_ids": [(5, 0, 0)]})

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "cleared_count": previous_count,
        "users": [{"id": u.id, "name": u.name, "login": u.login} for u in rule.user_ids],
    }


def _format_clear_menu_hides(result):
    users = ", ".join(u["name"] for u in result["users"]) or "none"
    if result["cleared_count"] == 0:
        return "Rule '%s' (id=%s) already had no hidden menus. Users: %s." % (
            result["rule_name"], result["rule_id"], users,
        )
    return "Cleared %s hidden menus on rule '%s' (id=%s). Users now see every menu via this rule: %s." % (
        result["cleared_count"], result["rule_name"], result["rule_id"], users,
    )


# ---------------------------------------------------------------------------
# Tool: allow_only_menus  (whitelist mode)
# ---------------------------------------------------------------------------

def allow_only_menus(cr, env, rule_id, menus, include_descendants=True):
    """Whitelist mode: hide every menu EXCEPT the ones listed.

    Accepts menu paths ('Inventory/Operations/Transfers' — recommended,
    unambiguous), plain names ('Transfers' — first match wins), or integer
    ids. Ancestors of whitelisted menus are always kept visible so the user
    can navigate down to them; descendants are kept by default so a parent
    menu opens up to all its children.

    Replaces the rule's existing hide_menu_ids — this tool is "set the
    visible menu set" not "add to it".
    """
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    menus = _parse_json_list(menus, "menus")
    if not menus:
        raise ValueError("'menus' cannot be empty")

    Menu = env["ir.ui.menu"].sudo()
    whitelisted = Menu.browse()
    resolved = []  # list of (input_value, match_list)
    unresolved = []

    for m in menus:
        matched = Menu.browse()
        # Path form: walk segment-by-segment (unambiguous)
        if isinstance(m, str) and "/" in m:
            matched = _resolve_menu_path(env, m)
        # Fall back to the generic finder (id / exact name / name ilike)
        if not matched:
            matched = _find_menus(env, m)
        if matched:
            whitelisted |= matched
            resolved.append({
                "input": m,
                "matches": [{"id": x.id, "name": x.complete_name or x.name} for x in matched],
            })
        else:
            unresolved.append(m)

    if not whitelisted:
        raise ValueError(
            "None of the given menus could be resolved: %s. "
            "Use search_menus to find exact names, or a path like 'Inventory/Operations/Transfers'."
            % unresolved
        )

    # Keep set: whitelisted + ancestors (+ descendants if requested)
    keep = _expand_menu_ancestors(env, whitelisted)
    if _to_bool(include_descendants):
        keep = _expand_menu_descendants(env, keep)

    all_menus = Menu.search([])
    to_hide = all_menus - keep

    menu_item_ids = _menu_item_ids_for_menus(env, to_hide.ids)
    rule.write({"hide_menu_ids": [(6, 0, menu_item_ids)]})

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "resolved": resolved,
        "unresolved": unresolved,
        "include_descendants": _to_bool(include_descendants),
        "whitelisted_count": len(whitelisted),
        "kept_count": len(keep),
        "hidden_count": len(to_hide),
        "total_menus": len(all_menus),
        "sample_kept": [
            {"id": m.id, "name": m.complete_name or m.name}
            for m in (keep & all_menus)[:10]
        ],
        "sample_hidden": [
            {"id": m.id, "name": m.complete_name or m.name}
            for m in to_hide[:10]
        ],
    }


def _format_allow_only_menus(result):
    lines = [
        "Whitelist applied on rule '%s' (id=%s)." % (result["rule_name"], result["rule_id"]),
        "",
        "Whitelisted (%s):" % result["whitelisted_count"],
    ]
    for r in result["resolved"]:
        names = ", ".join(m["name"] for m in r["matches"])
        lines.append("  '%s' -> %s" % (r["input"], names))
    if result["unresolved"]:
        lines.append("  Unresolved (ignored): %s" % ", ".join(str(x) for x in result["unresolved"]))
    lines.append("")
    lines.append(
        "Kept %s of %s menus visible (descendants %s); hid %s." % (
            result["kept_count"],
            result["total_menus"],
            "included" if result["include_descendants"] else "excluded",
            result["hidden_count"],
        )
    )
    if result["sample_hidden"]:
        sample = ", ".join(m["name"] for m in result["sample_hidden"])
        lines.append("Sample hidden: %s%s" % (
            sample,
            " ..." if result["hidden_count"] > len(result["sample_hidden"]) else "",
        ))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: restrict_model_operations
# ---------------------------------------------------------------------------

def restrict_model_operations(cr, env, rule_id, model, restrict_create=None, restrict_edit=None,
                               restrict_delete=None, restrict_archive=None, restrict_duplicate=None,
                               restrict_export=None, restrict_import=None, readonly=None,
                               restrict_chatter=None, restrict_spreadsheet=None):
    """Set model-level operation restrictions (create, edit, delete, etc.) on a rule."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    ir_model = _find_model(env, model)
    if not ir_model:
        raise ValueError("Model not found: %s" % model)
    if len(ir_model) > 1:
        return {
            "error": "Multiple models found. Please use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    # Find existing rag.mcp.remove.action for this model in this rule
    existing = env["rag.mcp.remove.action"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
    ], limit=1)

    vals = {"model_id": ir_model.id}
    if restrict_create is not None:
        vals["restrict_create"] = _to_bool(restrict_create)
    if restrict_edit is not None:
        vals["restrict_edit"] = _to_bool(restrict_edit)
    if restrict_delete is not None:
        vals["restrict_delete"] = _to_bool(restrict_delete)
    if restrict_archive is not None:
        vals["restrict_archive_unarchive"] = _to_bool(restrict_archive)
    if restrict_duplicate is not None:
        vals["restrict_duplicate"] = _to_bool(restrict_duplicate)
    if restrict_export is not None:
        vals["restrict_export"] = _to_bool(restrict_export)
    if restrict_import is not None:
        vals["restrict_import"] = _to_bool(restrict_import)
    if readonly is not None:
        vals["readonly"] = _to_bool(readonly)
    if restrict_chatter is not None:
        vals["restrict_chatter"] = _to_bool(restrict_chatter)
    if restrict_spreadsheet is not None:
        vals["restrict_spreadsheet"] = _to_bool(restrict_spreadsheet)

    if existing:
        existing.write(vals)
        rec = existing
    else:
        vals["access_management_id"] = rule.id
        rec = env["rag.mcp.remove.action"].create(vals)

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "model": ir_model.model,
        "model_name": ir_model.name,
        "restrictions": {
            "create": rec.restrict_create,
            "edit": rec.restrict_edit,
            "delete": rec.restrict_delete,
            "archive": rec.restrict_archive_unarchive,
            "duplicate": rec.restrict_duplicate,
            "export": rec.restrict_export,
            "import": rec.restrict_import,
            "readonly": rec.readonly,
            "chatter": rec.restrict_chatter,
        },
    }


def _format_restrict_model(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    r = result["restrictions"]
    active = [k for k, v in r.items() if v]
    return "Model restrictions for '%s' (%s) on rule '%s': %s" % (
        result["model_name"], result["model"], result["rule_name"],
        ", ".join(active) if active else "none"
    )


# ---------------------------------------------------------------------------
# Tool: set_field_access
# ---------------------------------------------------------------------------

def set_field_access(cr, env, rule_id, model, fields, invisible=False, readonly=False, required=False):
    """Set field-level visibility/readonly/required for specific fields on a model."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    ir_model = _find_model(env, model)
    if not ir_model or len(ir_model) > 1:
        if not ir_model:
            raise ValueError("Model not found: %s" % model)
        return {
            "error": "Multiple models found. Use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    fields = _parse_json_list(fields, "fields")
    if not fields:
        raise ValueError("'fields' cannot be empty")

    # Find ir.model.fields
    IrField = env["ir.model.fields"]
    field_recs = IrField.browse()
    for fname in fields:
        f = IrField.search([("model_id", "=", ir_model.id), ("name", "=", fname)], limit=1)
        if f:
            field_recs |= f
        else:
            raise ValueError("Field '%s' not found on model %s" % (fname, ir_model.model))

    # Find existing rag.mcp.hide.field for this model in this rule
    existing = env["rag.mcp.hide.field"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
        ("invisible", "=", _to_bool(invisible)),
        ("readonly", "=", _to_bool(readonly)),
        ("required", "=", _to_bool(required)),
    ], limit=1)

    if existing:
        # Add fields to existing record
        existing.write({"field_id": [(4, f.id) for f in field_recs]})
        rec = existing
    else:
        rec = env["rag.mcp.hide.field"].create({
            "access_management_id": rule.id,
            "model_id": ir_model.id,
            "field_id": [(6, 0, field_recs.ids)],
            "invisible": _to_bool(invisible),
            "readonly": _to_bool(readonly),
            "required": _to_bool(required),
        })

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "model": ir_model.model,
        "fields": [f.name for f in rec.field_id],
        "invisible": rec.invisible,
        "readonly": rec.readonly,
        "required": rec.required,
    }


def _format_field_access(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    flags = []
    if result["invisible"]:
        flags.append("hidden")
    if result["readonly"]:
        flags.append("readonly")
    if result["required"]:
        flags.append("required")
    return "Field access on %s for rule '%s': fields=%s flags=%s" % (
        result["model"], result["rule_name"], ", ".join(result["fields"]), ", ".join(flags)
    )


# ---------------------------------------------------------------------------
# Tool: set_domain_access
# ---------------------------------------------------------------------------

def set_domain_access(cr, env, rule_id, model, domain="[]", read=True, create=False, write=False, delete=False):
    """Set domain-based record-level access on a model. Domain filters which records the user can see."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    ir_model = _find_model(env, model)
    if not ir_model or len(ir_model) > 1:
        if not ir_model:
            raise ValueError("Model not found: %s" % model)
        return {
            "error": "Multiple models found. Use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    # Find existing domain rule for this model
    existing = env["rag.mcp.access.domain.ah"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
    ], limit=1)

    parsed_domain = _parse_json_domain(domain)
    vals = {
        "model_id": ir_model.id,
        "apply_domain": True,
        "domain": json.dumps(parsed_domain),
        "read_right": _to_bool(read),
        "create_right": _to_bool(create),
        "write_right": _to_bool(write),
        "delete_right": _to_bool(delete),
    }

    if existing:
        existing.write(vals)
        rec = existing
    else:
        vals["access_management_id"] = rule.id
        rec = env["rag.mcp.access.domain.ah"].create(vals)

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "model": ir_model.model,
        "domain": rec.domain,
        "rights": {
            "read": rec.read_right,
            "create": rec.create_right,
            "write": rec.write_right,
            "delete": rec.delete_right,
        },
    }


def _format_domain_access(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    r = result["rights"]
    rights = [k for k, v in r.items() if v]
    return "Domain access on %s for rule '%s': domain=%s rights=%s" % (
        result["model"], result["rule_name"], result["domain"], ", ".join(rights)
    )


# ---------------------------------------------------------------------------
# Tool: set_global_restrictions
# ---------------------------------------------------------------------------

def set_global_restrictions(cr, env, rule_id, readonly=None, disable_login=None,
                             disable_debug_mode=None, hide_export=None, hide_import=None,
                             hide_chatter=None, hide_send_mail=None, hide_log_notes=None,
                             hide_schedule_activity=None, hide_spreadsheet=None, hide_add_property=None):
    """Set global restrictions on a rule (affects all models for the rule's users)."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    vals = {}
    if readonly is not None:
        vals["readonly"] = _to_bool(readonly)
    if disable_login is not None:
        vals["disable_login"] = _to_bool(disable_login)
    if disable_debug_mode is not None:
        vals["disable_debug_mode"] = _to_bool(disable_debug_mode)
    if hide_export is not None:
        vals["hide_export"] = _to_bool(hide_export)
    if hide_import is not None:
        vals["hide_import"] = _to_bool(hide_import)
    if hide_chatter is not None:
        vals["hide_chatter"] = _to_bool(hide_chatter)
    if hide_send_mail is not None:
        vals["hide_send_mail"] = _to_bool(hide_send_mail)
    if hide_log_notes is not None:
        vals["hide_log_notes"] = _to_bool(hide_log_notes)
    if hide_schedule_activity is not None:
        vals["hide_schedule_activity"] = _to_bool(hide_schedule_activity)
    if hide_spreadsheet is not None:
        vals["hide_spreadsheet"] = _to_bool(hide_spreadsheet)
    if hide_add_property is not None:
        vals["hide_add_property"] = _to_bool(hide_add_property)

    if vals:
        rule.write(vals)

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "settings": {
            "readonly": rule.readonly,
            "disable_login": rule.disable_login,
            "disable_debug_mode": rule.disable_debug_mode,
            "hide_export": rule.hide_export,
            "hide_import": rule.hide_import,
            "hide_chatter": rule.hide_chatter,
            "hide_send_mail": rule.hide_send_mail,
            "hide_log_notes": rule.hide_log_notes,
            "hide_schedule_activity": rule.hide_schedule_activity,
            "hide_spreadsheet": rule.hide_spreadsheet,
            "hide_add_property": rule.hide_add_property,
        },
    }


def _format_global_restrictions(result):
    active = [k for k, v in result["settings"].items() if v]
    return "Global restrictions on rule '%s' (id=%s): %s" % (
        result["rule_name"], result["rule_id"],
        ", ".join(active) if active else "none"
    )


# ---------------------------------------------------------------------------
# View-catalog helper (shared by discover_view_elements / hide_view_elements)
# ---------------------------------------------------------------------------

def _ensure_view_catalog(env, ir_model):
    """Guarantee that rag.mcp.store.model.nodes has entries for this model.

    Scans the model's views lazily on the first call, using a transient
    rag.mcp.hide.view.nodes record so we don't pollute the DB with orphan scanner
    rows. Safe to call multiple times — `_upsert_node` dedups catalog rows.
    """
    StoreNodes = env["rag.mcp.store.model.nodes"]
    if not StoreNodes.search_count([("model_id", "=", ir_model.id)]):
        scratch = env["rag.mcp.hide.view.nodes"].new({"model_id": ir_model.id})
        scratch._get_button()
    return StoreNodes.search([("model_id", "=", ir_model.id)])


def _serialize_catalog(catalog):
    """Split a rag.mcp.store.model.nodes recordset into buttons/tabs/links dicts."""
    buttons, tabs, links = [], [], []
    for node in catalog:
        entry = {
            "id": node.id,
            "name": node.attribute_name or "",
            "label": node.attribute_string or "",
        }
        if node.node_option == "button":
            entry["is_smart"] = bool(node.is_smart_button)
            entry["button_type"] = node.button_type or ""
            buttons.append(entry)
        elif node.node_option == "page":
            tabs.append(entry)
        elif node.node_option == "link":
            links.append(entry)
    return buttons, tabs, links


# ---------------------------------------------------------------------------
# Tool: discover_view_elements
# ---------------------------------------------------------------------------

def discover_view_elements(cr, env, model):
    """List hideable buttons, tabs/pages, and kanban links on a model.

    Scans the model's form/list/kanban views on first call and caches the
    result in rag.mcp.store.model.nodes. No access rule is modified; use
    hide_view_elements afterwards to actually hide elements.
    """
    ir_model = _find_model(env, model)
    if not ir_model:
        raise ValueError("Model not found: %s" % model)
    if len(ir_model) > 1:
        return {
            "error": "Multiple models found. Use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    catalog = _ensure_view_catalog(env, ir_model)
    buttons, tabs, links = _serialize_catalog(catalog)
    return {
        "model": ir_model.model,
        "model_id": ir_model.id,
        "buttons": buttons,
        "tabs": tabs,
        "links": links,
    }


def _format_discover_view_elements(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    lines = ["Hideable elements on %s:" % result["model"]]
    if result["buttons"]:
        lines.append("")
        lines.append("Buttons (%s):" % len(result["buttons"]))
        for b in result["buttons"]:
            tag = " [smart]" if b.get("is_smart") else ""
            lines.append("  id=%s name='%s' label='%s'%s" % (b["id"], b["name"], b["label"], tag))
    if result["tabs"]:
        lines.append("")
        lines.append("Tabs / Pages (%s):" % len(result["tabs"]))
        for t in result["tabs"]:
            lines.append("  id=%s name='%s' label='%s'" % (t["id"], t["name"], t["label"]))
    if result["links"]:
        lines.append("")
        lines.append("Kanban links (%s):" % len(result["links"]))
        for l in result["links"]:
            lines.append("  id=%s name='%s' label='%s'" % (l["id"], l["name"], l["label"]))
    if not (result["buttons"] or result["tabs"] or result["links"]):
        lines.append("  (none found — the model may not expose any hideable buttons or tabs)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: hide_view_elements
# ---------------------------------------------------------------------------

def hide_view_elements(cr, env, rule_id, model, buttons=None, tabs=None):
    """Hide specific buttons or tabs/pages from a model's views for users in this rule.

    Call discover_view_elements(model) first to list available button/tab ids,
    then pass the ids (or names) here. Calling without buttons/tabs still
    returns discovery data for backward compatibility.
    """
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    ir_model = _find_model(env, model)
    if not ir_model or len(ir_model) > 1:
        if not ir_model:
            raise ValueError("Model not found: %s" % model)
        return {
            "error": "Multiple models found. Use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    StoreNodes = env["rag.mcp.store.model.nodes"]

    # Make sure the catalog is populated before we look things up.
    _ensure_view_catalog(env, ir_model)

    # Find or create rag.mcp.hide.view.nodes record for this (rule, model) pair.
    existing = env["rag.mcp.hide.view.nodes"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
    ], limit=1)

    if not existing:
        existing = env["rag.mcp.hide.view.nodes"].create({
            "access_management_id": rule.id,
            "model_id": ir_model.id,
        })

    # If no buttons/tabs specified, return available ones for discovery
    if not buttons and not tabs:
        available_buttons = StoreNodes.search([
            ("model_id", "=", ir_model.id),
            ("node_option", "=", "button"),
        ])
        available_tabs = StoreNodes.search([
            ("model_id", "=", ir_model.id),
            ("node_option", "=", "page"),
        ])
        return {
            "rule_id": rule.id,
            "model": ir_model.model,
            "mode": "discovery",
            "available_buttons": [{"id": b.id, "name": b.attribute_name, "label": b.attribute_string, "is_smart": b.is_smart_button} for b in available_buttons],
            "available_tabs": [{"id": t.id, "name": t.attribute_name, "label": t.attribute_string} for t in available_tabs],
        }

    # Apply button/tab hiding
    vals = {}
    if buttons:
        buttons = _parse_json_list(buttons, "buttons")
        btn_nodes = StoreNodes.browse()
        for btn in buttons:
            if isinstance(btn, int):
                btn_nodes |= StoreNodes.browse(btn).exists()
            else:
                found = StoreNodes.search([
                    ("model_id", "=", ir_model.id),
                    ("node_option", "=", "button"),
                    "|", ("attribute_name", "=", btn), ("attribute_string", "ilike", btn),
                ], limit=1)
                if found:
                    btn_nodes |= found
        if btn_nodes:
            vals["btn_store_model_nodes_ids"] = [(4, b.id) for b in btn_nodes]

    if tabs:
        tabs = _parse_json_list(tabs, "tabs")
        tab_nodes = StoreNodes.browse()
        for tab in tabs:
            if isinstance(tab, int):
                tab_nodes |= StoreNodes.browse(tab).exists()
            else:
                found = StoreNodes.search([
                    ("model_id", "=", ir_model.id),
                    ("node_option", "=", "page"),
                    "|", ("attribute_name", "=", tab), ("attribute_string", "ilike", tab),
                ], limit=1)
                if found:
                    tab_nodes |= found
        if tab_nodes:
            vals["page_store_model_nodes_ids"] = [(4, t.id) for t in tab_nodes]

    if vals:
        existing.write(vals)

    return {
        "rule_id": rule.id,
        "model": ir_model.model,
        "mode": "applied",
        "hidden_buttons": [{"name": b.attribute_name, "label": b.attribute_string} for b in existing.btn_store_model_nodes_ids],
        "hidden_tabs": [{"name": t.attribute_name, "label": t.attribute_string} for t in existing.page_store_model_nodes_ids],
    }


def _format_hide_view_elements(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    if result["mode"] == "discovery":
        lines = ["Available elements on %s:" % result["model"], ""]
        if result["available_buttons"]:
            lines.append("Buttons:")
            for b in result["available_buttons"]:
                lines.append("  id=%s name='%s' label='%s'%s" % (
                    b["id"], b["name"], b["label"], " [smart]" if b["is_smart"] else ""))
        if result["available_tabs"]:
            lines.append("Tabs/Pages:")
            for t in result["available_tabs"]:
                lines.append("  id=%s name='%s' label='%s'" % (t["id"], t["name"], t["label"]))
        if not result["available_buttons"] and not result["available_tabs"]:
            lines.append("No buttons or tabs found. They may need to be scanned first.")
        return "\n".join(lines)
    else:
        btns = ", ".join(b["label"] or b["name"] for b in result["hidden_buttons"])
        tabs_str = ", ".join(t["label"] or t["name"] for t in result["hidden_tabs"])
        return "Hidden elements on %s: buttons=[%s] tabs=[%s]" % (result["model"], btns, tabs_str)


# ---------------------------------------------------------------------------
# Tool: set_model_chatter
# ---------------------------------------------------------------------------

def set_model_chatter(cr, env, rule_id, model, hide_chatter=False, hide_send_mail=False,
                       hide_log_notes=False, hide_schedule_activity=False):
    """Control chatter visibility on a specific model for users in a rule."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    ir_model = _find_model(env, model)
    if not ir_model or len(ir_model) > 1:
        if not ir_model:
            raise ValueError("Model not found: %s" % model)
        return {
            "error": "Multiple models found. Use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    existing = env["rag.mcp.hide.chatter"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
    ], limit=1)

    vals = {
        "model_id": ir_model.id,
        "hide_chatter": _to_bool(hide_chatter),
        "hide_send_mail": _to_bool(hide_send_mail),
        "hide_log_notes": _to_bool(hide_log_notes),
        "hide_schedule_activity": _to_bool(hide_schedule_activity),
    }

    if existing:
        existing.write(vals)
        rec = existing
    else:
        vals["access_management_id"] = rule.id
        rec = env["rag.mcp.hide.chatter"].create(vals)

    return {
        "rule_id": rule.id,
        "model": ir_model.model,
        "hide_chatter": rec.hide_chatter,
        "hide_send_mail": rec.hide_send_mail,
        "hide_log_notes": rec.hide_log_notes,
        "hide_schedule_activity": rec.hide_schedule_activity,
    }


def _format_model_chatter(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    flags = []
    if result["hide_chatter"]:
        flags.append("chatter")
    if result["hide_send_mail"]:
        flags.append("send_mail")
    if result["hide_log_notes"]:
        flags.append("log_notes")
    if result["hide_schedule_activity"]:
        flags.append("schedule_activity")
    return "Chatter settings on %s: hidden=%s" % (result["model"], ", ".join(flags) if flags else "none")


# ---------------------------------------------------------------------------
# Tool: block_model_access
# ---------------------------------------------------------------------------

def block_model_access(cr, env, rule_id, model, block_menus=True):
    """Completely block a model from a user.

    Hard-blocks every record of the target model by writing an
    `rag.mcp.access.domain.ah` entry with read_right=False (which makes
    `ir.rule._compute_domain` return [('id','=',False)] for that model —
    enforced on every read, even from a hand-crafted URL).

    Also writes a `rag.mcp.remove.action` entry flagging the model readonly with
    create/edit/delete restrictions. When `block_menus` is true (default),
    every ir.ui.menu whose action targets this model is also hidden for
    users in the rule (so the module disappears from the navbar)."""
    rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
    if not rule:
        raise ValueError("Access rule with id %s not found" % rule_id)

    ir_model = _find_model(env, model)
    if not ir_model:
        raise ValueError("Model not found: %s" % model)
    if len(ir_model) > 1:
        return {
            "error": "Multiple models found. Please use the technical name.",
            "matches": [{"id": m.id, "model": m.model, "name": m.name} for m in ir_model],
        }
    ir_model = ir_model[0]

    # 1) rag.mcp.access.domain.ah -> ir.rule blocks all records
    domain_existing = env["rag.mcp.access.domain.ah"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
    ], limit=1)
    domain_vals = {
        "model_id": ir_model.id,
        "apply_domain": True,
        "domain": '[["id","=",False]]',
        "read_right": False,
        "create_right": False,
        "write_right": False,
        "delete_right": False,
    }
    if domain_existing:
        domain_existing.write(domain_vals)
    else:
        domain_vals["access_management_id"] = rule.id
        env["rag.mcp.access.domain.ah"].create(domain_vals)

    # 2) rag.mcp.remove.action -> disables CRUD buttons + readonly
    ra_existing = env["rag.mcp.remove.action"].search([
        ("access_management_id", "=", rule.id),
        ("model_id", "=", ir_model.id),
    ], limit=1)
    ra_vals = {
        "model_id": ir_model.id,
        "restrict_create": True,
        "restrict_edit": True,
        "restrict_delete": True,
        "restrict_duplicate": True,
        "restrict_archive_unarchive": True,
        "restrict_export": True,
        "restrict_import": True,
        "readonly": True,
    }
    if ra_existing:
        ra_existing.write(ra_vals)
    else:
        ra_vals["access_management_id"] = rule.id
        env["rag.mcp.remove.action"].create(ra_vals)

    # 3) optional: hide every menu whose action points at this model
    hidden_menu_count = 0
    if _to_bool(block_menus):
        # Find all window actions targeting this model
        actions = env["ir.actions.act_window"].sudo().search([("res_model", "=", ir_model.model)])
        menus = env["ir.ui.menu"].sudo().browse()
        if actions:
            action_refs = ["ir.actions.act_window,%s" % a.id for a in actions]
            menus = env["ir.ui.menu"].sudo().search([("action", "in", action_refs)])
        if menus:
            menu_item_ids = _menu_item_ids_for_menus(env, menus.ids)
            rule.write({"hide_menu_ids": [(4, mid) for mid in menu_item_ids]})
            hidden_menu_count = len(menu_item_ids)

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "model": ir_model.model,
        "model_name": ir_model.name,
        "blocked": True,
        "hidden_menus_for_model": hidden_menu_count,
    }


def _format_block_model_access(result):
    if "error" in result:
        lines = [result["error"]]
        for m in result.get("matches", []):
            lines.append("  - %s (%s)" % (m["name"], m["model"]))
        return "\n".join(lines)
    return "BLOCKED %s (%s) on rule '%s'. Domain, CRUD and %s menu(s) targeting the model are now hidden." % (
        result["model_name"], result["model"], result["rule_name"], result["hidden_menus_for_model"],
    )


# ---------------------------------------------------------------------------
# Tool: list_groups
# ---------------------------------------------------------------------------

def list_groups(cr, env, query="", limit=30):
    """Search res.groups (Odoo security groups) by name, category name or xml id."""
    Groups = env["res.groups"]
    domain = []
    if query:
        domain = ["|", "|",
                  ("name", "ilike", query),
                  ("full_name", "ilike", query),
                  ("category_id.name", "ilike", query)]
    limit = min(int(limit) if limit else 30, 200)
    groups = Groups.search(domain, limit=limit, order="category_id,name")
    return {
        "count": len(groups),
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "full_name": g.full_name,
                "category": g.category_id.name if g.category_id else "",
                "xml_id": (g.get_external_id().get(g.id) or ""),
            }
            for g in groups
        ],
    }


def _format_list_groups(result):
    lines = ["Groups found: %s" % result["count"], ""]
    for g in result["groups"]:
        lines.append("  id=%s | %s%s" % (
            g["id"], g["full_name"] or g["name"],
            (" [%s]" % g["xml_id"]) if g["xml_id"] else "",
        ))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: create_user
# ---------------------------------------------------------------------------

def _resolve_groups(env, groups):
    """Resolve a list of group identifiers (id, xml_id, or name) to res.groups recordset."""
    if not groups:
        return env["res.groups"].browse()
    groups = _parse_json_list(groups, "groups")
    Groups = env["res.groups"].sudo()
    result = Groups.browse()
    for g in groups:
        found = Groups.browse()
        if isinstance(g, int):
            found = Groups.browse(g).exists()
        elif isinstance(g, str):
            if g.isdigit():
                found = Groups.browse(int(g)).exists()
            elif "." in g:
                # xml_id form 'module.group_xxx'
                try:
                    found = env.ref(g, raise_if_not_found=False)
                    if found and found._name != "res.groups":
                        found = Groups.browse()
                except Exception:
                    found = Groups.browse()
            if not found:
                # fall back to name / full_name lookup
                found = Groups.search([
                    "|", ("full_name", "=", g), ("name", "=", g),
                ], limit=1)
            if not found:
                found = Groups.search([
                    "|", ("full_name", "ilike", g), ("name", "ilike", g),
                ], limit=1)
        if not found:
            raise ValueError("Group not found: %s (use list_groups to search)" % g)
        result |= found
    return result


def create_user(cr, env, name, login, email=None, password=None, groups=None,
                company_id=None, rule_id=None, active=True):
    """Create a new res.users.

    Args:
        name: display name.
        login: login/username (usually the email).
        email: optional email (falls back to login).
        password: initial password. If omitted, Odoo sets a random one and
            the user will need the reset-password flow.
        groups: optional list of res.groups identifiers (id, xml_id, or name)
            e.g. ["base.group_user", "Sales / User: Own Documents Only"].
            If empty, user is created with only the Internal User group.
        company_id: optional company id (defaults to current).
        rule_id: optional rag.mcp.access.management rule id to attach the user to.
        active: user active flag.
    """
    User = env["res.users"].sudo()

    # Avoid duplicate login
    existing = User.search([("login", "=", login)], limit=1)
    if existing:
        raise ValueError("A user with login '%s' already exists (id=%s)" % (login, existing.id))

    group_recs = _resolve_groups(env, groups)
    if not group_recs:
        # default to Internal User
        default_group = env.ref("base.group_user", raise_if_not_found=False)
        if default_group:
            group_recs = default_group

    vals = {
        "name": name,
        "login": login,
        "email": email or login,
        "active": _to_bool(active),
    }
    if password:
        vals["password"] = password
    if company_id:
        cid = int(company_id)
        vals["company_id"] = cid
        vals["company_ids"] = [(6, 0, [cid])]
    if group_recs:
        vals["groups_id"] = [(6, 0, group_recs.ids)]

    user = User.create(vals)

    attached_rule = None
    if rule_id:
        rule = env["rag.mcp.access.management"].browse(int(rule_id)).exists()
        if not rule:
            raise ValueError("Access rule with id %s not found" % rule_id)
        rule.write({"user_ids": [(4, user.id)]})
        attached_rule = {"id": rule.id, "name": rule.name}

    return {
        "id": user.id,
        "name": user.name,
        "login": user.login,
        "email": user.email,
        "active": user.active,
        "groups": [{"id": g.id, "name": g.full_name or g.name} for g in user.groups_id],
        "company": {"id": user.company_id.id, "name": user.company_id.name},
        "attached_rule": attached_rule,
        "password_set": bool(password),
    }


def _format_create_user(result):
    lines = [
        "Created user '%s' (login=%s, id=%s)" % (result["name"], result["login"], result["id"]),
        "  email: %s" % result["email"],
        "  company: %s" % result["company"]["name"],
        "  groups: %s" % (", ".join(g["name"] for g in result["groups"]) or "none"),
    ]
    if result["attached_rule"]:
        lines.append("  attached to rule: %s (id=%s)" % (
            result["attached_rule"]["name"], result["attached_rule"]["id"],
        ))
    if not result["password_set"]:
        lines.append("  (no password provided — user must reset via email flow)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _to_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


# ---------------------------------------------------------------------------
# Tool definitions (for MCP protocol tools/list)
# ---------------------------------------------------------------------------

ACCESS_TOOL_DEFINITIONS = [
    {
        "name": "list_access_rules",
        "description": "List all user access management rules. Shows rule name, assigned users, and summary of restrictions (hidden menus, model restrictions, field rules, domain rules). Use this first to see existing rules before creating new ones.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_user_access_summary",
        "description": "Get a complete summary of all access restrictions applied to a specific user. Shows which menus are hidden, which models have CRUD restrictions, field-level rules, domain filters, and global settings. Use a user name, login, or id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user": {"type": "string", "description": "User name, login, or id. Examples: 'John', 'john@example.com', '15'"},
            },
            "required": ["user"],
        },
    },
    {
        "name": "search_users",
        "description": "Search Odoo users by name or login. Use this to find user ids before creating access rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term (name or login). Leave empty to list all users.", "default": ""},
                "limit": {"type": "integer", "default": 20, "description": "Max results"},
            },
        },
    },
    {
        "name": "search_menus",
        "description": "Search Odoo menus (modules/apps). Use parent_only=true to find top-level app menus (Sales, Inventory, Accounting, etc.). Use this to find menu ids before hiding them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Menu name to search. Examples: 'Sales', 'Inventory', 'Accounting'. Leave empty to list all.", "default": ""},
                "parent_only": {"type": "boolean", "default": True, "description": "If true, only return top-level app menus"},
            },
        },
    },
    {
        "name": "create_access_rule",
        "description": "Create a new access management rule. After creation, use other tools to add restrictions (hide_menus, restrict_model_operations, etc.). You can assign users now or later with assign_users_to_rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Rule name, e.g. 'Sales Team Restrictions', 'Warehouse Read-Only'"},
                "users": {"type": "string", "description": "Optional. JSON array of user names, logins, or ids. E.g. '[\"john@example.com\", \"Jane\"]' or '[5, 8]'"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "delete_access_rule",
        "description": "Delete an access management rule by its id. This removes all restrictions defined in the rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id to delete"},
            },
            "required": ["rule_id"],
        },
    },
    {
        "name": "assign_users_to_rule",
        "description": "Add, remove, or set users on an access rule. action='add' adds users, 'remove' removes them, 'set' replaces all users.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "users": {"type": "string", "description": "JSON array of user names, logins, or ids. E.g. '[\"john@example.com\"]' or '[5, 8]'"},
                "action": {"type": "string", "enum": ["add", "remove", "set"], "default": "add", "description": "add=add users, remove=remove users, set=replace all"},
            },
            "required": ["rule_id", "users"],
        },
    },
    {
        "name": "clear_menu_hides",
        "description": "Reset the rule's menu hides — every menu becomes visible again for users attached to this rule. Use for 'user X should see all menus', 'remove all menu restrictions from this rule', 'unhide everything'. Leaves the rule, its users, and any non-menu restrictions untouched.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id to clear menu hides on"},
            },
            "required": ["rule_id"],
        },
    },
    {
        "name": "allow_only_menus",
        "description": "WHITELIST MODE. Hide every menu EXCEPT the ones listed. Perfect for restrictive roles: 'warehouse operator can only see Inventory/Operations/Transfers', 'this user can only access Contacts and CRM'. Accepts menu paths like 'Inventory/Operations/Transfers' (recommended — unambiguous), plain names like 'Contacts' (first match wins), or ids. Ancestors of whitelisted menus stay visible so the user can navigate. By default descendants are kept visible too (pass include_descendants=false to whitelist the exact menu only). This REPLACES the rule's hide_menu_ids — use it for a one-shot 'lock down to X' setup, not to add to existing hides.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "menus": {"type": "string", "description": "JSON array of menu paths, names, or ids. Paths are recommended: '[\"Inventory/Operations/Transfers\", \"Contacts\"]'. Plain names and ids also work: '[\"CRM\", 42]'."},
                "include_descendants": {"type": "boolean", "default": True, "description": "When true (default), every submenu of a whitelisted menu stays visible. Set false to keep only the exact menus listed."},
            },
            "required": ["rule_id", "menus"],
        },
    },
    {
        "name": "hide_menus",
        "description": "Hide or unhide specific menus (modules/apps/submenus) from users in an access rule. BLACKLIST mode — for whitelist mode (hide everything except X), use allow_only_menus. Use search_menus first to find menu names. By default every descendant submenu of the matched menus is also hidden (set include_submenus=false to hide only the exact menus). Examples: hide 'Sales' module, hide 'Inventory > Configuration', hide a specific sub-menu. action='add' hides, 'remove' unhides.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "menus": {"type": "string", "description": "JSON array of menu names or ids. E.g. '[\"Sales\", \"Inventory\"]' or '[5, 12]'"},
                "action": {"type": "string", "enum": ["add", "remove"], "default": "add", "description": "add=hide menus, remove=unhide menus"},
                "include_submenus": {"type": "boolean", "default": True, "description": "If true, also hide every descendant submenu of the matched menus."},
            },
            "required": ["rule_id", "menus"],
        },
    },
    {
        "name": "block_model_access",
        "description": "Completely block a user (rule) from accessing a model — even by typing the URL manually or via API. This writes a read=false domain rule that makes every record invisible, flags the model readonly+no-CRUD, and (by default) hides every menu whose window-action targets the model. Use this whenever the user says things like 'user X should not access the sale module/model', 'block user Y from leads', 'make stock.picking completely inaccessible for Z'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "model": {"type": "string", "description": "Odoo model technical name, e.g. 'sale.order', 'crm.lead', 'stock.picking'"},
                "block_menus": {"type": "boolean", "default": True, "description": "Also hide every menu whose action opens this model."},
            },
            "required": ["rule_id", "model"],
        },
    },
    {
        "name": "list_groups",
        "description": "Search Odoo security groups (res.groups) by name, full name, category or xml_id. Use this to find group identifiers before calling create_user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term. Leave empty to list all.", "default": ""},
                "limit": {"type": "integer", "default": 30, "description": "Max results (capped at 200)."},
            },
        },
    },
    {
        "name": "create_user",
        "description": "Create a new Odoo user (res.users) with the given name/login/password and optionally: assign security groups, pick a company, and attach them to an existing rag.mcp.access.management rule for visibility/CRUD restrictions. To translate natural-language access requests into groups, call list_groups first to discover their xml_ids or names. To apply fine-grained restrictions on top (hide menus, block models, readonly fields, etc.), first create an rag.mcp.access.management rule via create_access_rule, pass its id as rule_id here, and then call the corresponding tools (hide_menus, block_model_access, restrict_model_operations, set_field_access, ...).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name of the user"},
                "login": {"type": "string", "description": "Login (usually the email address)"},
                "email": {"type": "string", "description": "Email (defaults to login)"},
                "password": {"type": "string", "description": "Initial password. If omitted, Odoo sets a random one and the user must reset it."},
                "groups": {"type": "string", "description": "JSON array of group identifiers — ids, xml_ids like 'base.group_user', 'sales_team.group_sale_salesman', or human names. Defaults to Internal User."},
                "company_id": {"type": "integer", "description": "Optional company id (defaults to current)."},
                "rule_id": {"type": "integer", "description": "Optional rag.mcp.access.management rule id to attach the user to."},
                "active": {"type": "boolean", "default": True, "description": "User active flag."},
            },
            "required": ["name", "login"],
        },
    },
    {
        "name": "restrict_model_operations",
        "description": "Set model-level operation restrictions for users in an access rule. Control create, edit, delete, archive, duplicate, export, import on a specific Odoo model. Use model technical names like 'sale.order', 'stock.picking', 'account.move', 'purchase.order'. Set any restriction to true to block that operation, false to allow it. Only specified restrictions are changed; others stay as they were.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "model": {"type": "string", "description": "Odoo model technical name. E.g. 'sale.order', 'stock.picking', 'account.move', 'product.template'"},
                "restrict_create": {"type": "boolean", "description": "Block creating new records"},
                "restrict_edit": {"type": "boolean", "description": "Block editing existing records"},
                "restrict_delete": {"type": "boolean", "description": "Block deleting records"},
                "restrict_archive": {"type": "boolean", "description": "Block archiving/unarchiving records"},
                "restrict_duplicate": {"type": "boolean", "description": "Block duplicating records"},
                "restrict_export": {"type": "boolean", "description": "Block exporting records"},
                "restrict_import": {"type": "boolean", "description": "Block importing records"},
                "readonly": {"type": "boolean", "description": "Make the entire model read-only"},
                "restrict_chatter": {"type": "boolean", "description": "Hide chatter on this model"},
                "restrict_spreadsheet": {"type": "boolean", "description": "Hide spreadsheet on this model"},
            },
            "required": ["rule_id", "model"],
        },
    },
    {
        "name": "set_field_access",
        "description": "Control field-level visibility on a specific model. Make fields invisible (hidden), readonly, or required for users in the rule. Use model technical names and field technical names.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "model": {"type": "string", "description": "Odoo model technical name, e.g. 'sale.order'"},
                "fields": {"type": "string", "description": "JSON array of field technical names. E.g. '[\"amount_total\", \"margin\"]'"},
                "invisible": {"type": "boolean", "default": False, "description": "Hide the fields from the view"},
                "readonly": {"type": "boolean", "default": False, "description": "Make the fields read-only"},
                "required": {"type": "boolean", "default": False, "description": "Make the fields required"},
            },
            "required": ["rule_id", "model", "fields"],
        },
    },
    {
        "name": "set_domain_access",
        "description": "Set domain-based record-level access rules. Controls which records a user can see and what they can do with them (read/create/write/delete). Domain uses Odoo domain syntax, e.g. [['user_id','=',0]] where 0 is replaced by current user id. Set read=false to completely block access to the model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "model": {"type": "string", "description": "Odoo model technical name"},
                "domain": {"type": "string", "default": "[]", "description": "Odoo domain filter as JSON string. E.g. '[[\"user_id\",\"=\",0]]' (0=current user). Use '[[\"id\",\"=\",false]]' to block all records."},
                "read": {"type": "boolean", "default": True, "description": "Allow reading records matching domain"},
                "create": {"type": "boolean", "default": False, "description": "Allow creating records"},
                "write": {"type": "boolean", "default": False, "description": "Allow editing records"},
                "delete": {"type": "boolean", "default": False, "description": "Allow deleting records"},
            },
            "required": ["rule_id", "model"],
        },
    },
    {
        "name": "set_global_restrictions",
        "description": "Set global restrictions that apply across ALL models for users in a rule. Includes: readonly (entire system read-only), disable_login (block login), disable_debug_mode, hide_export, hide_import, hide_chatter, hide_send_mail, hide_log_notes, hide_schedule_activity, hide_spreadsheet, hide_add_property.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "readonly": {"type": "boolean", "description": "Make entire system read-only for users"},
                "disable_login": {"type": "boolean", "description": "Prevent users from logging in"},
                "disable_debug_mode": {"type": "boolean", "description": "Disable developer mode"},
                "hide_export": {"type": "boolean", "description": "Hide export option everywhere"},
                "hide_import": {"type": "boolean", "description": "Hide import option everywhere"},
                "hide_chatter": {"type": "boolean", "description": "Hide chatter globally"},
                "hide_send_mail": {"type": "boolean", "description": "Hide Send Message globally"},
                "hide_log_notes": {"type": "boolean", "description": "Hide Log Notes globally"},
                "hide_schedule_activity": {"type": "boolean", "description": "Hide Schedule Activity globally"},
                "hide_spreadsheet": {"type": "boolean", "description": "Hide spreadsheet globally"},
                "hide_add_property": {"type": "boolean", "description": "Hide Add Property globally"},
            },
            "required": ["rule_id"],
        },
    },
    {
        "name": "discover_view_elements",
        "description": "List every button, notebook tab/page, and kanban link that can be hidden on a model's views. Call this BEFORE hide_view_elements to get the exact ids/names to pass. No rule is modified. Results are cached per model; the first call scans the form/list/kanban views.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Odoo model technical name, e.g. 'sale.order', 'crm.lead'"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "hide_view_elements",
        "description": "Hide specific buttons or tabs/pages from a model's form/list views. Use discover_view_elements(model) first to get button/tab ids, then pass them here. Calling with just model (no buttons/tabs) also returns discovery data for backward compatibility.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "model": {"type": "string", "description": "Odoo model technical name"},
                "buttons": {"type": "string", "description": "Optional. JSON array of button names or ids to hide. E.g. '[\"action_confirm\", \"action_cancel\"]' or '[12, 34]'"},
                "tabs": {"type": "string", "description": "Optional. JSON array of tab/page names or ids to hide. E.g. '[\"order_line\", \"notes\"]'"},
            },
            "required": ["rule_id", "model"],
        },
    },
    {
        "name": "set_model_chatter",
        "description": "Control chatter visibility on a specific model (per-model, not global). Hide entire chatter, or just send_mail/log_notes/schedule_activity buttons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rule_id": {"type": "integer", "description": "The access rule id"},
                "model": {"type": "string", "description": "Odoo model technical name"},
                "hide_chatter": {"type": "boolean", "default": False, "description": "Hide entire chatter"},
                "hide_send_mail": {"type": "boolean", "default": False, "description": "Hide Send Message button"},
                "hide_log_notes": {"type": "boolean", "default": False, "description": "Hide Log Notes button"},
                "hide_schedule_activity": {"type": "boolean", "default": False, "description": "Hide Schedule Activity button"},
            },
            "required": ["rule_id", "model"],
        },
    },
]


# Dispatch map: tool_name -> (handler_function, formatter_function)
ACCESS_DISPATCH = {
    "list_access_rules": (list_access_rules, _format_list_access_rules),
    "get_user_access_summary": (get_user_access_summary, _format_user_access_summary),
    "search_users": (search_users, _format_search_users),
    "search_menus": (search_menus, _format_search_menus),
    "create_access_rule": (create_access_rule, _format_create_access_rule),
    "delete_access_rule": (delete_access_rule, _format_delete_access_rule),
    "assign_users_to_rule": (assign_users_to_rule, _format_assign_users),
    "hide_menus": (hide_menus, _format_hide_menus),
    "allow_only_menus": (allow_only_menus, _format_allow_only_menus),
    "clear_menu_hides": (clear_menu_hides, _format_clear_menu_hides),
    "restrict_model_operations": (restrict_model_operations, _format_restrict_model),
    "set_field_access": (set_field_access, _format_field_access),
    "set_domain_access": (set_domain_access, _format_domain_access),
    "set_global_restrictions": (set_global_restrictions, _format_global_restrictions),
    "discover_view_elements": (discover_view_elements, _format_discover_view_elements),
    "hide_view_elements": (hide_view_elements, _format_hide_view_elements),
    "set_model_chatter": (set_model_chatter, _format_model_chatter),
    "block_model_access": (block_model_access, _format_block_model_access),
    "list_groups": (list_groups, _format_list_groups),
    "create_user": (create_user, _format_create_user),
}

# Write tools that need cr.commit()
ACCESS_WRITE_TOOLS = frozenset({
    "create_access_rule",
    "delete_access_rule",
    "assign_users_to_rule",
    "hide_menus",
    "allow_only_menus",
    "clear_menu_hides",
    "restrict_model_operations",
    "set_field_access",
    "set_domain_access",
    "set_global_restrictions",
    "discover_view_elements",
    "hide_view_elements",
    "set_model_chatter",
    "block_model_access",
    "create_user",
})
