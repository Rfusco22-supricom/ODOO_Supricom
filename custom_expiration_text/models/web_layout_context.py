# models/web_layout_context.py
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class WebLayoutContext(models.AbstractModel):
    _name = 'web.layout.context'
    _description = 'Web Layout Context'

    @api.model
    def get_lock_date(self):
        self.env.cr.execute("""
            SELECT fiscalyear_lock_date
            FROM res_company
            WHERE id = %s
        """, (self.env.company.id,))
        result = self.env.cr.fetchone()

        if result and result[0]:
            lock_date_str = result[0].strftime('%d/%m/%Y')
            _logger.info(f"[WEB CONTEXT] Fecha de bloqueo: {lock_date_str}")
            return lock_date_str
        _logger.warning("[WEB CONTEXT] No hay fecha de bloqueo establecida")
        return "No hay fecha de bloqueo establecida"