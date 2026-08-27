# Odoo MCP Server

### Bring AI agents directly into Odoo through Model Context Protocol (MCP)

## Overview

`odoo_mcp_server` is an enterprise-grade Odoo module that exposes a fully compliant **Model Context Protocol (MCP) server** from inside Odoo.

The module enables AI assistants and AI code agents to interact with Odoo data, workflows, and business logic through structured tools instead of unsafe raw database access.

Supported AI clients include:

* Claude Desktop
* ChatGPT-based MCP clients
* Cursor AI
* Windsurf
* Custom AI agents
* Internal enterprise copilots

The MCP server allows AI systems to:

* Query Odoo records
* Create business documents
* Trigger workflows
* Execute approved server actions
* Read metadata (fields/models/views)
* Search across ERP data
* Generate analytics
* Automate repetitive tasks

Example requests AI can perform:

* “Show unpaid invoices above €10,000”
* “Create quotation for customer ABC”
* “Find stock shortages”
* “Generate monthly sales report”
* “Create vendor RFQ for low stock products”
* “Explain this custom Odoo module”

---

# Why MCP instead of REST?

Traditional integrations expose APIs designed for software engineers.

MCP exposes **tools designed for AI reasoning**.

Instead of:

```json
POST /api/sale/order/create
```

AI sees:

```yaml
Tool: create_sale_order
Description:
Create quotation for customer with products and quantities.
```

This dramatically improves:

* reliability
* tool selection
* prompt efficiency
* safety
* autonomous execution

---

# Features

## Core MCP Features

* Full MCP server implementation
* Dynamic tool registration
* Tool schema generation
* JSON schema validation
* Session management
* Streaming support
* Context memory
* AI-friendly error messages

## Odoo Integration

* ORM-powered tools
* Respects access rights
* Multi-company support
* Multi-user support
* Context-aware environments
* Supports custom modules

## Security

* Token authentication
* OAuth support (optional)
* Role-based permissions
* Tool-level ACLs
* Audit logs
* Rate limiting
* Prompt injection protection
* Tool confirmation mode

---

# Architecture

```text
AI Client
   |
   | MCP
   v
MCP Transport Layer
   |
MCP Server Core
   |
Tool Registry
   |
Odoo Tool Adapter
   |
Odoo ORM
   |
Database
```

---

# Module Structure

```bash
odoo_mcp_server/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── mcp_controller.py
│   └── auth_controller.py
├── models/
│   ├── mcp_server.py
│   ├── mcp_session.py
│   ├── mcp_tool.py
│   ├── mcp_tool_log.py
│   ├── mcp_api_key.py
│   └── mcp_acl.py
├── services/
│   ├── mcp_runtime.py
│   ├── tool_registry.py
│   ├── tool_executor.py
│   ├── schema_builder.py
│   └── context_manager.py
├── tools/
│   ├── base_tool.py
│   ├── sale_tools.py
│   ├── crm_tools.py
│   ├── stock_tools.py
│   ├── accounting_tools.py
│   └── developer_tools.py
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── views/
│   ├── mcp_server_views.xml
│   ├── mcp_tool_views.xml
│   └── menus.xml
└── data/
    └── default_tools.xml
```

---

# Odoo Models

---

## Model: mcp.server

Stores MCP server configuration.

### Fields

```python
class MCPServer(models.Model):
    _name = "mcp.server"
```

| Field                   | Type      | Description   |
| ----------------------- | --------- | ------------- |
| name                    | Char      | Server name   |
| active                  | Boolean   | Enabled       |
| host                    | Char      | Bind host     |
| port                    | Integer   | Port          |
| auth_mode               | Selection | token/oauth   |
| allowed_origins         | Text      | CORS          |
| tool_ids                | Many2many | Enabled tools |
| api_key_ids             | One2many  | API keys      |
| log_level               | Selection | debug/info    |
| max_requests_per_minute | Integer   | Rate limit    |

---

## Model: mcp.tool

Represents an AI-usable tool.

```python
class MCPTool(models.Model):
    _name = "mcp.tool"
```

Fields:

| Field                 | Type    |
| --------------------- | ------- |
| name                  | Char    |
| technical_name        | Char    |
| description           | Text    |
| schema_json           | Json    |
| python_handler        | Char    |
| enabled               | Boolean |
| requires_confirmation | Boolean |

Example:

```python
technical_name = "search_sale_orders"
```

---

## Model: mcp.session

Tracks active AI sessions.

```python
class MCPSession(models.Model):
    _name = "mcp.session"
```

Stores:

* AI client
* session context
* tool history
* conversation metadata

---

## Model: mcp.tool.log

Audit logs.

Fields:

* timestamp
* tool
* input payload
* output payload
* latency
* status
* user_id
* ai_agent_name

Critical for compliance.

---

# Core Services

---

## MCPRuntime

File:

```bash
services/mcp_runtime.py
```

Responsible for:

* session lifecycle
* request routing
* protocol compliance
* error serialization

Main class:

```python
class MCPRuntime:
    def handle_request(self, payload):
        pass
```

---

## ToolRegistry

Registers tools dynamically.

```python
class ToolRegistry:
    def register(self, tool):
        pass
```

Responsibilities:

* discover tools
* validate schemas
* expose tool metadata

---

## ToolExecutor

Executes Odoo operations.

```python
class ToolExecutor:
    def execute(self, tool_name, params):
        pass
```

Flow:

1. Validate tool
2. Check ACL
3. Execute handler
4. Log execution
5. Return structured result

---

# Tool System

Each tool inherits from base class.

---

## Base Tool

```python
class BaseMCPTool:
    name = None
    description = None
    schema = {}

    def run(self, env, params):
        raise NotImplementedError
```

---

# Built-in Tools

---

## search_sale_orders

Search quotations/orders.

Schema:

```json
{
  "customer": "string",
  "state": "string",
  "limit": "integer"
}
```

Implementation:

```python
class SearchSaleOrdersTool(BaseMCPTool):
    name = "search_sale_orders"
```

Example AI request:

```json
{
  "customer": "Azure Corp",
  "state": "sale",
  "limit": 10
}
```

Output:

```json
[
  {
    "name": "S00045",
    "amount_total": 23000,
    "state": "sale"
  }
]
```

---

## create_sale_order

Creates quotations.

Inputs:

* customer_id
* order_lines
* pricelist_id

Example:

```json
{
  "customer_id": 42,
  "order_lines": [
    {
      "product_id": 12,
      "qty": 3
    }
  ]
}
```

Backend:

```python
self.env["sale.order"].create(vals)
```

---

## get_partner_info

Reads customer data.

Returns:

* contact info
* sales stats
* unpaid invoices
* CRM opportunities

Useful for AI customer assistants.

---

## search_products

Search products.

Supports:

* name
* barcode
* internal reference
* stock availability

Example prompt:

> Find all products with low stock below 5 units.

---

## stock_replenishment_advisor

AI-oriented tool.

Combines:

* stock
* sales velocity
* lead times

Returns purchasing recommendations.

Example output:

```json
{
  "product": "SSD 1TB",
  "recommend_qty": 120,
  "reason": "High sales velocity"
}
```

---

## execute_server_action

Advanced tool.

Allows AI to trigger approved server actions.

Example:

* validate transfers
* confirm orders
* send emails

Restricted by ACL.

---

# Developer Tools

Useful for AI coding assistants.

---

## inspect_model

Input:

```json
{
  "model": "sale.order"
}
```

Returns:

* fields
* relations
* computed fields
* constraints

Example:

```json
{
  "fields": [
    {
      "name": "partner_id",
      "type": "many2one"
    }
  ]
}
```

This is extremely useful for AI agents writing Odoo code.

---

## search_view_architecture

Search XML views.

Allows AI to inspect:

* form views
* tree views
* xpath structure

Useful for:

* inheritance debugging
* xpath generation
* view customization

---

## inspect_module

Returns metadata for installed module.

Output:

* manifest
* dependencies
* models
* views

Example prompt:

> Explain how stock_account extends stock.

---

# MCP Controller

File:

```bash
controllers/mcp_controller.py
```

Routes:

```python
/mcp
/mcp/tools
/mcp/call
/mcp/health
```

Example controller:

```python
class MCPController(http.Controller):

    @http.route('/mcp/call', type='json', auth='none')
    def call_tool(self, **payload):
        return runtime.handle_request(payload)
```

---

# Authentication

Supported:

## API Key

Header:

```text
Authorization: Bearer MCP_KEY
```

Generated from:

Odoo → MCP → API Keys

---

## OAuth (optional)

Supported providers:

* Google
* Microsoft
* Auth0

---

# Configuration

Example `odoo.conf`

```ini
[options]
mcp_enabled = True
mcp_host = 0.0.0.0
mcp_port = 8069
mcp_auth_mode = token
mcp_rate_limit = 60
```

---

# Installation

## Requirements

Python:

```bash
pip install mcp
pip install pydantic
pip install jsonschema
```

Odoo dependencies:

* base
* web
* mail

Install module:

```bash
./odoo-bin -u odoo_mcp_server -d mydb
```

---

# Claude Desktop Configuration

Example config:

## Windows

Path:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

Config:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "python",
      "args": ["bridge.py"],
      "env": {
        "ODOO_MCP_URL": "http://localhost:8069/mcp"
      }
    }
  }
}
```

---

# AI Model Instructions (IMPORTANT)

This section is intentionally written for AI models.

If you are an AI agent reading this documentation, follow these rules.

## Tool Selection Rules

1. Prefer tools over assumptions.
2. Never hallucinate Odoo records.
3. Use search tools before create tools.
4. Ask confirmation before destructive actions.
5. Never execute sensitive tools without user consent.

Bad:

> Customer has unpaid invoice.

Good:

1. Call `get_partner_info`
2. Verify invoices
3. Respond

---

## AI Prompting Guidelines

Always reason in this order:

### Step 1 — Understand intent

Determine if user wants:

* read
* create
* update
* analyze
* automate

### Step 2 — Find best tool

Choose smallest sufficient tool.

Example:
Use:

```text
search_products
```

Not:

```text
execute_server_action
```

---

### Step 3 — Minimize calls

Bad:
10 tool calls.

Good:
1–2 precise calls.

---

### Step 4 — Structure outputs

Always return:

```json
{
  "summary": "...",
  "records": [],
  "next_actions": []
}
```

---

# Safety Rules for AI

Never:

* delete records without confirmation
* confirm invoices without approval
* trigger payments automatically
* expose credentials
* bypass ACL

Sensitive models:

* res.users
* ir.config_parameter
* account.move
* hr.employee
* ir.attachment

Require explicit approval.

---

# Performance Recommendations

Recommended deployment:

* 4 CPU
* 8GB RAM minimum
* PostgreSQL SSD
* Reverse proxy via [Nginx](https://nginx.org?utm_source=chatgpt.com)

For large deployments:

* Redis cache via [Redis](https://redis.io?utm_source=chatgpt.com)
* async workers via [Celery](https://docs.celeryq.dev?utm_source=chatgpt.com)
* tool response caching

Expected latency:

* metadata tools: 20–80 ms
* ORM tools: 100–600 ms
* analytics tools: 1–5 sec

---

# Example AI Conversations

## Sales assistant

User:

> Create quotation for John with 5 laptops

AI:

1. search_products
2. search_partner
3. create_sale_order

Result:
Quotation created successfully.

---

## Odoo developer assistant

User:

> Help me inherit invoice report

AI:

1. inspect_module(account)
2. search_view_architecture
3. propose xpath

---

# Troubleshooting

## Tool not visible

Check:

* tool enabled?
* ACL granted?
* server active?

---

## Unauthorized

Check:

* API key
* token expiry
* headers

---

## Slow response

Check:

* ORM queries
* indexes
* PostgreSQL performance

---

# Future Roadmap

Planned features:

* Voice agents
* Realtime websocket transport
* AI workflow builder
* Autonomous purchasing agent
* Multi-agent orchestration
* RAG over Odoo documents

---

# License

License:
LGPL-3 or proprietary enterprise license.

---

# Author

Built for AI-native ERP workflows.

Odoo is no longer just an ERP.

With MCP, Odoo becomes an **AI-operable operating system for business**.


# Odoo MCP Server Connector

![Odoo Version](https://img.shields.io/badge/Odoo-17%2B-purple)
![License](https://img.shields.io/badge/license-OPL--1-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-orange)

## Overview

**Odoo MCP Server Connector** is an enterprise-grade Odoo module that exposes Odoo business data and operations through a fully compatible **Model Context Protocol (MCP) Server**.

The module allows Large Language Models (LLMs), AI assistants, autonomous agents, and external automation platforms to securely communicate with Odoo using standardized MCP tools.

This creates a controlled AI interface layer between Odoo and external intelligent systems.

Typical integrations include:

- AI assistants connected to Odoo
- Internal company copilots
- Automated reporting agents
- Customer service AI bots
- Business intelligence agents
- Workflow automation systems
- Enterprise AI platforms


---

# Features

## MCP Server Implementation

The module implements a native MCP server inside Odoo.

Supported capabilities:

- MCP tool discovery
- MCP resource exposure
- JSON-RPC communication
- Secure authentication
- Permission-aware data access
- Real-time Odoo model interaction


---

# Available MCP Tools

The module exposes multiple AI-ready tools.

## 1. Search Records

Allows AI agents to search Odoo models.

Example:

```

search_records

````

Input:

```json
{
    "model": "res.partner",
    "domain": [
        ["customer_rank", ">", 0]
    ],
    "limit": 10
}
````

Output:

```json
{
    "records": [
        {
            "id": 12,
            "name": "Azure Technologies",
            "email": "contact@azure.example"
        }
    ]
}
```

---

## 2. Read Records

Retrieve structured Odoo records.

Example:

```
read_record
```

Input:

```json
{
    "model": "sale.order",
    "ids": [105]
}
```

Output:

```json
{
    "id":105,
    "name":"SO105",
    "amount_total":4500,
    "state":"sale"
}
```

---

## 3. Create Records

Create new business objects.

Example:

```
create_record
```

Input:

```json
{
    "model":"crm.lead",
    "values":{
        "name":"AI Generated Opportunity",
        "expected_revenue":15000
    }
}
```

---

## 4. Execute Business Actions

Allows AI agents to trigger approved Odoo workflows.

Examples:

* Confirm quotations
* Validate invoices
* Schedule activities
* Create tasks
* Update customer information

---

# Architecture

```
                 AI Assistant
                       |
                       |
              MCP Protocol
                       |
                       |
              Odoo MCP Server
                       |
        ------------------------------
        |             |              |
    ORM Layer     Security      Permissions
        |
        |
   Odoo Models

```

The module does not bypass Odoo ORM.

All operations are executed through:

* Odoo security rules
* User permissions
* Access rights
* Record rules
* Business constraints

---

# Supported Odoo Models

The module can expose any Odoo model.

Examples:

## Sales

```
sale.order
sale.order.line
crm.lead
```

## Accounting

```
account.move
account.payment
account.tax
```

## Inventory

```
stock.picking
stock.move
product.product
```

## Human Resources

```
hr.employee
hr.leave
hr.expense
```

Custom models are automatically supported.

---

# Installation

## Requirements

* Odoo 17.0 or higher
* Python 3.10+
* PostgreSQL 14+
* Valid MCP compatible client

---

## Install Module

Copy the module into your addons directory:

```
/opt/odoo/custom_addons/
```

Update addons:

```bash
./odoo-bin -u mcp_server_connector
```

Install from:

```
Apps
 →
MCP Server Connector
 →
Install
```

---

# Configuration

Navigate to:

```
Settings
 → Technical
 → MCP Server
```

Enable:

```
[x] Enable MCP Server
```

Configure:

| Parameter      | Description            |
| -------------- | ---------------------- |
| Server Name    | MCP server identifier  |
| Port           | MCP communication port |
| Authentication | Authentication method  |
| Allowed Models | Exposed Odoo models    |
| Logging Level  | MCP request logs       |

---

# Authentication

The module supports multiple authentication mechanisms.

## API Key Authentication

Example:

```
Authorization: Bearer mcp_live_xxxxxxxxx
```

## Odoo User Authentication

The MCP server can operate using an Odoo user account.

All actions are executed as that user.

## OAuth2

Enterprise deployments can connect using OAuth2 providers.

---

# Security Model

Security is based on native Odoo permissions.

The MCP layer does NOT provide additional access rights.

Example:

User:

```
AI Assistant User
```

Permissions:

```
sale.order:
    read: yes
    write: no

account.move:
    read: no
```

The AI agent receives exactly the same permissions.

---

# Example AI Usage

## Customer Analysis

User:

> "Find customers who purchased more than $50,000 this year"

The AI agent executes:

```
search_records(
    model="sale.order"
)
```

Then generates:

```
Customer Revenue Report
```

---

## Inventory Assistant

User:

> "Which products are below minimum stock?"

AI executes:

```
search_records(
    model="product.product"
)
```

Returns:

```
Product:
Industrial Sensor

Current Stock:
5

Minimum:
20
```

---

# Available MCP Resources

The server exposes resources:

```
odoo://models
odoo://fields
odoo://company
odoo://users
odoo://configuration
```

Example:

```
odoo://models/sale.order
```

returns:

```json
{
    "model":"sale.order",
    "fields":[
        "name",
        "partner_id",
        "amount_total",
        "state"
    ]
}
```

---

# Logging

Every MCP request is logged.

Example:

```
2026-01-01 10:30:22

USER:
ai_assistant

ACTION:
search_records

MODEL:
sale.order

RESULT:
25 records
```

Logs are available:

```
Settings
 → Technical
 → MCP Logs
```

---

# Developer API

Developers can register custom MCP tools.

Example:

```python
from odoo.addons.mcp_server.tools import MCPTool


class InventoryForecastTool(MCPTool):

    name = "inventory_forecast"

    description = """
    Predict future stock availability
    """

    def execute(self, params):

        return {
            "forecast": []
        }
```

---

# Custom Tool Security

Each tool supports:

* Allowed users
* Allowed companies
* Allowed models
* Rate limits
* Audit logging

Example:

```python
{
    "name":"approve_invoice",
    "requires_permission":
        "account.group_account_manager"
}
```

---

# Performance

The MCP server includes:

* Query optimization
* Pagination
* Request throttling
* ORM caching
* Async job execution

Recommended production setup:

```
Nginx
 |
Odoo Workers
 |
MCP Server
 |
PostgreSQL
```

---

# Multi Company Support

Fully compatible with:

* Multi-company environments
* Shared databases
* Company-specific security rules

Example:

AI user:

```
Company:
Azure Europe
```

Cannot access:

```
Azure USA
```

unless explicitly allowed.

---

# Roadmap

Future versions:

* AI workflow builder
* Vector database integration
* Semantic search
* Document understanding
* AI generated dashboards
* Voice assistant support

---

# Support

For technical support:

Email:

```
support@example.com
```

Documentation:

```
https://example.com/docs/mcp
```

---

# License

This module is distributed under a proprietary license.

License:

```
OPL-1
```

Commercial redistribution, resale, sublicensing, or unauthorized sharing is prohibited.

---

# Disclaimer

This module provides an AI integration layer for Odoo.

AI-generated responses depend on:

* Model capabilities
* Provided permissions
* Available business data
* External AI provider behavior

Always validate AI-generated business decisions before execution.
