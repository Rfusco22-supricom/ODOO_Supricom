# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class DigiflexCxcBannerController(http.Controller):

    @http.route('/digiflex_cxc_odoo/export_banner', type='json', auth='user')
    def get_export_banner(self, **kwargs):
        return {
            'html': """
                <div class="alert alert-info d-flex align-items-center justify-content-between p-3 m-0 border-0 rounded-0" style="background: linear-gradient(135deg, #1F4E78 0%, #2F5597 100%); color: white;">
                    <div class="d-flex align-items-center">
                        <i class="fa fa-file-excel-o fa-2x me-3" style="color: #28a745;"></i>
                        <div>
                            <strong class="fs-6" style="color: #FFFFFF;">Exportación de Cuentas por Cobrar</strong>
                            <div class="small opacity-75" style="color: #E0E0E0;">Descargue directamente el reporte en Excel respetando los filtros y búsquedas aplicadas en pantalla.</div>
                        </div>
                    </div>
                    <div>
                        <button type="object" name="action_export_excel" class="btn btn-success fw-bold px-4 py-2 shadow-sm text-white o_btn_export_cxc_excel">
                            <i class="fa fa-download me-1"></i> Exportar a Excel
                        </button>
                    </div>
                </div>
            """
        }

    @http.route('/digiflex_cxc_odoo/export_excel', type='http', auth='user')
    def export_excel(self, **kwargs):
        action_res = request.env['digiflex.cxc.report'].action_export_excel()
        if isinstance(action_res, dict) and action_res.get('type') == 'ir.actions.act_url':
            return request.redirect(action_res.get('url'))
        return request.redirect('/web#action=digiflex_cxc_odoo.action_digiflex_cxc_report')
