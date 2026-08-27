# -*- coding: utf-8 -*-

from odoo import models, api

class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def _prepare_default_reversal(self, move):
        """
        Sobrescribe la preparación de valores por defecto para la reversión
        para asegurar que se copie la tasa de cambio original y la configuración 
        de TRM manual del movimiento origen.
        """
        res = super(AccountMoveReversal, self)._prepare_default_reversal(move)
        
        # Copiar campos de moneda dual si existen en el movimiento original
        if hasattr(move, 'tax_today'):
            res.update({
                'tax_today': move.tax_today,
                'edit_trm': True, # Forzar TRUE para evitar que se recalcule por fecha
            })
            
        if hasattr(move, 'currency_id_dif'):
            res.update({
                'currency_id_dif': move.currency_id_dif.id,
            })
            
        return res
