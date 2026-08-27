# -*- coding: utf-8 -*-
# from odoo import http


# class RagOdooMcpServer(http.Controller):
#     @http.route('/rag_odoo_mcp_server/rag_odoo_mcp_server', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/rag_odoo_mcp_server/rag_odoo_mcp_server/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('rag_odoo_mcp_server.listing', {
#             'root': '/rag_odoo_mcp_server/rag_odoo_mcp_server',
#             'objects': http.request.env['rag_odoo_mcp_server.rag_odoo_mcp_server'].search([]),
#         })

#     @http.route('/rag_odoo_mcp_server/rag_odoo_mcp_server/objects/<model("rag_odoo_mcp_server.rag_odoo_mcp_server"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('rag_odoo_mcp_server.object', {
#             'object': obj
#         })

