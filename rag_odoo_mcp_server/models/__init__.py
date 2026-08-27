# -*- coding: utf-8 -*-

from . import models
from . import ir_http
from . import res_config_settings
from . import generate_api_key_wizard
from . import dashboard
from . import oauth
from . import lead_generation_brief
from . import lead_generation_brief_wizard
from . import mailing_campaign_brief
from . import mailing_campaign_brief_wizard

# Access Manager (optional feature) — access-rules enforcement + data models.
# Ported from rag_odoo_mcp_server_access (without its RAG-API chat). These are
# only *used* by the connected LLM when the "Access Manager" setting is on, but
# the models/enforcement load unconditionally so existing access rules keep
# working regardless of the toggle.
from . import action_data
from . import view_data
from . import remove_action
from . import ir_rule
from . import access_management
from . import ir_ui_menu
from . import res_users
from . import ir_actions_actions
from . import hide_field
from . import base_model
from . import ir_model_access
from . import ir_ui_view
from . import access_domain_ah
from . import ir_module_module
from . import hide_view_nodes
from . import hide_filters_groups
from . import ir_model
from . import hide_chatter
from . import menu_item
