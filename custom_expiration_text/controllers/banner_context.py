from odoo import http
import json

class FiscalBannerController(http.Controller):
    @http.route('/banner/fiscal_date', type='json', auth='user')
    def get_fiscal_lock_date(self):
        lock_date = http.request.env.user.company_id.fiscalyear_lock_date
        return {
            'lock_date_str': lock_date.strftime('%d/%m/%Y') if lock_date else None
        }