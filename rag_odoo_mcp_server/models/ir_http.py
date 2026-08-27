# -*- coding: utf-8 -*-
"""
Set request.session.db from the ?db= query parameter so multi-db works without db= in odoo.conf.
We set it for every request that has ?db= so the database is bound before any per-db logic runs.
"""

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _dispatch(cls, endpoint):
        """Bind session to db from ?db= for any request, so routing and dispatch see the correct database."""
        if request and getattr(request, 'httprequest', None) and getattr(request, 'session', None):
            db = request.httprequest.args.get('db')
            if db:
                request.session.db = db
        return super()._dispatch(endpoint)
