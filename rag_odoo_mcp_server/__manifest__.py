# -*- coding: utf-8 -*-
{
    'name': "Claude Connector | RAG Odoo Mcp",

    'summary': "This module will connect and train Claude to interact with your odoo instance. Use it for generating dashboards, create or read any records and much more......",

    'description': """
        Exposes an MCP (Model Context Protocol) server as part of the Odoo HTTP server.
        Claude or other LLM can query and manage your Odoo data using natural language.
        Installing the module is enough — no separate process needed.
        
        Usage Examples
        ---------------------------------------------
        Data retrieval:
          • "Show me all customers from Spain"
          • "Find products with stock below 10 units"
          • "List today's sales orders over $1000"
          • "Search for unpaid invoices from last month"
        Data management:
          • "Create a new customer contact for Acme Corporation"
          • "Add a new product called 'Premium Widget' with price $99.99"
          • "Update the phone number for customer John Doe"
          • "Change the status of order SO/2024/001 to confirmed"
          • "Delete the test contact we created earlier"
        Website SEO (optional "SEO Manager" feature — needs the Website app):
          • "Audit my website's SEO and tell me what to fix first"
          • "Write meta titles and descriptions for every page missing one"
          • "Rename /page-1 to /handmade-ceramic-vases and keep the ranking"
          • "Which pages are excluded from Google, and why?"
          • "Add alt text to the images on the homepage"
            """,

    'author': "RAG Solutions",
    'price': 115.00,
    'currency': 'EUR',
    'website': "https://rag-solutions.cloud/",
    'version': '17.0.1.3.0',
    'license': 'OPL-1',
    'category': 'Uncategorized',

    # web provides ir.http for multi-db URL dispatch. product / crm / mass_mailing
    # (and the crm_iap_mine / mass_mailing_crm bridges) are required by the
    # lead-generation and mailing-campaign "from a brief" feature (brief models
    # inherit crm.lead / mailing.mailing and reference product.template; the Claude
    # brief buttons inherit their list views). They install automatically; the
    # Settings → CRM Manager checkbox controls whether the brief UI and the
    # CRM/mailing MCP tools are actually exposed.
    'depends': ['base', 'web', 'product', 'crm', 'mass_mailing', 'mass_mailing_crm', 'crm_iap_mine'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/dashboard_security.xml',
        'security/crm_manager_security.xml',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/generate_api_key_wizard_views.xml',
        'views/views.xml',
        'views/templates.xml',
        'views/dashboard_views.xml',
        'views/lead_generation_brief_wizard_views.xml',
        'views/lead_generation_brief_views.xml',
        'views/crm_lead_views.xml',
        'views/mailing_campaign_brief_wizard_views.xml',
        'views/mailing_campaign_brief_views.xml',
        'views/mailing_mailing_views.xml',
    ],
    'post_init_hook': '_post_init_fix_body_arch',
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rag_odoo_mcp_server/static/src/js/dashboard_viewer.js',
            'rag_odoo_mcp_server/static/src/xml/dashboard_viewer.xml',
            'rag_odoo_mcp_server/static/src/css/dashboard_viewer.css',
            # Settings: pretty, copy-able MCP client config block.
            'rag_odoo_mcp_server/static/src/js/mcp_config_field.js',
            'rag_odoo_mcp_server/static/src/xml/mcp_config_field.xml',
            'rag_odoo_mcp_server/static/src/css/mcp_config_field.css',
        ],
    },
    'images': [
            'static/description/banner.gif'
    ],
}

