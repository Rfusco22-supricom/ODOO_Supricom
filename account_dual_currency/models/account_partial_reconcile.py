# -*- coding: utf-8 -*-
from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError, ValidationError
import logging

from datetime import date

_logger = logging.getLogger(__name__)


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    company_currency_id_dif = fields.Many2one(
        comodel_name='res.currency',
        string="Company Currency",
        related='company_id.currency_id_dif')

    # ==== Amount fields ====
    amount_usd = fields.Monetary(
        currency_field='company_currency_id_dif',
        help="Always positive amount concerned by this matching expressed in the company currency.",default=0)

    def unlink(self):
        """
        Override para forzar recálculo de payment_state después de romper reconciliación.
        """
        # Guardar las facturas/pagos afectados antes de eliminar
        moves_to_recompute = self.env['account.move']
        for partial in self:
            moves_to_recompute |= partial.debit_move_id.move_id
            moves_to_recompute |= partial.credit_move_id.move_id
        
        # Ejecutar unlink del core
        res = super().unlink()
        
        # Forzar recálculo de payment_state en las facturas afectadas
        moves_to_recompute._compute_amount()
        
        return res

    @api.model
    def _migrate_amount_usd_data(self):
        """
        Migración para actualizar el campo amount_usd en reconciliaciones parciales existentes.
        Esta función se ejecuta automáticamente al actualizar el módulo desde el archivo XML de data.
        """
        _logger.info("=== Iniciando migración de amount_usd en account.partial.reconcile ===")
        
        # Paso 1: Contar registros a actualizar
        self.env.cr.execute("""
            SELECT COUNT(*) 
            FROM account_partial_reconcile 
            WHERE amount_usd = 0 
            AND create_date > '2025-01-01'
        """)
        count_before = self.env.cr.fetchone()[0]
        _logger.info(f"Encontradas {count_before} reconciliaciones parciales con amount_usd = 0")
        
        if count_before == 0:
            _logger.info("No hay registros para migrar. Migración completada.")
            return True
        
        # Paso 2: Actualizar amount_usd en reconciliaciones parciales
        self.env.cr.execute("""
            WITH rates AS (
                SELECT 
                    apr.id as partial_id,
                    apr.amount,
                    COALESCE(
                        CASE WHEN debit_currency.name = 'USD' THEN
                            COALESCE(NULLIF(debit_aml.tax_today, 0), NULLIF(debit_move.tax_today, 0))
                        WHEN credit_currency.name = 'USD' THEN
                            COALESCE(NULLIF(credit_aml.tax_today, 0), NULLIF(credit_move.tax_today, 0))
                        ELSE
                            COALESCE(NULLIF(debit_aml.tax_today, 0), NULLIF(debit_move.tax_today, 0))
                        END,
                        COALESCE(NULLIF(debit_aml.tax_today, 0), NULLIF(debit_move.tax_today, 0)),
                        COALESCE(NULLIF(credit_aml.tax_today, 0), NULLIF(credit_move.tax_today, 0)),
                        1.0
                    ) as rate
                FROM account_partial_reconcile apr
                INNER JOIN account_move_line debit_aml ON apr.debit_move_id = debit_aml.id
                INNER JOIN account_move debit_move ON debit_aml.move_id = debit_move.id
                LEFT JOIN res_currency debit_currency ON debit_aml.currency_id = debit_currency.id
                INNER JOIN account_move_line credit_aml ON apr.credit_move_id = credit_aml.id
                INNER JOIN account_move credit_move ON credit_aml.move_id = credit_move.id
                LEFT JOIN res_currency credit_currency ON credit_aml.currency_id = credit_currency.id
                WHERE apr.amount_usd = 0
                  AND apr.create_date > '2025-01-01'
            )
            UPDATE account_partial_reconcile apr
            SET amount_usd = ABS(rates.amount / NULLIF(rates.rate, 0))
            FROM rates
            WHERE apr.id = rates.partial_id
              AND rates.rate > 0
        """)
        
        count_updated = self.env.cr.rowcount
        _logger.info(f"✓ Actualizadas {count_updated} reconciliaciones parciales")
        
        # Paso 3: Invalidar amount_residual_usd para forzar recálculo
        self.env.cr.execute("""
            UPDATE account_move_line aml 
            SET amount_residual_usd = NULL 
            WHERE aml.account_id IN (
                SELECT id FROM account_account 
                WHERE account_type IN ('asset_receivable', 'liability_payable')
            ) 
            AND EXISTS (
                SELECT 1 FROM account_partial_reconcile apr 
                WHERE apr.debit_move_id = aml.id OR apr.credit_move_id = aml.id
            )
        """)
        
        count_invalidated = self.env.cr.rowcount
        _logger.info(f"✓ Invalidados {count_invalidated} registros de amount_residual_usd para recálculo")
        
        _logger.info("=== Migración de amount_usd completada exitosamente ===")
        return True
