from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to intercept exchange difference creation.
        When partials are created, Odoo may try to create exchange moves.
        """
        _logger.info(f"[PARTIAL-REC-CREATE] Creating partials. Context: no_exchange_difference={self._context.get('no_exchange_difference')}")
        
        # If we're blocking exchange differences, we add a flag to prevent
        # the post-create hook from generating exchange moves
        if self._context.get('no_exchange_difference'):
            self = self.with_context(skip_exchange_diff=True)
        
        result = super().create(vals_list)
        
        _logger.info(f"[PARTIAL-REC-CREATE] Created partials: {result.ids}")
        return result

    def _create_exchange_difference_move(self):
        """
        Override to intercept exchange difference creation during reconciliation.
        If context 'no_exchange_difference' is True, we skip creating the exchange move.
        """
        _logger.info(f"[PARTIAL-REC] _create_exchange_difference_move CALLED on account.partial.reconcile")
        _logger.info(f"[PARTIAL-REC] Context: no_exchange_difference={self._context.get('no_exchange_difference')}, skip_exchange_diff={self._context.get('skip_exchange_diff')}")
        _logger.info(f"[PARTIAL-REC] Self (partials): {self.ids}")
        
        if self._context.get('no_exchange_difference') or self._context.get('skip_exchange_diff'):
            _logger.info("[PARTIAL-REC] BLOCKING exchange diff creation due to context flag.")
            return self.env['account.move']
        
        _logger.info("[PARTIAL-REC] Proceeding with standard exchange diff creation (calling super).")
        return super()._create_exchange_difference_move()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    def reconcile(self):
        """
        Override reconcile to log and pass no_exchange_difference=True context.

        IMPORTANTE: En Odoo 16, si _create_exchange_difference_move() retorna vacío
        DESPUÉS de que se crea el partial principal, el savepoint hace rollback y el
        partial principal también se perde. Para evitar esto, pasamos no_exchange_difference=True
        ANTES de llamar super(), así Odoo 16 sabe desde el inicio que NO debe crear
        asientos de diferencia de cambio, y no hay rollback del partial principal.

        Impacto contable: ninguno. Las diferencias de cambio en el sistema dual-moneda
        (VEF+USD) son manejadas por account_dual_currency vía tax_today, no por el
        mecanismo estándar de Odoo. Bloquear el asiento de diferencia es la intención
        original de este módulo.
        """
        _logger.info(f"[AML-RECONCILE] reconcile() CALLED on account.move.line")
        _logger.info(f"[AML-RECONCILE] Context: no_exchange_difference={self._context.get('no_exchange_difference')}")
        _logger.info(f"[AML-RECONCILE] Lines: {self.ids}")


        # asiento de diferencia de cambio desde el inicio (no intentar y luego bloquear).
        # NOTA: super(AccountMoveLine, self.with_context(...)) es necesario para que
        # Python salte ESTA clase en el MRO. Si usamos super().with_context(...).reconcile(),
        # el resultado es un recordset del mismo tipo → llama nuestro método de nuevo → recursión.
        result = super(AccountMoveLine, self.with_context(no_exchange_difference=True)).reconcile()

        _logger.info(f"[AML-RECONCILE] Reconcile result: {result}")
        return result

    def _reconcile_plan(self, reconcile_plan):
        """
        Override _reconcile_plan which is the internal method that calculates partials.
        """
        _logger.info(f"[AML-RECONCILE-PLAN] _reconcile_plan() CALLED")
        _logger.info(f"[AML-RECONCILE-PLAN] Context: no_exchange_difference={self._context.get('no_exchange_difference')}")
        _logger.info(f"[AML-RECONCILE-PLAN] Plan entries: {len(reconcile_plan) if reconcile_plan else 0}")
        for i, entry in enumerate(reconcile_plan or []):
            _logger.info(f"[AML-RECONCILE-PLAN] Plan[{i}]: {list(entry.keys()) if isinstance(entry, dict) else entry}")

        result = super()._reconcile_plan(reconcile_plan)
        _logger.info(f"[AML-RECONCILE-PLAN] _reconcile_plan() result: {result}")
        return result

    def _prepare_reconciliation_partials(self):
        """
        Override to intercept the preparation of partial reconciliations.
        """
        _logger.info(f"[AML-PREPARE-PARTIALS] _prepare_reconciliation_partials() CALLED")
        _logger.info(f"[AML-PREPARE-PARTIALS] Context: no_exchange_difference={self._context.get('no_exchange_difference')}")

        # Log line amounts to diagnose reconciliation failures
        for line in self:
            _logger.info(
                f"[AML-PREPARE-PARTIALS] Line id={line.id} "
                f"account={line.account_id.code} "
                f"balance={line.balance:.4f} {line.company_currency_id.name} "
                f"amount_currency={line.amount_currency:.4f} {line.currency_id.name} "
                f"amount_residual={line.amount_residual:.4f} "
                f"amount_residual_currency={line.amount_residual_currency:.4f} "
                f"currency_rate={getattr(line, 'currency_rate', 'N/A')}"
            )

        result = super()._prepare_reconciliation_partials()

        _logger.info(f"[AML-PREPARE-PARTIALS] Partials computed: {len(result)} items")
        for p in result:
            _logger.info(f"[AML-PREPARE-PARTIALS] Partial: amount={p.get('amount')} amount_currency={p.get('amount_currency')} debit={p.get('debit_move_id')} credit={p.get('credit_move_id')}")

        return result

    def _prepare_exchange_difference_move_vals(self, amounts, exchange_diff_vals=None, aml_to_fix=None, **kwargs):
        """
        Override to block exchange difference move vals preparation.
        """
        _logger.info(f"[AML-EXCH-VALS] _prepare_exchange_difference_move_vals() CALLED")
        _logger.info(f"[AML-EXCH-VALS] Context: no_exchange_difference={self._context.get('no_exchange_difference')}")
        _logger.info(f"[AML-EXCH-VALS] amounts: {amounts}")
        
        if self._context.get('no_exchange_difference') or self._context.get('skip_exchange_diff'):
            _logger.info("[AML-EXCH-VALS] BLOCKING - returning empty due to context")
            return {}
        
        return super()._prepare_exchange_difference_move_vals(amounts, exchange_diff_vals=exchange_diff_vals, aml_to_fix=aml_to_fix, **kwargs)

