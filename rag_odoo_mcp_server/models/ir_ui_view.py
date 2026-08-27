# -*- coding: utf-8 -*-
import ast
import logging

from odoo import models, _

_logger = logging.getLogger(__name__)


def _mcp_access_tables_ready(cr):
    """Return True only once this module's access tables exist.

    The view post-processors below query rag.mcp.hide.field / rag.mcp.hide.view.nodes /
    rag.mcp.hide.filters.groups. View post-processing runs during module install/upgrade,
    before those tables are created, which would abort the load transaction.
    ``to_regclass`` returns NULL (no error) when the table is absent, so this is
    safe to call inside a live transaction.
    """
    try:
        cr.execute("SELECT to_regclass('rag_mcp_access_management'), to_regclass('rag_mcp_access_domain_ah')")
        row = cr.fetchone()
        return bool(row and row[0] and row[1])
    except Exception:
        return False


def _translate_string(view, source_lang, target_lang, value):
    """Translate an attribute string from `source_lang` to `target_lang` using
    the view's stored translation dictionary. Returns the input unchanged if
    the translation cannot be resolved.
    """
    if not value or source_lang == target_lang:
        return value
    try:
        field = view._fields['arch_db']
        translation_dictionary = field.get_translation_dictionary(
            view.with_context(lang=source_lang).arch_db,
            {target_lang: view.with_context(lang=target_lang).arch_db},
        )
        entry = translation_dictionary.get(value)
        if entry and target_lang in entry:
            return entry[target_lang]
    except (KeyError, AttributeError) as exc:
        _logger.debug("hide.view.nodes: translation lookup failed for %r (%s -> %s): %s",
                      value, source_lang, target_lang, exc)
    return value


class ir_ui_view(models.Model):
    _inherit = 'ir.ui.view'

    def _active_hide_domain(self, model_name):
        """Domain shared by all _postprocess_tag_* hooks."""
        return [
            ('access_management_id.company_ids', 'in', self.env.company.id),
            ('model_id.model', '=', model_name),
            ('access_management_id.active', '=', True),
            ('access_management_id.user_ids', 'in', self._uid),
        ]

    def _postprocess_tag_field(self, node, name_manager, node_info):
        super()._postprocess_tag_field(node, name_manager, node_info)
        if not _mcp_access_tables_ready(self._cr):
            return
        if node.tag not in ('field', 'label'):
            return
        try:
            hide_fields = self.env['rag.mcp.hide.field'].sudo().search(self._active_hide_domain(name_manager.model._name))
        except Exception as exc:
            _logger.warning("hide.field search failed for %s: %s", name_manager.model._name, exc)
            return

        for hide_field in hide_fields:
            for field_id in hide_field.field_id:
                is_field_match = node.tag == 'field' and node.get('name') == field_id.name
                is_label_match = node.tag == 'label' and node.attrib.get('for') == field_id.name
                if not (is_field_match or is_label_match):
                    continue
                if hide_field.external_link:
                    options_dict = {}
                    raw = node.attrib.get('options')
                    if raw:
                        try:
                            options_dict = ast.literal_eval(raw) or {}
                            if not isinstance(options_dict, dict):
                                options_dict = {}
                        except (ValueError, SyntaxError) as exc:
                            _logger.debug("hide.field: invalid options %r on %s: %s", raw, field_id.name, exc)
                            options_dict = {}
                    options_dict.update({"no_edit": True, "no_create": True, "no_open": True})
                    node.attrib['options'] = str(options_dict)
                if hide_field.invisible:
                    node_info['invisible'] = True
                    node.set('invisible', '1')
                if hide_field.readonly:
                    node_info['readonly'] = True
                    node.set('readonly', '1')
                    node.set('force_save', '1')
                if hide_field.required:
                    node_info['required'] = True
                    node.set('required', '1')

    def _postprocess_tag_button(self, node, name_manager, node_info):
        postprocessor = getattr(super(ir_ui_view, self), '_postprocess_tag_button', False)
        if postprocessor:
            super(ir_ui_view, self)._postprocess_tag_button(node, name_manager, node_info)

        if not _mcp_access_tables_ready(self._cr):
            return None
        node_name = node.get('name')
        if not node_name:
            return None

        hide_ids = self.env['rag.mcp.hide.view.nodes'].sudo().search(self._active_hide_domain(name_manager.model._name))
        btn_nodes = hide_ids.mapped('btn_store_model_nodes_ids')
        if any(b.attribute_name == node_name for b in btn_nodes):
            node.set('invisible', '1')
            node.attrib.pop('attrs', None)
            node_info['invisible'] = True
        return None

    def _postprocess_tag_page(self, node, name_manager, node_info):
        postprocessor = getattr(super(ir_ui_view, self), '_postprocess_tag_page', False)
        if postprocessor:
            super(ir_ui_view, self)._postprocess_tag_page(node, name_manager, node_info)

        if not _mcp_access_tables_ready(self._cr):
            return None
        node_string = node.get('string')
        if not node_string:
            return None

        hide_ids = self.env['rag.mcp.hide.view.nodes'].sudo().search(self._active_hide_domain(name_manager.model._name))
        for tab in hide_ids.mapped('page_store_model_nodes_ids'):
            attribute_string = _translate_string(self, tab.lang_code or self.env.lang, self.env.lang, tab.attribute_string)
            if attribute_string == node_string:
                node.set('invisible', '1')
                node.attrib.pop('attrs', None)
                node_info['invisible'] = True
                break
        return None

    def _postprocess_tag_a(self, node, name_manager, node_info):
        postprocessor = getattr(super(ir_ui_view, self), '_postprocess_tag_a', False)
        if postprocessor:
            super(ir_ui_view, self)._postprocess_tag_a(node, name_manager, node_info)

        if not _mcp_access_tables_ready(self._cr):
            return None
        node_name = node.get('name')
        if not node_name:
            return None

        hide_ids = self.env['rag.mcp.hide.view.nodes'].sudo().search(self._active_hide_domain(name_manager.model._name))
        links = hide_ids.mapped('link_store_model_nodes_ids')
        if any(_(link.attribute_name or '') == node_name for link in links):
            node.set('invisible', '1')
            node.attrib.pop('attrs', None)
            node_info['invisible'] = True
        return None

    def _postprocess_tag_div(self, node, name_manager, node_info):
        postprocessor = getattr(super(ir_ui_view, self), '_postprocess_tag_div', False)
        if postprocessor:
            super(ir_ui_view, self)._postprocess_tag_div(node, name_manager, node_info)

        if not _mcp_access_tables_ready(self._cr):
            return None
        if name_manager.model._name != 'res.config.settings' or node.tag != 'app' or not node.get('string'):
            return None

        data_key = node.get('data-key')
        if not data_key:
            return None

        hide_ids = self.env['rag.mcp.hide.view.nodes'].sudo().search(self._active_hide_domain(name_manager.model._name))
        for setting_tab in hide_ids.mapped('page_store_model_nodes_ids'):
            if setting_tab.attribute_name == data_key:
                node_info['invisible'] = True
                node.set('invisible', '1')
                break
        return None

    def _postprocess_tag_filter(self, node, name_manager, node_info):
        postprocessor = getattr(super(ir_ui_view, self), '_postprocess_tag_filter', False)
        if postprocessor:
            super(ir_ui_view, self)._postprocess_tag_filter(node, name_manager, node_info)

        if not _mcp_access_tables_ready(self._cr):
            return None
        if node.tag not in ('filter', 'group'):
            return None

        node_name = node.get('name')
        if not node_name:
            return None

        hide_filter_groups = self.env['rag.mcp.hide.filters.groups'].sudo().search(
            self._active_hide_domain(name_manager.model._name))
        for rec in hide_filter_groups:
            filter_names = rec.filters_store_model_nodes_ids.mapped('attribute_name')
            group_names = rec.groups_store_model_nodes_ids.mapped('attribute_name')
            if node_name in filter_names or node_name in group_names:
                node_info['invisible'] = True
                node.set('invisible', '1')
                break
        return None
