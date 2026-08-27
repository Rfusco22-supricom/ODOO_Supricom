from odoo import models, _, api, fields
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    # Campo computado para mostrar diferenciales cambiarios asociados a esta factura
    exchange_differential_move_ids = fields.Many2many(
        'account.move',
        compute='_compute_exchange_differential_moves',
        string='Diferenciales Cambiarios',
        store=False,
    )
    exchange_differential_count = fields.Integer(
        compute='_compute_exchange_differential_moves',
        string='# Diferenciales',
        store=False,
    )
    exchange_differential_widget = fields.Text(
        compute='_compute_exchange_differential_moves',
        string='Diferenciales Cambiarios',
        store=False,
    )

    @api.depends('name', 'state')
    def _compute_exchange_differential_moves(self):
        for move in self:
            if move.name and move.name != '/' and move.state == 'posted':
                exchange_journal = move.company_id.currency_exchange_journal_id
                if exchange_journal:
                    # Buscar asientos con referencia que contenga el nombre de esta factura
                    exchange_moves = self.env['account.move'].search([
                        ('ref', 'ilike', move.name),
                        ('journal_id', '=', exchange_journal.id),
                        ('state', '=', 'posted'),
                        ('id', '!=', move.id),  # Excluir la factura misma
                    ])
                    move.exchange_differential_move_ids = exchange_moves
                    move.exchange_differential_count = len(exchange_moves)
                    
                    # Generar HTML widget estilo Odoo
                    if exchange_moves:
                        html_parts = []
                        for exch_move in exchange_moves:
                            amount = exch_move.amount_total_signed
                            # Determinar si es ganancia o pérdida
                            is_gain = amount >= 0
                            color = '#28a745' if is_gain else '#dc3545'
                            icon = 'fa-arrow-up' if is_gain else 'fa-arrow-down'
                            label = '' if is_gain else ''
                            
                            # Formatear monto
                            formatted_amount = '{:,.2f}'.format(abs(amount))
                            
                            html_parts.append(f'''
<div style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; margin: 4px 0; background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); border-radius: 8px; border: 1px solid #e9ecef; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
    <a href="/web#id={exch_move.id}&amp;model=account.move&amp;view_type=form" 
       style="color: #495057; text-decoration: none; font-weight: 500; display: flex; align-items: center; gap: 8px;"
       title="Ver asiento">
        <span style="display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: {color}20; border-radius: 6px;">
            <i class="fa {icon}" style="color: {color}; font-size: 12px;"></i>
        </span>
        <span>{exch_move.name}</span>
    </a>
    <div style="text-align: right;">
        <div style="color: {color}; font-weight: 600; font-size: 14px;">{formatted_amount} Bs.F</div>
        <div style="color: #6c757d; font-size: 11px;">{label}</div>
    </div>
</div>''')
                        move.exchange_differential_widget = ''.join(html_parts)
                    else:
                        move.exchange_differential_widget = False
                else:
                    move.exchange_differential_move_ids = self.env['account.move']
                    move.exchange_differential_count = 0
                    move.exchange_differential_widget = False
            else:
                move.exchange_differential_move_ids = self.env['account.move']
                move.exchange_differential_count = 0
                move.exchange_differential_widget = False

    def _create_exchange_difference_move(self, exchange_diff_vals):
        """ 
        Override to prevent recursive exchange difference generation.
        If the move triggering the exchange diff is ALREADY an exchange diff (from our exclusive journal),
        we skip the generation of a new one.
        """
        _logger.info(f"[EXCH-DIFF-OVERRIDE] _create_exchange_difference_move CALLED!")
        _logger.info(f"[EXCH-DIFF-OVERRIDE] Context: no_exchange_difference={self._context.get('no_exchange_difference')}")
        _logger.info(f"[EXCH-DIFF-OVERRIDE] exchange_diff_vals: {exchange_diff_vals}")
        
        # Check if we are dealing with our custom exchange journal
        journal_id = exchange_diff_vals.get('journal_id')
        if journal_id:
            journal = self.env['account.journal'].browse(journal_id)
            _logger.info(f"[EXCH-DIFF-OVERRIDE] Journal: {journal.name}, exclude_from_dual_currency={journal.exclude_from_dual_currency}")
            
        # If context flag is present, skip creation
        if self._context.get('no_exchange_difference'):
            _logger.info("[EXCH-DIFF-OVERRIDE] BLOCKING exchange diff creation due to context flag.")
            return self.env['account.move']
            
        _logger.info("[EXCH-DIFF-OVERRIDE] Proceeding with standard exchange diff creation (calling super).")
        return super()._create_exchange_difference_move(exchange_diff_vals)
        
    def action_open_payment_split_wizard(self):
        """ Abre el wizard de asignación avanzada """
        # Soporte para multi-selección
        if not self:
             raise UserError(_("No se han seleccionado facturas."))

        # 1. Validar Mensaje: Mismo Partner
        partners = self.mapped('partner_id')
        if len(partners) > 1:
            raise UserError(_("Todas las facturas seleccionadas deben pertenecer al mismo cliente/proveedor."))
        
        # 2. Validar Estado
        if any(m.state != 'posted' for m in self):
             raise UserError(_("Solo se pueden procesar facturas publicadas."))

        # 3. Preparar Contexto
        ctx = dict(self.env.context)
        ctx.update({
            'default_invoice_id': self[0].id, # Principal (legacy fallback)
            'default_partner_id': partners[0].id,
            'default_company_id': self[0].company_id.id,
            'default_selected_invoice_ids': self.ids, # Nueva lista de IDs explícitos
        })

        return {
            'name': _('Asignación Avanzada de Pagos'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.split.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx
        }

    def action_open_apply_diff_wizard(self):
        """ Abre el wizard para aplicar diferencial cambiario manual """
        self.ensure_one()
        return {
            'name': _('Aplicar Diferencial Cambiario'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.apply.exchange.diff.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
                'default_company_id': self.company_id.id,
            }
        }
    
class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    def unlink(self):
        """
        Al eliminar una conciliación parcial (desconciliar), buscamos si existe
        un asiento de diferencial cambiario MANUAL creado por nuestro wizard
        y lo eliminamos también.
        Identificamos el asiento buscando el tag [partial_id:ID] en su referencia.
        """
        # Obtenemos los IDs antes de llamar a super, por si acaso
        partial_ids = self.ids
        
        # Llamamos a super primero (o despues? Mejor antes para asegurar que no hay bloqueos, 
        # pero si borramos el partial, el tag sigue existiendo en el move).
        # Vamos a buscar los moves ANTES de borrar nada.
        
        moves_to_remove = self.env['account.move']
        for pid in partial_ids:
            # Busqueda estricta por string en referencia
            tag = f"[partial_id:{pid}]"
            linked_moves = self.env['account.move'].search([
                ('ref', 'ilike', tag),
                ('move_type', '=', 'entry'),
                ('state', '!=', 'cancel') # Solo si no está cancelado ya
            ])
            if linked_moves:
                _logger.info(f"[PARTIAL-UNLINK] Found Manual Exchange Move(s) for Partial {pid}: {linked_moves.ids}. Removing...")
                moves_to_remove += linked_moves
        
        # Eliminamos (Revertimos) los asientos encontradoss
        if moves_to_remove:
            # Primero desconciliamos cualquier linea de ese asiento (la linea contra la factura)
            for move in moves_to_remove:
                # Romper conciliaciones de sus lineas
                move.line_ids.remove_move_reconcile()
            
            # Ahora borradores y cancelar
            moves_to_remove.button_draft()
            moves_to_remove.button_cancel()
            moves_to_remove.unlink()

        return super(AccountPartialReconcile, self).unlink()