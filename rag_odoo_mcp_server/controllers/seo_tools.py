# -*- coding: utf-8 -*-
"""
MCP tools for on-site SEO of the Odoo Website (optional "SEO Manager" feature).

Gated behind Settings -> RAG Odoo MCP Server -> Optional features -> SEO Manager.
When the flag is off the controller hides these tools from tools/list and refuses
them on tools/call, exactly like the CRM Manager and Access Manager features.

Design notes
------------
* The ``website`` module is NOT a dependency of rag_odoo_mcp_server on purpose:
  it is a heavy frontend app and most instances that use this connector for
  CRM / dashboards do not want it force-installed. Every tool here therefore
  resolves the website models at runtime through ``env.get(...)`` and returns a
  readable "install the Website app first" message when they are missing.

* SEO metadata lives on the ``website.seo.metadata`` abstract mixin
  (website_meta_title / website_meta_description / website_meta_keywords /
  website_meta_og_img / seo_name). Many models inherit it: website.page (through
  its delegated ir.ui.view), blog.post, product.template, event.event,
  event.track, res.partner, helpdesk.team... Rather than hard-coding that list,
  :func:`seo_models` discovers every installed model carrying the mixin fields,
  so the tools keep working on instances with extra website_* apps.

* Content edits are deliberately surgical: only image ``alt`` attributes and the
  heading structure are touched, never the body copy or the snippet markup. The
  previous markup is stashed in ir.config_parameter before each write so
  ``seo_restore_arch_backup`` can undo the last change.

* Records are accessed with ``sudo()``. Reading website.page requires it in
  standard Odoo anyway, robots_txt is restricted to group_website_designer, and
  the feature as a whole is already gated by an administrator-only checkbox.
"""

import json
import logging
import re

from lxml import etree, html as lxml_html

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SEO rules of thumb (2025/2026 practice, Google + Bing)
# ---------------------------------------------------------------------------
# Titles are truncated by pixel width, not character count, but ~60 characters
# is the widely used safe proxy for a ~600px SERP title.
TITLE_MIN = 30
TITLE_MAX = 60
TITLE_HARD_MAX = 65
# Descriptions are not a ranking factor but drive click-through; Google rewrites
# anything much outside this band.
DESC_MIN = 70
DESC_MAX = 160
DESC_HARD_MAX = 320
URL_MAX_LEN = 75
URL_MAX_DEPTH = 4
MIN_WORDS_CONTENT = 300

_SEVERITY_WEIGHT = {"error": 15, "warning": 7, "info": 2}

# Anchor texts that carry no semantic value for crawlers (EN + FR + ES + NL).
_GENERIC_ANCHORS = {
    "click here", "here", "read more", "more", "link", "this link", "learn more",
    "see more", "details", "download",
    "cliquez ici", "ici", "en savoir plus", "lire la suite", "voir plus", "plus",
    "haga clic aqui", "leer mas", "ver mas",
    "lees meer", "klik hier",
}

# ir.ui.view is the delegated backing model of website.page: auditing it directly
# would report every QWeb template in the database, so pages are audited through
# website.page instead.
_SEO_MODEL_BLACKLIST = {"ir.ui.view"}

# Nicer, stable ordering for the models an audit walks through.
_SEO_MODEL_PRIORITY = [
    "website.page",
    "blog.post",
    "product.template",
    "event.event",
    "event.track",
    "blog.blog",
    "blog.tag",
    "helpdesk.team",
    "res.partner",
]

# Editable markup fields, in the order we look for them on a record.
# 'arch' is XML (QWeb) and must round-trip through the XML parser; the rest are
# HTML fields and round-trip through the HTML parser.
_HTML_FIELD_CANDIDATES = (
    "arch",                    # website.page (delegated to ir.ui.view)
    "content",                 # blog.post
    "description_ecommerce",   # product.template (Odoo 17+)
    "website_description",     # product.template (older) / event.event
    "description_sale",
    "body_html",
    "description",
)

_ARCH_BACKUP_PREFIX = "rag_odoo_mcp_server.seo_arch_backup."
# ir.config_parameter values are unlimited text, but a runaway page should not
# balloon the parameter table; anything larger simply is not backed up and the
# tool says so instead of silently pretending an undo exists.
_ARCH_BACKUP_MAX_CHARS = 400000

_WEBSITE_MISSING_MSG = (
    "This tool needs Odoo's Website app, which is not installed on this database. "
    "Tell the user: 'The SEO tools need the Website app. Install it from Apps "
    "(technical name: website), then ask me again.' Do not try to install it "
    "yourself and do not fall back to odoo_write on website models — they do not "
    "exist here."
)


# ---------------------------------------------------------------------------
# Argument coercion — MCP clients often send everything as strings
# ---------------------------------------------------------------------------

def _as_int(value, name, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError("'%s' must be an integer, got a boolean" % name)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("'%s' must be an integer, got %r" % (name, value))


def _as_bool(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "y", "on")


def _as_list(value, name):
    """Coerce None / list / scalar / JSON string into a list."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped[0] in "[{":
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Invalid JSON for '%s': %s. Example: '[{\"src_contains\": \"hero\", "
                    "\"alt\": \"Blue ceramic vase\"}]'" % (name, exc)
                )
            return parsed if isinstance(parsed, list) else [parsed]
        return [stripped]
    raise ValueError("'%s' must be a list or JSON string, got %s" % (name, type(value).__name__))


def _as_dict(value, name):
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON object for '%s': %s" % (name, exc))
        if not isinstance(parsed, dict):
            raise ValueError("'%s' must decode to a JSON object" % name)
        return parsed
    raise ValueError("'%s' must be an object or JSON string, got %s" % (name, type(value).__name__))


def _format_json(data):
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Website / model resolution
# ---------------------------------------------------------------------------

def _require_website(env):
    """Return the (sudo) website model, or raise a message the LLM can relay."""
    model = env.get("website")
    if model is None:
        raise ValueError(_WEBSITE_MISSING_MSG)
    return model.sudo()


def _websites(env, website_id=None):
    Website = _require_website(env)
    wid = _as_int(website_id, "website_id")
    if wid:
        site = Website.browse(wid).exists()
        if not site:
            raise ValueError("No website with id=%s. Call seo_get_overview to list websites." % wid)
        return site
    return Website.search([])


def seo_models(env):
    """Every installed, concrete model that carries the website.seo.metadata fields.

    Returns an ordered dict {model_name: description}. Discovery is dynamic so
    the tools automatically cover website_sale, website_blog, website_event and
    any third-party app that inherits the mixin.
    """
    try:
        candidates = list(env.registry.models.keys())
    except Exception:  # pragma: no cover - defensive, registry internals
        candidates = env["ir.model"].sudo().search([]).mapped("model")

    found = {}
    for name in candidates:
        if name in _SEO_MODEL_BLACKLIST:
            continue
        try:
            model = env.get(name)
        except Exception:
            continue
        if model is None or model._abstract or model._transient:
            continue
        if "website_meta_title" not in model._fields:
            continue
        found[name] = model._description or name

    ordered = {}
    for name in _SEO_MODEL_PRIORITY:
        if name in found:
            ordered[name] = found.pop(name)
    for name in sorted(found):
        ordered[name] = found[name]
    return ordered


def _check_seo_model(env, model):
    model = (model or "").strip()
    if not model:
        raise ValueError("'model' is required. Call seo_get_overview to see the SEO-capable models.")
    available = seo_models(env)
    if model not in available:
        raise ValueError(
            "'%s' has no SEO metadata fields on this database. SEO-capable models here: %s"
            % (model, ", ".join(available) or "(none — is the Website app installed?)")
        )
    return env[model].sudo()


def _resolve_record(env, model=None, res_id=None, url=None, website_id=None):
    """Locate one record either by (model, res_id) or by public URL."""
    if model and res_id not in (None, ""):
        Model = _check_seo_model(env, model)
        rec = Model.browse(_as_int(res_id, "res_id")).exists()
        if not rec:
            raise ValueError("No %s record with id=%s." % (model, res_id))
        return rec

    if url:
        url = "/" + url.strip().lstrip("/")
        Page = env.get("website.page")
        if Page is None:
            raise ValueError(_WEBSITE_MISSING_MSG)
        domain = [("url", "=", url)]
        wid = _as_int(website_id, "website_id")
        if wid:
            domain.append(("website_id", "in", [wid, False]))
        page = Page.sudo().search(domain, limit=1)
        if page:
            return page
        # Fall back to any SEO model exposing that public URL.
        for name in seo_models(env):
            Model = env[name].sudo()
            if "website_url" not in Model._fields:
                continue
            try:
                match = Model.search([], limit=500).filtered(lambda r: _record_url(r) == url)
            except Exception:
                continue
            if match:
                return match[0]
        raise ValueError(
            "No page or record found at URL '%s'. Call seo_audit to list the known URLs." % url
        )

    raise ValueError("Provide either (model + res_id) or url.")


def _record_url(rec):
    for field in ("website_url", "url"):
        if field in rec._fields:
            try:
                value = rec[field]
            except Exception:
                continue
            if value and value != "#":
                return value
    return ""


def _record_label(rec):
    for field in ("name", "display_name"):
        if field in rec._fields:
            try:
                value = rec[field]
            except Exception:
                continue
            if value:
                return value
    return "%s,%s" % (rec._name, rec.id)


def _is_published(rec):
    for field in ("is_published", "website_published", "active"):
        if field in rec._fields:
            try:
                return bool(rec[field])
            except Exception:
                continue
    return True


# ---------------------------------------------------------------------------
# Markup parsing / analysis
# ---------------------------------------------------------------------------

def _editable_field(rec):
    """Return (field_name, kind) of the markup field to analyse/edit, or (None, None)."""
    for field in _HTML_FIELD_CANDIDATES:
        if field in rec._fields:
            try:
                value = rec[field]
            except Exception:
                continue
            if value:
                return field, ("xml" if field == "arch" else "html")
    return None, None


def _load_markup(rec):
    """Return (field, kind, raw). Never raises for an empty/unknown record."""
    field, kind = _editable_field(rec)
    if not field:
        return None, None, ""
    return field, kind, str(rec[field] or "")


def _parse_for_analysis(raw):
    """Lenient parse used for read-only analysis (the tree may be mutated freely)."""
    if not raw or not raw.strip():
        return None
    try:
        root = lxml_html.fromstring(raw)
    except Exception:
        try:
            root = lxml_html.fragment_fromstring(raw, create_parent="div")
        except Exception:
            return None
    for bad in root.xpath(".//script | .//style"):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)
    return root


def _parse_for_edit(raw, kind):
    """Strict, round-trip-safe parse used before writing markup back."""
    if kind == "xml":
        parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
        return etree.fromstring(raw.encode("utf-8"), parser=parser)
    return lxml_html.fragment_fromstring(raw, create_parent="div")


def _dump_after_edit(root, kind):
    if kind == "xml":
        return etree.tostring(root, encoding="unicode")
    # Serialize the children only, dropping the synthetic wrapper div.
    out = root.text or ""
    for child in root:
        out += lxml_html.tostring(child, encoding="unicode")
    return out


def _visible_text(root):
    if root is None:
        return ""
    text = root.text_content() if hasattr(root, "text_content") else "".join(root.itertext())
    return re.sub(r"\s+", " ", text or "").strip()


def _iter_tag(root, tag):
    """Iterate elements by tag name, tolerating namespaces and comments."""
    for el in root.iter():
        name = el.tag
        if not isinstance(name, str):
            continue
        if "}" in name:
            name = name.rsplit("}", 1)[1]
        if name.lower() == tag:
            yield el


def _analyze_markup(raw):
    """Content-side SEO signals extracted from a page's markup."""
    root = _parse_for_analysis(raw)
    if root is None:
        return {
            "parsed": False,
            "word_count": 0,
            "headings": {},
            "h1_texts": [],
            "images": {"total": 0, "missing_alt": 0, "empty_alt": 0, "samples": []},
            "links": {"internal": 0, "external": 0, "external_without_rel": 0, "generic_anchors": []},
        }

    text = _visible_text(root)
    words = [w for w in re.split(r"\s+", text) if w]

    headings = {}
    h1_texts = []
    heading_sequence = []
    for level in range(1, 7):
        tag = "h%d" % level
        texts = []
        for el in _iter_tag(root, tag):
            value = re.sub(r"\s+", " ", (el.text_content() or "")).strip()
            texts.append(value)
            heading_sequence.append(level)
        if texts:
            headings[tag] = texts
        if level == 1:
            h1_texts = texts

    images = {"total": 0, "missing_alt": 0, "empty_alt": 0, "samples": []}
    for el in _iter_tag(root, "img"):
        images["total"] += 1
        src = (el.get("src") or el.get("data-src") or "").strip()
        if "alt" not in el.attrib:
            images["missing_alt"] += 1
            state = "missing"
        elif not (el.get("alt") or "").strip():
            images["empty_alt"] += 1
            state = "empty"
        else:
            state = "ok"
        if state != "ok" and len(images["samples"]) < 20:
            images["samples"].append({"src": src[:200], "alt": state})

    links = {"internal": 0, "external": 0, "external_without_rel": 0, "generic_anchors": []}
    for el in _iter_tag(root, "a"):
        href = (el.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if href.startswith(("http://", "https://", "//")):
            links["external"] += 1
            rel = (el.get("rel") or "").lower()
            if "nofollow" not in rel and "noopener" not in rel:
                links["external_without_rel"] += 1
        else:
            links["internal"] += 1
        anchor = re.sub(r"\s+", " ", (el.text_content() or "")).strip().lower().rstrip(" .!:>")
        if anchor in _GENERIC_ANCHORS and anchor not in links["generic_anchors"]:
            links["generic_anchors"].append(anchor)

    # Heading hierarchy: report the first skipped level (h1 -> h3).
    skipped = None
    previous = None
    for level in heading_sequence:
        if previous is not None and level > previous + 1:
            skipped = "h%d -> h%d" % (previous, level)
            break
        previous = level

    return {
        "parsed": True,
        "word_count": len(words),
        "headings": headings,
        "h1_texts": h1_texts,
        "heading_skip": skipped,
        "images": images,
        "links": links,
        "text_preview": text[:400],
    }


# ---------------------------------------------------------------------------
# Auditing
# ---------------------------------------------------------------------------

def _issue(code, severity, message, fix):
    return {"code": code, "severity": severity, "message": message, "fix": fix}


def _score_from_issues(issues):
    score = 100
    for issue in issues:
        score -= _SEVERITY_WEIGHT.get(issue["severity"], 5)
    return max(score, 0)


def _grade(score):
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _audit_meta(rec, has_default_social_image):
    """Metadata-side issues for a single record."""
    issues = []
    title = (rec.website_meta_title or "").strip()
    desc = (rec.website_meta_description or "").strip()
    keywords = (rec.website_meta_keywords or "").strip()
    og_img = (rec.website_meta_og_img or "").strip()

    if not title:
        issues.append(_issue(
            "meta_title_missing", "error",
            "No meta title: Google falls back to the page's <h1> or the site name, which rarely "
            "matches search intent.",
            "seo_update_meta with a %d-%d character title starting with the primary keyword."
            % (TITLE_MIN, TITLE_MAX),
        ))
    else:
        if len(title) < TITLE_MIN:
            issues.append(_issue(
                "meta_title_short", "warning",
                "Meta title is only %d characters — wasted SERP real estate." % len(title),
                "Extend to %d-%d characters, e.g. 'Primary keyword | Benefit | Brand'." % (TITLE_MIN, TITLE_MAX),
            ))
        elif len(title) > TITLE_HARD_MAX:
            issues.append(_issue(
                "meta_title_long", "warning",
                "Meta title is %d characters and will be truncated in results." % len(title),
                "Trim to %d characters or fewer, keeping the keyword first." % TITLE_MAX,
            ))

    if not desc:
        issues.append(_issue(
            "meta_description_missing", "error",
            "No meta description: Google auto-generates a snippet, costing click-through rate.",
            "seo_update_meta with a %d-%d character description containing the keyword and a call to action."
            % (DESC_MIN, DESC_MAX),
        ))
    else:
        if len(desc) < DESC_MIN:
            issues.append(_issue(
                "meta_description_short", "warning",
                "Meta description is only %d characters." % len(desc),
                "Extend to %d-%d characters." % (DESC_MIN, DESC_MAX),
            ))
        elif len(desc) > DESC_HARD_MAX:
            issues.append(_issue(
                "meta_description_long", "warning",
                "Meta description is %d characters and will be cut off." % len(desc),
                "Trim to %d characters or fewer." % DESC_MAX,
            ))

    if not keywords:
        issues.append(_issue(
            "meta_keywords_missing", "info",
            "No meta keywords. Google has ignored this tag since 2009, but Odoo's own "
            "'SEO optimized' indicator requires it, so the page shows as unoptimized in the backend.",
            "Optional. Set 2-5 keywords with seo_update_meta if the user wants Odoo's indicator green.",
        ))

    if not og_img and not has_default_social_image:
        issues.append(_issue(
            "og_image_missing", "warning",
            "No OpenGraph image on the record and no site-wide default social image: links shared "
            "on LinkedIn/Facebook/X render without a preview.",
            "Set website_meta_og_img with seo_update_meta, or set a site-wide default via "
            "seo_update_website_settings.",
        ))
    return issues


def _audit_url(url):
    issues = []
    if not url:
        return issues
    path = url.split("?")[0].split("#")[0]
    if path.lower() != path:
        issues.append(_issue(
            "url_uppercase", "warning",
            "URL '%s' contains uppercase characters; crawlers treat /Page and /page as two URLs." % path,
            "Rename with seo_set_page_url (it creates the 301 redirect automatically).",
        ))
    if "_" in path:
        issues.append(_issue(
            "url_underscores", "info",
            "URL '%s' uses underscores; Google treats hyphens, not underscores, as word separators." % path,
            "Rename with seo_set_page_url using hyphens.",
        ))
    if len(path) > URL_MAX_LEN:
        issues.append(_issue(
            "url_long", "info",
            "URL is %d characters long." % len(path),
            "Shorten to under %d characters with seo_set_page_url." % URL_MAX_LEN,
        ))
    depth = len([seg for seg in path.split("/") if seg])
    if depth > URL_MAX_DEPTH:
        issues.append(_issue(
            "url_deep", "info",
            "URL is %d levels deep; deep pages receive less internal link equity." % depth,
            "Flatten the path with seo_set_page_url if the page matters for search.",
        ))
    return issues


def _audit_indexing(rec):
    issues = []
    if "website_indexed" in rec._fields and not rec.website_indexed:
        issues.append(_issue(
            "not_indexed", "error",
            "'Indexed' is off: Odoo excludes this page from sitemap.xml and renders "
            "<meta name=\"robots\" content=\"noindex\">, so it cannot rank at all.",
            "Turn it on with seo_set_indexing — unless the page is intentionally private "
            "(thank-you page, internal landing page).",
        ))
    if not _is_published(rec):
        issues.append(_issue(
            "not_published", "warning",
            "Record is not published: anonymous visitors and crawlers get a 404.",
            "Publish it with seo_set_indexing(is_published=true) once the content is ready.",
        ))
    return issues


def _audit_content(analysis, url):
    issues = []
    if not analysis.get("parsed"):
        return issues

    h1_count = len(analysis.get("h1_texts") or [])
    if h1_count == 0:
        issues.append(_issue(
            "h1_missing", "error",
            "No <h1> on the page: the strongest on-page relevance signal is absent.",
            "Add one with seo_fix_headings(h1_text=...) — it promotes the first heading or "
            "inserts an h1 at the top of the content.",
        ))
    elif h1_count > 1:
        issues.append(_issue(
            "h1_multiple", "warning",
            "%d <h1> elements found (%s): the page topic is ambiguous."
            % (h1_count, ", ".join(t[:40] for t in analysis["h1_texts"][:3])),
            "Keep one and demote the rest with seo_fix_headings(demote_extra_h1=true).",
        ))

    if analysis.get("heading_skip"):
        issues.append(_issue(
            "heading_hierarchy", "info",
            "Heading levels skip (%s), which breaks the document outline for crawlers and screen readers."
            % analysis["heading_skip"],
            "Re-level the intermediate headings in the website editor.",
        ))

    words = analysis.get("word_count", 0)
    if words < MIN_WORDS_CONTENT:
        issues.append(_issue(
            "thin_content", "warning",
            "Only %d words of visible text (thin content threshold: %d)." % (words, MIN_WORDS_CONTENT),
            "Expand the copy, or accept it if this is a contact/legal page that does not target search.",
        ))

    images = analysis.get("images") or {}
    missing = images.get("missing_alt", 0) + images.get("empty_alt", 0)
    if missing:
        issues.append(_issue(
            "images_without_alt", "warning",
            "%d of %d images have no alt text: they are invisible to Google Images and to screen readers."
            % (missing, images.get("total", 0)),
            "Fix with seo_set_image_alt — describe the image, do not stuff keywords.",
        ))

    links = analysis.get("links") or {}
    if links.get("internal", 0) == 0 and url not in ("/", ""):
        issues.append(_issue(
            "no_internal_links", "info",
            "No internal links: the page is a dead end for crawlers and passes no link equity.",
            "Add 2-3 contextual links to related pages in the website editor.",
        ))
    if links.get("generic_anchors"):
        issues.append(_issue(
            "generic_anchor_text", "info",
            "Non-descriptive anchor text used: %s." % ", ".join(links["generic_anchors"][:5]),
            "Replace with keyword-bearing anchors describing the destination.",
        ))
    if links.get("external_without_rel"):
        issues.append(_issue(
            "external_links_no_rel", "info",
            "%d external links carry no rel attribute." % links["external_without_rel"],
            "Add rel=\"noopener\" (security) and rel=\"nofollow\"/\"sponsored\" on paid or untrusted links.",
        ))
    return issues


def _audit_record(rec, has_default_social_image, include_content=True):
    url = _record_url(rec)
    issues = []
    issues += _audit_meta(rec, has_default_social_image)
    issues += _audit_url(url)
    issues += _audit_indexing(rec)

    analysis = None
    if include_content:
        _field, _kind, raw = _load_markup(rec)
        if raw:
            analysis = _analyze_markup(raw)
            issues += _audit_content(analysis, url)

    score = _score_from_issues(issues)
    result = {
        "model": rec._name,
        "id": rec.id,
        "name": _record_label(rec),
        "url": url,
        "score": score,
        "grade": _grade(score),
        "meta_title": rec.website_meta_title or "",
        "meta_title_length": len((rec.website_meta_title or "").strip()),
        "meta_description": rec.website_meta_description or "",
        "meta_description_length": len((rec.website_meta_description or "").strip()),
        "indexed": bool(rec.website_indexed) if "website_indexed" in rec._fields else None,
        "published": _is_published(rec),
        "issues": issues,
    }
    if analysis:
        result["content"] = {
            "word_count": analysis["word_count"],
            "h1": analysis["h1_texts"],
            "heading_counts": {k: len(v) for k, v in (analysis.get("headings") or {}).items()},
            "images": analysis["images"],
            "links": analysis["links"],
        }
    return result


def _audit_website_config(site):
    """Site-wide configuration issues — these outrank any per-page fix."""
    issues = []
    domain = (site.domain or "").strip()
    if not domain:
        issues.append(_issue(
            "website_domain_missing", "warning",
            "Website Domain is empty. Odoo then builds canonical URLs, og:url and the robots.txt "
            "Sitemap line from whatever host the request arrived on, so the same page can be "
            "indexed under several hostnames.",
            "Set it with seo_update_website_settings(domain='https://www.example.com').",
        ))
    else:
        if not domain.startswith("https://"):
            issues.append(_issue(
                "website_domain_not_https", "warning",
                "Website Domain '%s' is not https. HTTPS is a confirmed (light) ranking signal and "
                "browsers flag http pages as not secure." % domain,
                "Switch to https:// with seo_update_website_settings once the certificate is in place.",
            ))
        issues.append(_issue(
            "website_domain_must_match", "info",
            "Website Domain is '%s'. Odoo serves 'Disallow: /' in robots.txt for every request whose "
            "host does not match it — a mismatch silently de-indexes the entire site." % domain,
            "Verify the live site is actually served on this exact host (scheme and www included).",
        ))

    if not (site.google_search_console or "").strip():
        issues.append(_issue(
            "search_console_missing", "info",
            "No Google Search Console key: indexing errors, coverage and query data are not available.",
            "Add the verification key with seo_update_website_settings(google_search_console=...).",
        ))

    if not site.has_social_default_image:
        issues.append(_issue(
            "social_default_image_missing", "info",
            "No default social share image: pages without their own OG image fall back to the site logo, "
            "which usually crops badly.",
            "Upload a 1200x630 image as the website's Default Social Share Image.",
        ))

    robots = re.sub(r"<[^>]+>", " ", site.robots_txt or "")
    if re.search(r"(?mi)^\s*Disallow:\s*/\s*$", robots):
        issues.append(_issue(
            "robots_disallow_all", "error",
            "The custom robots.txt content contains 'Disallow: /', which blocks the whole site from "
            "every crawler.",
            "Remove that line with seo_set_robots unless the site is deliberately hidden.",
        ))

    if len(site.language_ids) > 1:
        issues.append(_issue(
            "multilang_site", "info",
            "%d languages are active. Odoo emits hreflang alternates automatically, but each "
            "translation needs its own translated meta title and description." % len(site.language_ids),
            "Use seo_update_meta with the 'lang' argument (e.g. lang='fr_FR') per language.",
        ))
    return issues


# ---------------------------------------------------------------------------
# Tools — discovery
# ---------------------------------------------------------------------------

def seo_help(cr, env):
    """Static rulebook the assistant should read before its first SEO action."""
    return """== Odoo Website SEO — RULES (read before acting) ==

You are connected to an Odoo 18 instance through the RAG Odoo MCP server, with the
SEO Manager feature enabled. You can audit and improve the on-site SEO of the Odoo
Website app. You CANNOT see Google Search Console data, backlinks, rankings or
traffic — never pretend otherwise. Everything you report must come from a tool call.

## MANDATORY WORKFLOW
1. `seo_get_overview`      -> which websites exist, their config, which models carry SEO
                              metadata, and the site-wide problems. ALWAYS FIRST.
2. `seo_audit`             -> scored list of pages/products/posts with concrete issues.
3. `seo_get_page`          -> deep dive on one URL before you change it.
4. Propose the changes to the user, THEN write with the tools below.

Fix site-wide problems (step 1) before per-page ones: a wrong Website Domain or a
'Disallow: /' in robots.txt makes every per-page improvement worthless.

## WHAT ODOO DOES FOR YOU (do not reinvent it)
- sitemap.xml is generated automatically from published + indexed records and cached
  for 12 hours. `seo_refresh_sitemap` clears that cache; there is no manual sitemap.
- robots.txt is auto-generated (User-agent + Sitemap line). `seo_set_robots` only sets
  the CUSTOM part appended below it.
- hreflang alternates for multi-language sites are emitted automatically.
- Canonical tags are emitted automatically from the Website Domain.
- Turning 'Indexed' off both removes the page from sitemap.xml and adds meta noindex.

## SEO RULES YOU MUST APPLY WHEN WRITING METADATA
- Meta title: %d-%d characters. Primary keyword first, brand last, unique per page.
  Never duplicate a title across pages — duplicates are reported by seo_audit.
- Meta description: %d-%d characters. Include the keyword and a reason to click.
  It is not a ranking factor; it is a click-through factor. Write for humans.
- Meta keywords: ignored by Google since 2009. Odoo's "SEO optimized" flag still
  requires them, so set 2-5 only if the user wants that indicator green. Say so.
- URLs: lowercase, hyphen-separated, short, shallow. ALWAYS let `seo_set_page_url`
  create the 301 redirect — renaming a URL without one destroys its accumulated
  ranking.
- One <h1> per page, matching the search intent of the meta title (not identical).
- Every meaningful image needs descriptive alt text. Describe the image; do not
  stuff keywords. Decorative images may keep alt="".
- Never invent facts about the business to fill a description. If you do not know
  what the page sells, call `seo_get_page` and read the actual content first.

## WRITE TOOLS
  seo_update_meta / seo_bulk_update_meta   titles, descriptions, keywords, OG image, slug
  seo_set_page_url                         rename a URL (+ automatic 301)
  seo_set_indexing                         indexed / published flags
  seo_set_image_alt                        alt text on images (surgical markup edit)
  seo_fix_headings                         enforce exactly one <h1> (surgical markup edit)
  seo_restore_arch_backup                  undo the last markup edit on a record
  seo_create_redirect / seo_delete_redirect / seo_list_redirects
  seo_set_robots                           custom robots.txt block
  seo_refresh_sitemap                      invalidate the sitemap cache
  seo_update_website_settings              domain, Search Console, Analytics, socials

## SAFETY
- `seo_set_image_alt` and `seo_fix_headings` are the ONLY tools that touch page markup,
  and they only change alt attributes / heading tags. They never rewrite body copy.
  Each one stores a backup first; `seo_restore_arch_backup` undoes the last edit.
- Bulk metadata writes: confirm the list with the user before running
  `seo_bulk_update_meta` on more than ~10 records.
- Multi-language: metadata fields are translatable. Pass `lang` to write the
  translation instead of overwriting the source language.
""" % (TITLE_MIN, TITLE_MAX, DESC_MIN, DESC_MAX)


def seo_get_overview(cr, env, website_id=None):
    """Site-wide SEO snapshot: websites, configuration, SEO-capable models, coverage."""
    sites = _websites(env, website_id)
    models_map = seo_models(env)

    websites = []
    for site in sites:
        config_issues = _audit_website_config(site)
        robots_custom = re.sub(r"<[^>]+>", "", site.robots_txt or "").strip()
        websites.append({
            "id": site.id,
            "name": site.name,
            "domain": site.domain or "",
            "default_lang": site.default_lang_id.code if site.default_lang_id else "",
            "languages": site.language_ids.mapped("code"),
            "google_search_console": bool((site.google_search_console or "").strip()),
            "google_analytics_key": bool((site.google_analytics_key or "").strip()),
            "has_default_social_image": bool(site.has_social_default_image),
            "cdn_activated": bool(site.cdn_activated),
            "custom_robots_txt": robots_custom[:2000],
            "social_accounts": {
                key: bool(site[key])
                for key in (
                    "social_twitter", "social_facebook", "social_linkedin",
                    "social_instagram", "social_youtube", "social_tiktok", "social_github",
                )
                if key in site._fields
            },
            "config_issues": config_issues,
            "config_score": _score_from_issues(config_issues),
        })

    coverage = []
    for model_name, description in models_map.items():
        Model = env[model_name].sudo()
        try:
            total = Model.search_count([])
            optimized = Model.search_count([
                ("website_meta_title", "!=", False),
                ("website_meta_description", "!=", False),
            ])
        except Exception as exc:  # pragma: no cover - unusual ACL/domain failures
            _logger.warning("SEO coverage failed for %s: %s", model_name, exc)
            continue
        coverage.append({
            "model": model_name,
            "description": description,
            "records": total,
            "with_title_and_description": optimized,
            "missing_metadata": max(total - optimized, 0),
            "coverage_pct": round(100.0 * optimized / total, 1) if total else 0.0,
        })

    Rewrite = env.get("website.rewrite")
    redirects = Rewrite.sudo().search_count([]) if Rewrite is not None else 0

    sitemaps = env["ir.attachment"].sudo().search_read(
        [("type", "=", "binary"), ("url", "=like", "/sitemap-%")],
        ["url", "create_date"],
        limit=20,
    )

    return {
        "websites": websites,
        "seo_models": coverage,
        "redirect_count": redirects,
        "cached_sitemaps": sitemaps,
        "next_steps": (
            "Fix the config_issues first (they affect every page), then call seo_audit "
            "on the model with the lowest coverage_pct."
        ),
    }


def seo_audit(cr, env, website_id=None, model=None, limit=50, offset=0,
              only_problems=True, include_content_checks=True, max_score=None):
    """Score SEO-capable records and report actionable issues, worst first."""
    limit = min(max(_as_int(limit, "limit", 50) or 50, 1), 200)
    offset = max(_as_int(offset, "offset", 0) or 0, 0)
    only_problems = _as_bool(only_problems, True)
    include_content_checks = _as_bool(include_content_checks, True)
    max_score = _as_int(max_score, "max_score")

    models_map = seo_models(env)
    if model:
        _check_seo_model(env, model)
        target_models = [model]
    else:
        target_models = [name for name in ("website.page", "blog.post", "product.template")
                         if name in models_map] or list(models_map)[:1]
    if not target_models:
        raise ValueError(_WEBSITE_MISSING_MSG)

    sites = _websites(env, website_id)
    has_default_social_image = any(site.has_social_default_image for site in sites)
    wid = _as_int(website_id, "website_id")

    audited = []
    for model_name in target_models:
        Model = env[model_name].sudo()
        domain = []
        if wid and "website_id" in Model._fields:
            domain.append(("website_id", "in", [wid, False]))
        try:
            records = Model.search(domain, limit=limit, offset=offset)
        except Exception as exc:
            _logger.warning("SEO audit could not read %s: %s", model_name, exc)
            continue
        for rec in records:
            try:
                audited.append(_audit_record(rec, has_default_social_image, include_content_checks))
            except Exception as exc:  # one bad record must not kill the audit
                _logger.warning("SEO audit failed on %s,%s: %s", model_name, rec.id, exc)

    # Cross-page duplicate detection — only meaningful across the audited set.
    by_title = {}
    by_desc = {}
    for row in audited:
        title = (row["meta_title"] or "").strip().lower()
        desc = (row["meta_description"] or "").strip().lower()
        if title:
            by_title.setdefault(title, []).append(row)
        if desc:
            by_desc.setdefault(desc, []).append(row)
    for title, rows in by_title.items():
        if len(rows) > 1:
            others = ", ".join(r["url"] or "%s,%s" % (r["model"], r["id"]) for r in rows[:5])
            for row in rows:
                row["issues"].append(_issue(
                    "duplicate_meta_title", "warning",
                    "Meta title is shared by %d pages (%s): they compete with each other and Google "
                    "picks one." % (len(rows), others),
                    "Give each page a unique title with seo_update_meta.",
                ))
    for desc, rows in by_desc.items():
        if len(rows) > 1:
            for row in rows:
                row["issues"].append(_issue(
                    "duplicate_meta_description", "warning",
                    "Meta description is shared by %d pages." % len(rows),
                    "Write a distinct description per page with seo_update_meta.",
                ))
    for row in audited:
        row["score"] = _score_from_issues(row["issues"])
        row["grade"] = _grade(row["score"])
        row["issue_count"] = len(row["issues"])

    results = audited
    if only_problems:
        results = [r for r in results if r["issues"]]
    if max_score is not None:
        results = [r for r in results if r["score"] <= max_score]
    results.sort(key=lambda r: (r["score"], r["url"]))

    severity_totals = {"error": 0, "warning": 0, "info": 0}
    for row in audited:
        for issue in row["issues"]:
            severity_totals[issue["severity"]] = severity_totals.get(issue["severity"], 0) + 1

    return {
        "audited_models": target_models,
        "records_scanned": len(audited),
        "records_reported": len(results),
        "average_score": round(sum(r["score"] for r in audited) / len(audited), 1) if audited else 0,
        "issue_totals": severity_totals,
        "results": results,
        "next_steps": (
            "Work top-down (lowest score first). Show the user the proposed titles and "
            "descriptions before writing them with seo_update_meta or seo_bulk_update_meta."
        ),
    }


def seo_get_page(cr, env, model=None, res_id=None, url=None, website_id=None):
    """Full SEO snapshot of a single page/record, including content analysis."""
    rec = _resolve_record(env, model, res_id, url, website_id)
    sites = _websites(env, website_id)
    has_default_social_image = any(site.has_social_default_image for site in sites)

    report = _audit_record(rec, has_default_social_image, include_content=True)
    field, kind, raw = _load_markup(rec)
    report["markup_field"] = field
    report["markup_kind"] = kind
    if raw:
        analysis = _analyze_markup(raw)
        report["headings"] = analysis.get("headings")
        report["text_preview"] = analysis.get("text_preview")
        report["image_problems"] = (analysis.get("images") or {}).get("samples")
    report["meta_keywords"] = rec.website_meta_keywords or ""
    report["og_image"] = rec.website_meta_og_img or ""
    report["seo_name"] = rec.seo_name or ""
    report["editable"] = bool(field)
    report["next_steps"] = (
        "Propose concrete replacement values to the user, then call seo_update_meta. "
        "For alt text call seo_set_image_alt; for the <h1> call seo_fix_headings."
    )
    return report


# ---------------------------------------------------------------------------
# Tools — metadata writes
# ---------------------------------------------------------------------------

def _check_lang(env, lang):
    """Validate a language code against the DB's active languages.

    Writing a translation in a language Odoo has not activated raises a bare
    "Invalid language code" UserError; replace it with a message that tells the
    assistant which codes actually exist here.
    """
    if not lang:
        return None
    lang = str(lang).strip()
    active = env["res.lang"].sudo().search([]).mapped("code")
    if lang not in active:
        raise ValueError(
            "'%s' is not an active language on this database. Installed languages: %s. "
            "Ask the user to add the language first (Settings -> Translations -> Languages), "
            "or omit 'lang' to write the source language."
            % (lang, ", ".join(sorted(active)) or "(none)")
        )
    return lang


def _apply_meta(rec, title=None, description=None, keywords=None,
                og_image=None, seo_name=None, lang=None):
    lang = _check_lang(rec.env, lang)
    values = {}
    warnings = []
    if title is not None:
        title = str(title).strip()
        values["website_meta_title"] = title
        if title and not (TITLE_MIN <= len(title) <= TITLE_HARD_MAX):
            warnings.append("Title is %d characters (recommended %d-%d)." % (len(title), TITLE_MIN, TITLE_MAX))
    if description is not None:
        description = str(description).strip()
        values["website_meta_description"] = description
        if description and not (DESC_MIN <= len(description) <= DESC_HARD_MAX):
            warnings.append("Description is %d characters (recommended %d-%d)."
                            % (len(description), DESC_MIN, DESC_MAX))
    if keywords is not None:
        if isinstance(keywords, (list, tuple)):
            keywords = ", ".join(str(k).strip() for k in keywords if str(k).strip())
        values["website_meta_keywords"] = str(keywords).strip()
    if og_image is not None:
        values["website_meta_og_img"] = str(og_image).strip()
    if seo_name is not None:
        values["seo_name"] = str(seo_name).strip()

    if not values:
        raise ValueError(
            "Nothing to update: pass at least one of title, description, keywords, "
            "og_image or seo_name."
        )

    target = rec.with_context(lang=lang) if lang else rec
    target.write(values)
    return values, warnings


def seo_update_meta(cr, env, model, res_id, title=None, description=None, keywords=None,
                    og_image=None, seo_name=None, lang=None):
    """Write SEO metadata on one record."""
    rec = _resolve_record(env, model, res_id)
    values, warnings = _apply_meta(rec, title, description, keywords, og_image, seo_name, lang)
    return {
        "model": rec._name,
        "id": rec.id,
        "name": _record_label(rec),
        "url": _record_url(rec),
        "lang": lang or "source language",
        "updated": values,
        "warnings": warnings,
    }


def seo_bulk_update_meta(cr, env, items, lang=None):
    """Write SEO metadata on many records in one call.

    ``items``: [{"model": "website.page", "res_id": 4, "title": "...",
                 "description": "...", "keywords": "...", "og_image": "...",
                 "seo_name": "..."}]
    """
    items = _as_list(items, "items")
    if not items:
        raise ValueError(
            "'items' is empty. Example: "
            "[{\"model\": \"website.page\", \"res_id\": 4, \"title\": \"...\", \"description\": \"...\"}]"
        )
    updated, failed = [], []
    for raw_item in items:
        item = _as_dict(raw_item, "items[]")
        try:
            rec = _resolve_record(env, item.get("model"), item.get("res_id"), item.get("url"))
            values, warnings = _apply_meta(
                rec,
                item.get("title"), item.get("description"), item.get("keywords"),
                item.get("og_image"), item.get("seo_name"),
                item.get("lang") or lang,
            )
            updated.append({
                "model": rec._name, "id": rec.id, "url": _record_url(rec),
                "updated": sorted(values), "warnings": warnings,
            })
        except Exception as exc:
            failed.append({"item": item, "error": str(exc)})
    return {
        "updated_count": len(updated),
        "failed_count": len(failed),
        "updated": updated,
        "failed": failed,
    }


def seo_set_page_url(cr, env, page_id, new_url, create_redirect=True, redirect_type="301"):
    """Rename a website.page URL and (by default) create the 301 redirect."""
    Page = env.get("website.page")
    if Page is None:
        raise ValueError(_WEBSITE_MISSING_MSG)
    page = Page.sudo().browse(_as_int(page_id, "page_id")).exists()
    if not page:
        raise ValueError("No website.page with id=%s. Use seo_audit(model='website.page') to list pages." % page_id)

    create_redirect = _as_bool(create_redirect, True)
    redirect_type = str(redirect_type or "301").strip()
    if redirect_type not in ("301", "302", "308"):
        raise ValueError("redirect_type must be '301' (permanent, the SEO-safe default), '302' or '308'.")

    old_url = page.url
    new_url = "/" + str(new_url or "").strip().lstrip("/")
    if not new_url or new_url == "/":
        raise ValueError("new_url must be a non-empty path, e.g. '/ceramic-vases'.")

    page.write({"url": new_url})
    # Odoo slugifies and de-duplicates the URL on write, so read it back.
    effective_url = page.url

    redirect = None
    if create_redirect and effective_url != old_url:
        Rewrite = env.get("website.rewrite")
        if Rewrite is None:
            raise ValueError(_WEBSITE_MISSING_MSG)
        rewrite = Rewrite.sudo().create({
            "name": "SEO rename %s -> %s" % (old_url, effective_url),
            "redirect_type": redirect_type,
            "url_from": old_url,
            "url_to": effective_url,
            "website_id": page.website_id.id or False,
        })
        redirect = {"id": rewrite.id, "type": redirect_type, "from": old_url, "to": effective_url}

    return {
        "page_id": page.id,
        "name": page.name,
        "old_url": old_url,
        "new_url": effective_url,
        "url_was_adjusted": effective_url != new_url,
        "redirect": redirect,
        "note": (
            "Odoo slugifies URLs on write, so new_url may have been normalised. "
            + ("A %s redirect keeps the old URL's ranking." % redirect_type if redirect
               else "No redirect was created — the old URL now returns 404 and loses its ranking.")
        ),
    }


def seo_set_indexing(cr, env, model, res_id, website_indexed=None, is_published=None):
    """Toggle search-engine indexing and/or publication of a record."""
    rec = _resolve_record(env, model, res_id)
    website_indexed = _as_bool(website_indexed)
    is_published = _as_bool(is_published)

    values = {}
    if website_indexed is not None:
        if "website_indexed" not in rec._fields:
            raise ValueError("%s has no 'website_indexed' field; only website.page does." % rec._name)
        values["website_indexed"] = website_indexed
    if is_published is not None:
        field = "is_published" if "is_published" in rec._fields else (
            "website_published" if "website_published" in rec._fields else None)
        if not field:
            raise ValueError("%s cannot be published/unpublished." % rec._name)
        values[field] = is_published
    if not values:
        raise ValueError("Pass website_indexed and/or is_published.")

    rec.write(values)
    return {
        "model": rec._name,
        "id": rec.id,
        "url": _record_url(rec),
        "updated": values,
        "note": (
            "Indexing changes only reach Google after the sitemap cache expires (12h) "
            "or after seo_refresh_sitemap, and after the next crawl."
        ),
    }


# ---------------------------------------------------------------------------
# Tools — surgical markup edits
# ---------------------------------------------------------------------------

def _backup_key(rec):
    return "%s%s.%s" % (_ARCH_BACKUP_PREFIX, rec._name, rec.id)


def _store_backup(env, rec, field, raw):
    if len(raw) > _ARCH_BACKUP_MAX_CHARS:
        return False
    env["ir.config_parameter"].sudo().set_param(
        _backup_key(rec), json.dumps({"field": field, "markup": raw})
    )
    return True


def _write_markup(env, rec, field, kind, root):
    new_value = _dump_after_edit(root, kind)
    rec.write({field: new_value})
    return new_value


def seo_set_image_alt(cr, env, model, res_id, alts):
    """Set alt text on images inside a page's markup.

    ``alts``: [{"src_contains": "hero", "alt": "Blue ceramic vase on a wooden table"}]
    or [{"index": 0, "alt": "..."}] using the 0-based image order returned by
    ``seo_get_page``. Only the alt attribute is modified.
    """
    rec = _resolve_record(env, model, res_id)
    field, kind, raw = _load_markup(rec)
    if not field:
        raise ValueError("%s,%s has no editable markup field." % (rec._name, rec.id))

    rules = [_as_dict(rule, "alts[]") for rule in _as_list(alts, "alts")]
    if not rules:
        raise ValueError(
            "'alts' is empty. Example: "
            "[{\"src_contains\": \"hero\", \"alt\": \"Blue ceramic vase on a wooden table\"}]"
        )
    for rule in rules:
        if "alt" not in rule:
            raise ValueError("Each entry of 'alts' needs an 'alt' value. Got: %s" % json.dumps(rule))
        if "src_contains" not in rule and "index" not in rule:
            raise ValueError(
                "Each entry of 'alts' needs 'src_contains' or 'index'. Got: %s" % json.dumps(rule)
            )

    root = _parse_for_edit(raw, kind)
    images = list(_iter_tag(root, "img"))
    applied, unmatched = [], []

    for rule in rules:
        alt = str(rule["alt"]).strip()
        matched = []
        if "index" in rule:
            idx = _as_int(rule["index"], "alts[].index")
            if 0 <= idx < len(images):
                matched = [images[idx]]
        else:
            needle = str(rule["src_contains"]).strip().lower()
            matched = [
                img for img in images
                if needle in ((img.get("src") or "") + " " + (img.get("data-src") or "")).lower()
            ]
        if not matched:
            unmatched.append(rule)
            continue
        for img in matched:
            previous = img.get("alt")
            img.set("alt", alt)
            applied.append({
                "src": (img.get("src") or img.get("data-src") or "")[:200],
                "old_alt": previous,
                "new_alt": alt,
            })

    if not applied:
        raise ValueError(
            "None of the rules matched an image. The page has %d images: %s"
            % (len(images), json.dumps([(img.get("src") or "")[:120] for img in images[:20]]))
        )

    backed_up = _store_backup(env, rec, field, raw)
    _write_markup(env, rec, field, kind, root)

    return {
        "model": rec._name,
        "id": rec.id,
        "url": _record_url(rec),
        "field": field,
        "images_total": len(images),
        "applied": applied,
        "unmatched_rules": unmatched,
        "backup_stored": backed_up,
        "note": ("Undo with seo_restore_arch_backup." if backed_up
                 else "Markup was too large to back up; seo_restore_arch_backup will not help here."),
    }


def seo_fix_headings(cr, env, model, res_id, h1_text=None, demote_extra_h1=True):
    """Enforce exactly one <h1> on a page.

    - No <h1> at all: promote the first <h2>, or insert ``h1_text`` at the top.
    - Several <h1>: keep the first (optionally retitled) and demote the rest to <h2>.
    Only heading tag names and the first heading's text are touched.
    """
    rec = _resolve_record(env, model, res_id)
    field, kind, raw = _load_markup(rec)
    if not field:
        raise ValueError("%s,%s has no editable markup field." % (rec._name, rec.id))

    demote_extra_h1 = _as_bool(demote_extra_h1, True)
    h1_text = str(h1_text).strip() if h1_text else None

    root = _parse_for_edit(raw, kind)
    h1s = list(_iter_tag(root, "h1"))
    actions = []

    if not h1s:
        h2s = list(_iter_tag(root, "h2"))
        if h2s:
            promoted = h2s[0]
            old_text = re.sub(r"\s+", " ", "".join(promoted.itertext())).strip()
            promoted.tag = "h1"
            if h1_text:
                for child in list(promoted):
                    promoted.remove(child)
                promoted.text = h1_text
            actions.append({"action": "promoted_h2_to_h1", "old_text": old_text,
                            "new_text": h1_text or old_text})
        else:
            if not h1_text:
                raise ValueError(
                    "The page has no <h1> and no <h2> to promote. Pass h1_text so I can insert one, "
                    "e.g. seo_fix_headings(..., h1_text='Handmade ceramic vases')."
                )
            heading = etree.Element("h1") if kind == "xml" else lxml_html.Element("h1")
            heading.text = h1_text
            root.insert(0, heading)
            actions.append({"action": "inserted_h1", "new_text": h1_text})
    else:
        first = h1s[0]
        if h1_text:
            old_text = re.sub(r"\s+", " ", "".join(first.itertext())).strip()
            for child in list(first):
                first.remove(child)
            first.text = h1_text
            actions.append({"action": "retitled_h1", "old_text": old_text, "new_text": h1_text})
        if len(h1s) > 1 and demote_extra_h1:
            for extra in h1s[1:]:
                text = re.sub(r"\s+", " ", "".join(extra.itertext())).strip()
                extra.tag = "h2"
                actions.append({"action": "demoted_h1_to_h2", "text": text[:120]})

    if not actions:
        return {
            "model": rec._name, "id": rec.id, "url": _record_url(rec),
            "changed": False,
            "note": "The page already has exactly one <h1> and no h1_text was provided — nothing to do.",
        }

    backed_up = _store_backup(env, rec, field, raw)
    _write_markup(env, rec, field, kind, root)

    return {
        "model": rec._name,
        "id": rec.id,
        "url": _record_url(rec),
        "field": field,
        "changed": True,
        "actions": actions,
        "backup_stored": backed_up,
        "note": ("Undo with seo_restore_arch_backup." if backed_up
                 else "Markup was too large to back up; seo_restore_arch_backup will not help here."),
    }


def seo_restore_arch_backup(cr, env, model, res_id):
    """Restore the markup saved before the last seo_set_image_alt / seo_fix_headings call."""
    rec = _resolve_record(env, model, res_id)
    key = _backup_key(rec)
    stored = env["ir.config_parameter"].sudo().get_param(key)
    if not stored:
        raise ValueError(
            "No SEO markup backup for %s,%s. Backups only exist after seo_set_image_alt or "
            "seo_fix_headings, and only the most recent one is kept." % (rec._name, rec.id)
        )
    payload = json.loads(stored)
    rec.write({payload["field"]: payload["markup"]})
    env["ir.config_parameter"].sudo().search([("key", "=", key)]).unlink()
    return {
        "model": rec._name,
        "id": rec.id,
        "url": _record_url(rec),
        "restored_field": payload["field"],
        "note": "The backup was consumed; there is nothing left to restore for this record.",
    }


# ---------------------------------------------------------------------------
# Tools — redirects
# ---------------------------------------------------------------------------

def _require_rewrite(env):
    model = env.get("website.rewrite")
    if model is None:
        raise ValueError(_WEBSITE_MISSING_MSG)
    return model.sudo()


def seo_list_redirects(cr, env, website_id=None, limit=100):
    """List the configured URL redirects / rewrites."""
    Rewrite = _require_rewrite(env)
    limit = min(max(_as_int(limit, "limit", 100) or 100, 1), 500)
    domain = []
    wid = _as_int(website_id, "website_id")
    if wid:
        domain.append(("website_id", "in", [wid, False]))
    rows = Rewrite.search_read(
        domain, ["name", "redirect_type", "url_from", "url_to", "website_id", "active", "sequence"],
        limit=limit, order="sequence, id",
    )
    return {"count": len(rows), "redirects": rows}


def seo_create_redirect(cr, env, url_from, url_to=None, redirect_type="301",
                        name=None, website_id=None):
    """Create a redirect. Use 301 when a URL moved permanently — it passes ranking on."""
    Rewrite = _require_rewrite(env)
    redirect_type = str(redirect_type or "301").strip()
    if redirect_type not in ("301", "302", "308", "404"):
        raise ValueError(
            "redirect_type must be one of: '301' (moved permanently — the SEO default), "
            "'302' (temporary), '308' (rewrite, both URLs stay reachable), "
            "'404' (remove a route)."
        )
    url_from = "/" + str(url_from or "").strip().lstrip("/")
    if url_from == "/":
        raise ValueError("url_from must be a real path, e.g. '/old-page'.")
    if redirect_type != "404":
        if not url_to:
            raise ValueError("url_to is required for a %s redirect." % redirect_type)
        url_to = "/" + str(url_to).strip().lstrip("/")
        # Odoo 19 enforces this with a ValidationError on website.rewrite; check it
        # here so the assistant gets an actionable message on every version.
        if url_to.split("#")[0] == url_from.split("#")[0]:
            raise ValueError(
                "url_from and url_to are the same page ('%s'): that would be a redirect loop. "
                "If you meant to rename a page, use seo_set_page_url — it changes the URL and "
                "creates the redirect from the OLD one in a single step." % url_from
            )
        if redirect_type == "308" and url_to == "/":
            raise ValueError(
                "A 308 rewrite cannot target '/'. To change what the homepage shows, set the "
                "website's Homepage URL instead."
            )

    values = {
        "name": name or ("Redirect %s -> %s" % (url_from, url_to or "404")),
        "redirect_type": redirect_type,
        "url_from": url_from,
        "url_to": url_to if redirect_type != "404" else False,
    }
    wid = _as_int(website_id, "website_id")
    if wid:
        values["website_id"] = wid

    rewrite = Rewrite.create(values)
    return {
        "id": rewrite.id,
        "name": rewrite.name,
        "type": redirect_type,
        "url_from": url_from,
        "url_to": url_to,
        "note": (
            "Avoid redirect chains: if /a already redirects to /b, point /a at the final URL "
            "rather than adding /b -> /c."
        ),
    }


def seo_delete_redirect(cr, env, redirect_ids):
    """Delete redirect(s) by id."""
    Rewrite = _require_rewrite(env)
    ids = [_as_int(i, "redirect_ids[]") for i in _as_list(redirect_ids, "redirect_ids")]
    if not ids:
        raise ValueError("Pass redirect_ids, e.g. 12 or [12, 13].")
    records = Rewrite.browse(ids).exists()
    if not records:
        raise ValueError("No redirect found with id(s) %s." % ids)
    deleted = records.read(["name", "url_from", "url_to", "redirect_type"])
    records.unlink()
    return {"deleted_count": len(deleted), "deleted": deleted}


# ---------------------------------------------------------------------------
# Tools — robots.txt, sitemap, website settings
# ---------------------------------------------------------------------------

def seo_set_robots(cr, env, content, website_id=None):
    """Replace the CUSTOM part of robots.txt.

    Odoo always emits 'User-agent: *' and the Sitemap line itself; this value is
    appended below them. Do not repeat those lines here.
    """
    sites = _websites(env, website_id)
    if len(sites) > 1:
        raise ValueError(
            "This database has %d websites. Pass website_id — call seo_get_overview to list them."
            % len(sites)
        )
    content = str(content or "").strip()
    warning = None
    if re.search(r"(?mi)^\s*Disallow:\s*/\s*$", re.sub(r"<[^>]+>", " ", content)):
        warning = ("This content contains 'Disallow: /', which blocks the ENTIRE site from all "
                   "crawlers. Confirm with the user that this is intentional.")
    sites.write({"robots_txt": content})
    return {
        "website_id": sites.id,
        "website": sites.name,
        "custom_robots_txt": content,
        "warning": warning,
        "note": "Verify the result at <base_url>/robots.txt — Odoo prepends the auto-generated header.",
    }


def seo_refresh_sitemap(cr, env, website_id=None):
    """Invalidate the cached sitemap.xml so the next request regenerates it."""
    _require_website(env)  # fail fast with the install message when website is absent
    Attachment = env["ir.attachment"].sudo()
    domain = [("type", "=", "binary"), ("url", "=like", "/sitemap-%")]
    wid = _as_int(website_id, "website_id")
    if wid:
        domain.append(("url", "=like", "/sitemap-%d-%%" % wid))
    cached = Attachment.search(domain)
    urls = cached.mapped("url")
    count = len(cached)
    cached.unlink()
    return {
        "cleared_count": count,
        "cleared_urls": urls[:20],
        "note": (
            "The sitemap is rebuilt on the next request to /sitemap.xml and cached again for 12 hours. "
            "It lists published + indexed records only."
        ),
    }


_WEBSITE_SETTING_FIELDS = (
    "domain", "google_search_console", "google_analytics_key",
    "social_twitter", "social_facebook", "social_linkedin",
    "social_instagram", "social_youtube", "social_tiktok", "social_github",
)


def seo_update_website_settings(cr, env, website_id=None, domain=None,
                                google_search_console=None, google_analytics_key=None,
                                social_twitter=None, social_facebook=None,
                                social_linkedin=None, social_instagram=None,
                                social_youtube=None, social_tiktok=None, social_github=None):
    """Update site-wide SEO settings (domain, Search Console, Analytics, social accounts)."""
    sites = _websites(env, website_id)
    if len(sites) > 1:
        raise ValueError(
            "This database has %d websites. Pass website_id — call seo_get_overview to list them."
            % len(sites)
        )

    supplied = {
        "domain": domain,
        "google_search_console": google_search_console,
        "google_analytics_key": google_analytics_key,
        "social_twitter": social_twitter,
        "social_facebook": social_facebook,
        "social_linkedin": social_linkedin,
        "social_instagram": social_instagram,
        "social_youtube": social_youtube,
        "social_tiktok": social_tiktok,
        "social_github": social_github,
    }
    values = {}
    for key, value in supplied.items():
        if value is None:
            continue
        if key not in sites._fields:
            continue
        values[key] = str(value).strip()

    if not values:
        raise ValueError(
            "Nothing to update. Supported arguments: %s." % ", ".join(_WEBSITE_SETTING_FIELDS)
        )

    warnings = []
    if "domain" in values and values["domain"]:
        if not values["domain"].startswith(("http://", "https://")):
            raise ValueError(
                "domain must include the scheme, e.g. 'https://www.example.com' (got %r)."
                % values["domain"]
            )
        warnings.append(
            "Odoo serves 'Disallow: /' in robots.txt for any request whose host does not match "
            "this domain. Make sure the live site is actually served on %s." % values["domain"]
        )

    sites.write(values)
    return {
        "website_id": sites.id,
        "website": sites.name,
        "updated": values,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# MCP wiring — definitions, dispatch, write set
# ---------------------------------------------------------------------------

SEO_TOOL_DEFINITIONS = [
    {
        "name": "seo_help",
        "description": (
            "CALL THIS FIRST the very first time the user asks anything about SEO, website "
            "referencing, Google ranking, meta tags, sitemap or robots.txt. Returns the rules, the "
            "mandatory workflow, what Odoo already does automatically (sitemap, canonical, hreflang), "
            "and the character limits you must respect when writing metadata. No arguments."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "seo_get_overview",
        "description": (
            "CALL THIS BEFORE ANY OTHER SEO TOOL. Site-wide SEO snapshot: every website with its "
            "domain, languages, Google Search Console / Analytics keys, social defaults, custom "
            "robots.txt and scored configuration issues; the list of SEO-capable models "
            "(website.page, blog.post, product.template, ...) with metadata coverage percentages; "
            "the redirect count and cached sitemaps. Fix the reported config_issues before touching "
            "individual pages — a wrong Website Domain de-indexes the whole site."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "website_id": {"type": "integer", "description": "Restrict to one website. Omit for all."},
            },
        },
    },
    {
        "name": "seo_audit",
        "description": (
            "Scan SEO-capable records and return a scored, ranked list of concrete problems: missing "
            "or badly sized meta titles/descriptions, duplicate titles across pages, missing OG "
            "images, noindex/unpublished pages, bad URLs, missing or multiple <h1>, images without "
            "alt text, thin content, dead-end pages, generic anchor text. Each issue carries a "
            "severity and the exact tool to fix it. Defaults to website.page + blog.post + "
            "product.template; pass 'model' to target one. Use this to answer 'audit my website' or "
            "'why doesn't my site rank'. Report the findings to the user before writing anything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "website_id": {"type": "integer"},
                "model": {"type": "string", "description": "One SEO model, e.g. 'website.page', 'product.template', 'blog.post'."},
                "limit": {"type": "integer", "default": 50, "description": "Records per model (cap 200)."},
                "offset": {"type": "integer", "default": 0, "description": "Paginate through large sites."},
                "only_problems": {"type": "boolean", "default": True, "description": "Hide records with no issue."},
                "include_content_checks": {"type": "boolean", "default": True, "description": "Parse page markup for h1/alt/word-count checks. Set false for a faster metadata-only pass."},
                "max_score": {"type": "integer", "description": "Only return records scoring at or below this (0-100)."},
            },
        },
    },
    {
        "name": "seo_get_page",
        "description": (
            "Deep SEO dive on ONE page or record: current metadata with lengths, URL, indexed and "
            "published flags, full heading outline, word count, images missing alt text (with their "
            "src), internal/external link counts, a text preview, and the scored issue list. Call "
            "this before rewriting a page's metadata so your titles reflect the real content. "
            "Identify the record with model+res_id, or with a public url like '/shop'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "e.g. 'website.page'. Use with res_id."},
                "res_id": {"type": "integer", "description": "Record id. Use with model."},
                "url": {"type": "string", "description": "Public path instead of model+res_id, e.g. '/about-us'."},
                "website_id": {"type": "integer"},
            },
        },
    },
    {
        "name": "seo_update_meta",
        "description": (
            "Write SEO metadata on ONE record: meta title (%d-%d chars, keyword first), meta "
            "description (%d-%d chars, written for humans), meta keywords, OpenGraph image URL and "
            "seo_name (URL slug override). Only the arguments you pass are changed. Pass 'lang' "
            "(e.g. 'fr_FR') to write a translation instead of overwriting the source language. "
            "Show the proposed values to the user before calling this."
        ) % (TITLE_MIN, TITLE_MAX, DESC_MIN, DESC_MAX),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "e.g. 'website.page', 'product.template', 'blog.post'."},
                "res_id": {"type": "integer"},
                "title": {"type": "string", "description": "Meta title, %d-%d characters." % (TITLE_MIN, TITLE_MAX)},
                "description": {"type": "string", "description": "Meta description, %d-%d characters." % (DESC_MIN, DESC_MAX)},
                "keywords": {"type": "string", "description": "Comma-separated. Ignored by Google; only needed for Odoo's 'SEO optimized' indicator."},
                "og_image": {"type": "string", "description": "Image URL for social sharing, e.g. '/web/image/product.template/3/image_1920'."},
                "seo_name": {"type": "string", "description": "Slug override used when Odoo builds the record's URL."},
                "lang": {"type": "string", "description": "Language code to write the translation in, e.g. 'fr_FR', 'nl_NL'."},
            },
            "required": ["model", "res_id"],
        },
    },
    {
        "name": "seo_bulk_update_meta",
        "description": (
            "Write SEO metadata on MANY records in one call. Use after seo_audit when several pages "
            "need titles/descriptions. Each item: {\"model\": \"website.page\", \"res_id\": 4, "
            "\"title\": \"...\", \"description\": \"...\"} plus optional keywords, og_image, "
            "seo_name, lang. Failures are reported per item instead of aborting the batch. "
            "Confirm the full list with the user before running this on more than ~10 records."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {"type": "string", "description": "JSON array of {model, res_id, title, description, ...} objects."},
                "lang": {"type": "string", "description": "Default language code for every item, e.g. 'fr_FR'."},
            },
            "required": ["items"],
        },
    },
    {
        "name": "seo_set_page_url",
        "description": (
            "Rename a website.page URL and automatically create the 301 redirect from the old URL. "
            "ALWAYS keep create_redirect=true: renaming a URL without a redirect throws away every "
            "backlink and ranking the old URL had. Odoo slugifies the value, so the effective URL is "
            "returned — report it to the user."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "integer", "description": "website.page id (from seo_audit)."},
                "new_url": {"type": "string", "description": "New path, lowercase and hyphenated, e.g. '/ceramic-vases'."},
                "create_redirect": {"type": "boolean", "default": True, "description": "Keep true unless the user explicitly wants the old URL to 404."},
                "redirect_type": {"type": "string", "default": "301", "description": "'301' permanent (default), '302' temporary, '308' rewrite."},
            },
            "required": ["page_id", "new_url"],
        },
    },
    {
        "name": "seo_set_indexing",
        "description": (
            "Turn search-engine indexing and/or publication on or off for a record. "
            "website_indexed=false removes the page from sitemap.xml AND adds meta noindex, so the "
            "page cannot rank; is_published=false makes it a 404 for visitors. Use to re-enable "
            "pages that seo_audit flagged as not indexed, or to deliberately hide thank-you / "
            "internal pages from Google."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "res_id": {"type": "integer"},
                "website_indexed": {"type": "boolean", "description": "website.page only."},
                "is_published": {"type": "boolean"},
            },
            "required": ["model", "res_id"],
        },
    },
    {
        "name": "seo_set_image_alt",
        "description": (
            "Add or fix alt text on images inside a page's markup. Call seo_get_page first to see "
            "which images lack alt and get their src. Each rule is either "
            "{\"src_contains\": \"hero\", \"alt\": \"...\"} or {\"index\": 0, \"alt\": \"...\"}. "
            "Write a short, literal description of what the image shows — never keyword stuffing. "
            "Only the alt attribute is modified; the previous markup is backed up so "
            "seo_restore_arch_backup can undo it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "res_id": {"type": "integer"},
                "alts": {"type": "string", "description": "JSON array of {src_contains|index, alt} rules."},
            },
            "required": ["model", "res_id", "alts"],
        },
    },
    {
        "name": "seo_fix_headings",
        "description": (
            "Enforce exactly one <h1> on a page. With no <h1>, promotes the first <h2> or inserts "
            "h1_text at the top. With several <h1>, keeps the first and demotes the rest to <h2>. "
            "Pass h1_text to also set the heading's wording — make it match the page's search intent "
            "without being a copy of the meta title. Only heading tags and the first heading's text "
            "are touched; the previous markup is backed up for seo_restore_arch_backup."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "res_id": {"type": "integer"},
                "h1_text": {"type": "string", "description": "Wording for the h1. Required when the page has neither h1 nor h2."},
                "demote_extra_h1": {"type": "boolean", "default": True},
            },
            "required": ["model", "res_id"],
        },
    },
    {
        "name": "seo_restore_arch_backup",
        "description": (
            "Undo the last seo_set_image_alt or seo_fix_headings edit on a record by restoring the "
            "markup saved just before it. Only the most recent edit per record is kept, and the "
            "backup is consumed once restored. Use when the user says the page looks broken after "
            "an SEO markup change."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "res_id": {"type": "integer"},
            },
            "required": ["model", "res_id"],
        },
    },
    {
        "name": "seo_list_redirects",
        "description": (
            "List configured URL redirects/rewrites (website.rewrite) with their type, source and "
            "target. Check this before creating a redirect so you do not build a redirect chain "
            "(/a -> /b -> /c), which wastes crawl budget and leaks ranking."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "website_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 100},
            },
        },
    },
    {
        "name": "seo_create_redirect",
        "description": (
            "Create a URL redirect. '301' = moved permanently, passes ranking on, the correct choice "
            "for a renamed or merged page. '302' = temporary, does NOT pass ranking. '308' = rewrite, "
            "both URLs stay reachable. '404' = remove a route (url_to not needed). Point the source "
            "at the FINAL destination rather than chaining redirects."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url_from": {"type": "string", "description": "Old path, e.g. '/old-product'."},
                "url_to": {"type": "string", "description": "New path, e.g. '/ceramic-vases'. Not needed for type '404'."},
                "redirect_type": {"type": "string", "default": "301", "description": "'301', '302', '308' or '404'."},
                "name": {"type": "string", "description": "Optional label shown in the backend."},
                "website_id": {"type": "integer"},
            },
            "required": ["url_from"],
        },
    },
    {
        "name": "seo_delete_redirect",
        "description": (
            "Delete redirect(s) by id. Warn the user first: deleting a 301 makes the old URL return "
            "404 and loses whatever ranking and backlinks it still carried."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "redirect_ids": {"type": "string", "description": "Single id or JSON array, e.g. 12 or [12, 13]."},
            },
            "required": ["redirect_ids"],
        },
    },
    {
        "name": "seo_set_robots",
        "description": (
            "Replace the CUSTOM part of robots.txt. Odoo already emits 'User-agent: *' and the "
            "Sitemap line automatically — do not repeat them. Use this to disallow crawling of "
            "specific paths (e.g. 'Disallow: /shop/cart'). Never write a bare 'Disallow: /' unless "
            "the user explicitly wants the whole site hidden from Google; the tool warns when you do."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The custom robots.txt lines, e.g. 'Disallow: /shop/cart\\nDisallow: /web/login'."},
                "website_id": {"type": "integer", "description": "Required when the database has several websites."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "seo_refresh_sitemap",
        "description": (
            "Clear the cached sitemap.xml so it is regenerated on the next request. Odoo caches the "
            "sitemap for 12 hours; call this after publishing pages or changing indexing flags if "
            "the user wants the sitemap to reflect the change immediately."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "website_id": {"type": "integer"},
            },
        },
    },
    {
        "name": "seo_update_website_settings",
        "description": (
            "Update site-wide SEO settings: 'domain' (the canonical base URL — must include https:// "
            "and match the host actually serving the site, otherwise Odoo returns 'Disallow: /' in "
            "robots.txt and de-indexes everything), 'google_search_console' verification key, "
            "'google_analytics_key', and the social account handles used in OpenGraph/Twitter cards. "
            "Only the arguments you pass are changed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "website_id": {"type": "integer", "description": "Required when the database has several websites."},
                "domain": {"type": "string", "description": "Canonical base URL with scheme, e.g. 'https://www.example.com'."},
                "google_search_console": {"type": "string"},
                "google_analytics_key": {"type": "string"},
                "social_twitter": {"type": "string"},
                "social_facebook": {"type": "string"},
                "social_linkedin": {"type": "string"},
                "social_instagram": {"type": "string"},
                "social_youtube": {"type": "string"},
                "social_tiktok": {"type": "string"},
                "social_github": {"type": "string"},
            },
        },
    },
]


SEO_DISPATCH = {
    "seo_help": (seo_help, lambda x: x),
    "seo_get_overview": (seo_get_overview, _format_json),
    "seo_audit": (seo_audit, _format_json),
    "seo_get_page": (seo_get_page, _format_json),
    "seo_update_meta": (seo_update_meta, _format_json),
    "seo_bulk_update_meta": (seo_bulk_update_meta, _format_json),
    "seo_set_page_url": (seo_set_page_url, _format_json),
    "seo_set_indexing": (seo_set_indexing, _format_json),
    "seo_set_image_alt": (seo_set_image_alt, _format_json),
    "seo_fix_headings": (seo_fix_headings, _format_json),
    "seo_restore_arch_backup": (seo_restore_arch_backup, _format_json),
    "seo_list_redirects": (seo_list_redirects, _format_json),
    "seo_create_redirect": (seo_create_redirect, _format_json),
    "seo_delete_redirect": (seo_delete_redirect, _format_json),
    "seo_set_robots": (seo_set_robots, _format_json),
    "seo_refresh_sitemap": (seo_refresh_sitemap, _format_json),
    "seo_update_website_settings": (seo_update_website_settings, _format_json),
}


# Tools that modify data — the controller commits after these succeed.
SEO_WRITE_TOOLS = frozenset({
    "seo_update_meta",
    "seo_bulk_update_meta",
    "seo_set_page_url",
    "seo_set_indexing",
    "seo_set_image_alt",
    "seo_fix_headings",
    "seo_restore_arch_backup",
    "seo_create_redirect",
    "seo_delete_redirect",
    "seo_set_robots",
    "seo_refresh_sitemap",
    "seo_update_website_settings",
})
