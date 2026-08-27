# -*- coding: utf-8 -*-
import logging

from lxml import etree

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class hide_view_nodes(models.Model):
    _name = 'rag.mcp.hide.view.nodes'
    _description = 'Hide View Nodes'

    model_id = fields.Many2one('ir.model', string='Model', index=True, required=True, ondelete='cascade')
    model_name = fields.Char(string='Model Name', related='model_id.model', readonly=True, store=True)

    btn_store_model_nodes_ids = fields.Many2many('rag.mcp.store.model.nodes', 'rag_mcp_btn_hide_view_nodes_store_model_nodes_rel',
                                                 'hide_id', 'store_id', string='Hide Button',
                                                 domain="[('node_option','=','button')]")
    page_store_model_nodes_ids = fields.Many2many('rag.mcp.store.model.nodes', 'rag_mcp_page_hide_view_nodes_store_model_nodes_rel',
                                                  'hide_id', 'store_id', string='Hide Tab/Page',
                                                  domain="[('node_option','=','page')]")
    link_store_model_nodes_ids = fields.Many2many('rag.mcp.store.model.nodes', 'rag_mcp_link_hide_view_nodes_store_model_nodes_rel',
                                                  'hide_id', 'store_id', string='Hide Kanban Link',
                                                  domain="[('node_option','=','link')]")

    access_management_id = fields.Many2one('rag.mcp.access.management', 'Access Management')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_view_arch(arch):
        """Parse a view arch string/bytes into an lxml element.

        Handles both str and bytes, tolerates XML declarations, and returns
        None on failure instead of letting the caller crash.
        """
        if arch is None:
            return None
        if isinstance(arch, str):
            arch = arch.encode('utf-8')
        try:
            return etree.fromstring(arch)
        except etree.XMLSyntaxError as exc:
            _logger.warning("hide.view.nodes: could not parse view arch: %s", exc)
            return None

    def _upsert_node(self, vals):
        """Create a rag.mcp.store.model.nodes row only if no matching row exists.

        Dedup key is (model_id, node_option, button_type, attribute_name, attribute_string).
        """
        Store = self.env['rag.mcp.store.model.nodes']
        domain = [
            ('model_id', '=', vals['model_id']),
            ('node_option', '=', vals['node_option']),
            ('attribute_name', '=', vals.get('attribute_name') or False),
            ('attribute_string', '=', vals.get('attribute_string') or False),
        ]
        if vals.get('button_type'):
            domain.append(('button_type', '=', vals['button_type']))
        existing = Store.search(domain, limit=1)
        if existing:
            if vals.get('is_smart_button') and not existing.is_smart_button:
                existing.is_smart_button = True
            return existing
        return Store.create(vals)

    # ------------------------------------------------------------------
    # Button metadata collection
    # ------------------------------------------------------------------

    def _store_btn_data(self, btn, smart_button=False, smart_button_string=False):
        string_value = self._context.get('string_value') or False
        name = btn.get('string') or string_value
        if smart_button:
            name = smart_button_string
        if not name:
            return
        self._upsert_node({
            'model_id': self.model_id.id,
            'node_option': 'button',
            'attribute_name': btn.get('name'),
            'attribute_string': name,
            'button_type': btn.get('type'),
            'is_smart_button': smart_button,
            'lang_code': self.env.lang,
        })

    def _get_smart_btn_string(self, btn_list, type=False):
        Store = self.env['rag.mcp.store.model.nodes']

        def _get_span_text(span_list):
            parts = [sp.text for sp in span_list if sp.text]
            return ' '.join(parts).strip()

        for btn in btn_list:
            name = ''
            field_list = btn.findall('field')
            if field_list:
                name = field_list[0].get('string') or ''
            else:
                span_list = btn.findall('span')
                if span_list:
                    name = _get_span_text(span_list)
                else:
                    div_list = btn.findall('div')
                    if div_list:
                        name = _get_span_text(div_list[0].findall('span'))
            if not name:
                name = btn.get('string') or ''
            if name and type in ('object', 'action'):
                domain = [
                    ('button_type', '=', btn.get('type')),
                    ('attribute_string', '=', name),
                    ('model_id', '=', self.model_id.id),
                    ('node_option', '=', 'button'),
                    ('attribute_name', '=', btn.get('name')),
                ]
                smart = Store.search(domain, limit=1)
                if not smart:
                    self._store_btn_data(btn, smart_button=True, smart_button_string=name)
                else:
                    smart.is_smart_button = True

    @api.model
    @api.onchange('model_id')
    def _get_button(self):
        view_obj = self.env['ir.ui.view']
        if not (self.model_id and self.model_name):
            return

        model_name = self.model_name
        if model_name not in self.env:
            _logger.warning("hide.view.nodes: model %r is not loaded", model_name)
            return

        # Odoo 17 still uses the 'tree' view type internally.
        for view_type in ('form', 'tree', 'kanban'):
            for view in view_obj.search([('model', '=', model_name), ('type', '=', view_type)]):
                try:
                    res = self.env[model_name].sudo().get_view(view_id=view.id, view_type=view_type)
                except Exception as exc:
                    _logger.warning("hide.view.nodes: get_view(%s, %s) failed: %s", model_name, view_type, exc)
                    continue
                doc = self._parse_view_arch(res.get('arch'))
                if doc is None:
                    continue

                # Kanban links
                for link in doc.xpath("//a[@type and @name]"):
                    text = (link.text or '').strip()
                    if not text or '\n' in text:
                        continue
                    self._upsert_node({
                        'model_id': self.model_id.id,
                        'node_option': 'link',
                        'attribute_name': link.get('name'),
                        'attribute_string': text,
                        'button_type': link.get('type'),
                        'lang_code': self.env.lang,
                    })

                # Object / action buttons
                for btn_type in ('object', 'action'):
                    for btn in doc.xpath("//button[@type=$t]", t=btn_type):
                        string_value = btn.get('string')
                        if view_type == 'kanban' and not string_value:
                            raw = (btn.text or '').strip()
                            if raw and not raw.startswith('\n'):
                                string_value = raw
                        if not string_value and btn_type == 'object':
                            stat_texts = btn.findall(".//*[@class='o_stat_text']")
                            if stat_texts:
                                string_value = ' '.join(f.text for f in stat_texts if f.text).strip() or None
                        if btn.get('name') and string_value:
                            self.with_context(string_value=string_value)._store_btn_data(btn)

                if view_type == 'form':
                    for box in doc.xpath("//div[@class='oe_button_box']"):
                        smt_xml = etree.fromstring(etree.tostring(box))
                        self._get_smart_btn_string(smt_xml.xpath(".//button[@type='object']"), type='object')
                        self._get_smart_btn_string(smt_xml.xpath(".//button[@type='action']"), type='action')

                    for page in doc.xpath("//page"):
                        if not page.get('string'):
                            continue
                        self._upsert_node({
                            'model_id': self.model_id.id,
                            'node_option': 'page',
                            'attribute_name': page.get('name') or False,
                            'attribute_string': page.get('string'),
                            'lang_code': self.env.lang,
                        })

                    if model_name == 'res.config.settings':
                        for app in doc.xpath("//app"):
                            if not app.get('string'):
                                continue
                            self._upsert_node({
                                'model_id': self.model_id.id,
                                'node_option': 'page',
                                'attribute_name': app.get('name') or '',
                                'attribute_string': app.get('string'),
                                'lang_code': self.env.lang,
                            })


class store_model_nodes(models.Model):
    _name = 'rag.mcp.store.model.nodes'
    _description = 'Store Model Nodes'
    _rec_name = 'attribute_string'

    model_id = fields.Many2one('ir.model', string='Model', index=True, ondelete='cascade', required=True)
    node_option = fields.Selection([('button', 'Button'), ('page', 'Page'), ('link', 'Link')], string="Node Option",
                                   required=True)
    attribute_name = fields.Char('Attribute Name')
    attribute_string = fields.Char('Attribute String', required=True, translate=True)
    lang_code = fields.Char("Language Code")
    button_type = fields.Selection([('object', 'Object'), ('action', 'Action')], string="Button Type")
    is_smart_button = fields.Boolean('Smart Button')

    def name_get(self):
        result = []
        for rec in self:
            name = rec.attribute_string or ''
            if rec.attribute_name:
                name = name + ' (' + rec.attribute_name + ')'
                if rec.is_smart_button and rec.node_option == 'button':
                    name = name + ' (Smart Button)'
            result.append((rec.id, name))
        return result
