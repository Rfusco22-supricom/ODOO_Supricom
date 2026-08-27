from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    is_usd_invoice = fields.Boolean(compute='_compute_is_usd_invoice')

    # Detectar si es empresa USD (9 o 10)
    is_usd_company = fields.Boolean(compute='_compute_is_usd_company')

    homologacion_activa = fields.Boolean(
        related='company_id.homologacion_activa',
        string='Homologación Activa'
    )
    
    is_ve_company = fields.Boolean(
        related='company_id.is_ve_company',
        string='Empresa VE'
    )
    
    is_cash_payment_term = fields.Boolean(related='invoice_payment_term_id.is_cash_payment', store=True)
    amount_pay_usd = fields.Monetary(string='Monto a pagar en $', currency_field='currency_id')
    partial_amount_bs = fields.Monetary(string='Monto parcial en Bs', currency_field='company_currency_id')

    @api.constrains('sin_cred', 'vat_apply')
    def _check_fiscal_exclusion_homologacion(self):
        for move in self:
            if move.company_id.homologacion_activa and move.company_id.is_ve_company:
                if move.sin_cred:
                    raise UserError(_(
                        "Restricción Fiscal (Homologación): En una empresa homologada no se puede "
                        "excluir un documento del libro fiscal. Desmarque la opción "
                        "'Excluir este documento del libro fiscal' para continuar."
                    ))
                if hasattr(move, 'vat_apply') and move.vat_apply:
                    raise UserError(_(
                        "Restricción Fiscal (Homologación): En una empresa homologada no se puede "
                        "excluir un documento de la retención de IVA. Desmarque la opción "
                        "'Excluir este documento de la retención de IVA' para continuar."
                    ))

    @api.depends('currency_id')
    def _compute_is_usd_invoice(self):
        for move in self:
            move.is_usd_invoice = move.currency_id.name == 'USD'
    
    @api.depends('company_id')
    def _compute_is_usd_company(self):
        """Detecta si la empresa es 9 o 10 (empresas USD)"""
        for move in self:
            move.is_usd_company = move.company_id.id in [9, 10]
    
    @api.onchange('amount_pay_usd', 'tax_today', 'amount_total', 'is_cash_payment_term')
    def _onchange_amount_pay_usd(self):
        """Auto-calcula el monto parcial en Bs cuando se ingresa el monto en USD"""
        for move in self:
            if move.is_cash_payment_term and move.amount_pay_usd and move.amount_total and move.tax_today:
                # Calcular cuánto falta en USD
                remaining_usd = move.amount_total - move.amount_pay_usd
                # Convertir a Bs usando la tasa del día
                move.partial_amount_bs = remaining_usd * move.tax_today
    
    
    # Sobrescribir Número de Control para asegurar que sea readonly en la vista
    # ya lo es en el manifest pero por seguridad lo reforzamos aquí
    nro_ctrl = fields.Char(copy=False)

    @api.constrains('nro_ctrl')
    def _check_nro_ctrl_unique(self):
        for move in self:
            if not move.company_id.homologacion_activa or not move.company_id.is_ve_company:
                continue
            if move.nro_ctrl:
                # Caso Ventas: Unicidad absoluta por compañía
                if move.move_type in ['out_invoice', 'out_refund']:
                    duplicates = self.search([
                        ('nro_ctrl', '=', move.nro_ctrl),
                        ('id', '!=', move.id),
                        ('company_id', '=', move.company_id.id),
                        ('move_type', 'in', ['out_invoice', 'out_refund'])
                    ])
                    if duplicates:
                        raise UserError(_("Restricción Fiscal (Homologación): El número de control %s ya existe en otro documento de venta.") % move.nro_ctrl)
                
                # Caso Compras (CP-08): Unicidad por compañía Y por proveedor
                elif move.move_type in ['in_invoice', 'in_refund'] and move.partner_id:
                    duplicates = self.search([
                        ('nro_ctrl', '=', move.nro_ctrl),
                        ('id', '!=', move.id),
                        ('company_id', '=', move.company_id.id),
                        ('partner_id', '=', move.partner_id.id),
                        ('move_type', 'in', ['in_invoice', 'in_refund']),
                        ('state', '!=', 'cancel') # Ignorar cancelados
                    ])
                    if duplicates:
                        raise UserError(_("Restricción Fiscal (Homologación): El número de control %s ya existe en otra factura de este proveedor (%s).") % (move.nro_ctrl, move.partner_id.name))

    def write(self, vals):
        # Validar pagos de contado ANTES de guardar (solo facturas de cliente)
        for move in self:
            if not move.company_id.homologacion_activa or not move.company_id.is_ve_company:
                continue
            # Solo aplicar a facturas de cliente (out_invoice, out_refund)
            if move.move_type in ['out_invoice', 'out_refund']:
                # Si se está actualizando amount_pay_usd, partial_amount_bs, o cambiando a estado posted
                should_validate = (
                    move.is_cash_payment_term and 
                    ('amount_pay_usd' in vals or 'partial_amount_bs' in vals or vals.get('state') == 'posted')
                )
                
                if should_validate:
                    # Obtener valores actuales o nuevos
                    amount_pay_usd = vals.get('amount_pay_usd', move.amount_pay_usd)
                    partial_amount_bs = vals.get('partial_amount_bs', move.partial_amount_bs)
                    
                    # Si es pago de contado, el monto en USD es obligatorio
                    if not amount_pay_usd or amount_pay_usd == 0:
                        raise UserError(_(
                            "Error en Pago de Contado: Debe ingresar el monto a pagar en USD.\n\n"
                            "El campo 'Monto a pagar en $' es obligatorio para términos de pago de contado."
                        ))
                    
                    # Convertir el monto en USD a Bs
                    amount_usd_in_bs = amount_pay_usd * (move.tax_today or 1.0)
                    # Sumar con el monto parcial en Bs
                    total_payment_bs = amount_usd_in_bs + (partial_amount_bs or 0.0)
                    # Total de la factura en Bs
                    total_invoice_bs = move.amount_total * (move.tax_today or 1.0)
                    
                    # Validar con un margen de error de 0.01 Bs (por redondeos)
                    if abs(total_payment_bs - total_invoice_bs) > 0.01:
                        raise UserError(_(
                            "Error en Pago de Contado: El monto total de pago no coincide con el total de la factura.\n\n"
                            "Monto en $ (convertido a Bs): %s\n"
                            "Monto parcial en Bs: %s\n"
                            "Total pagado: %s Bs\n"
                            "Total factura: %s Bs\n\n"
                            "La diferencia debe ser menor a 0.01 Bs"
                        ) % (
                            '{:,.2f}'.format(amount_usd_in_bs),
                            '{:,.2f}'.format(partial_amount_bs or 0.0),
                            '{:,.2f}'.format(total_payment_bs),
                            '{:,.2f}'.format(total_invoice_bs)
                        ))
        
        # Validación de restricciones fiscales para documentos posteados
        # Lista de campos técnicos o de seguimiento que Odoo actualiza automáticamente
        # y que no deben disparar el bloqueo de inalterabilidad.
        technical_fields = {
            'message_main_attachment_id', 'message_follower_ids', 'message_ids',
            'activity_ids', 'access_token', 'is_move_sent', 'invoice_has_outstanding',
            'message_has_error', 'message_unread', 'message_needaction',
            'print_count', 'invoice_template_dual_printed', # Especiales de forma_libre
            'amount_residual', 'amount_residual_signed', 'amount_residual_usd',
            'payment_state', 'tax_today', 'needed_terms_dirty',
            'nro_ctrl', # Permitir escritura del nro de control por el sistema
            'issue_fb_id', 'check_fiscal', # Permitir corrección de estos campos en publicado
            'fb_id', # Permitir asignación automática a libro fiscal
            'exchange_differential_widget' # Widget de diferencial cambiario (computado)
        }

        for move in self:
            if move.company_id.homologacion_activa and move.company_id.is_ve_company and move.state == 'posted' and move.move_type in ['out_invoice', 'out_refund'] and not self.env.context.get('skip_fiscal_lock'):
                # Si el campo en vals es nro_ctrl y YA tiene uno, bloqueamos (inalterabilidad)
                # Si no tiene uno (caso de generación tras post), permitimos.
                changed_fields = set(vals.keys())
                real_edits = changed_fields - technical_fields
                
                if real_edits:
                    raise UserError(_("Restricción Fiscal (Homologación): No se puede editar un documento en estado 'Publicado'. Toda corrección debe realizarse mediante una Nota de Crédito. (Campos detectados: %s)") % ", ".join(real_edits))
        
        return super(AccountMove, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        # Asignar números al crear (guardar)
        res = super(AccountMove, self).create(vals_list)
        for move in res:
            if move.move_type in ['out_invoice', 'out_refund']:
                move._assign_fiscal_sequences()
        return res

    def _assign_fiscal_sequences(self):
        """Asigna las secuencias fiscales si no están presentes."""
        for rec in self:
            if rec.move_type in ['out_invoice', 'out_refund']:
                # Secuencia de Numero de Control
                if not rec.nro_ctrl:
                    # 1. Intentar obtener secuencia desde el diario
                    sequence = rec.journal_id.nro_ctrl_sequence_id
                    
                    # 2. Si no hay en diario, buscar la predeterminada por código
                    if not sequence:
                        sequence = self.env['ir.sequence'].search([
                            ('code', 'in', ['g3c.nro.ctrl', 'l10n_nro_control_sale']),
                            ('company_id', '=', rec.company_id.id)
                        ], order='code asc', limit=1)
                    
                    if sequence:
                        rec.nro_ctrl = sequence.next_by_id()
                
                # Secuencia de Numero de Factura Cliente (si aplica g3c.customer.invoice.number)
                # Ojo: Odoo 17 usa 'name' por defecto, pero el módulo anterior usaba este campo extra
                if hasattr(rec, 'customer_invoice_number') and not rec.customer_invoice_number:
                    seq_cust = self.env['ir.sequence'].search([
                        ('code', '=', 'g3c.customer.invoice.number'),
                        ('company_id', '=', rec.company_id.id)
                    ], limit=1)
                    if seq_cust:
                        rec.customer_invoice_number = seq_cust.next_by_id()

    def action_post(self):
        # Requerimiento: Prohibir asignación de número de control en estado borrador (UI)
        # Asignar números al momento de publicar (action_post) para asegurar correlatividad
        self._assign_fiscal_sequences()
            
        for rec in self:
            # Restricción de Inventario: Bloqueo de Facturas en Negativo (Facturación directa)
            if rec.company_id.homologacion_activa and rec.company_id.is_ve_company and rec.move_type == 'out_invoice' and not rec.invoice_origin:
                # Optimized: Search warehouse once outside the line loop to prevent N+1 query issue
                warehouse = self.env['stock.warehouse'].search([('company_id', '=', rec.company_id.id)], limit=1)
                location = warehouse.lot_stock_id
                
                if location:
                    for line in rec.invoice_line_ids:
                        if line.product_id and line.product_id.type == 'product':
                            product_ctx = line.product_id.with_context(location=location.id)
                            available_qty = product_ctx.qty_available
                            
                            if line.quantity > available_qty:
                                raise UserError(_(
                                    "Restricción de Inventario (Homologación): No hay suficiente stock físico para el producto '%s' "
                                    "en la ubicación de la compañía '%s'.\n\n"
                                    "Disponible: %s %s\n"
                                    "Facturando: %s %s\n\n"
                                    "El sistema tiene prohibido procesar facturas en negativo."
                                ) % (
                                    line.product_id.display_name,
                                    location.display_name,
                                     available_qty, line.product_uom_id.name,
                                     line.quantity, line.product_uom_id.name
                                 ))


            # Restricción Notas de Crédito: No exceder la factura original
            if rec.company_id.homologacion_activa and rec.company_id.is_ve_company and rec.move_type == 'out_refund' and rec.reversed_entry_id:
                if rec.amount_total > rec.reversed_entry_id.amount_total:
                    raise UserError(_("Restricción Fiscal (Homologación): El monto de la Nota de Crédito no puede exceder el monto de la factura original (%s).") % rec.reversed_entry_id.amount_total)
        
        return super(AccountMove, self).action_post()

    def unlink(self):
        for move in self:
            if move.company_id.homologacion_activa and move.company_id.is_ve_company and move.state == 'posted' and move.move_type in ['out_invoice', 'out_refund']:
                # Requerimiento 2: Queda prohibido eliminar facturas en estado "Publicado"
                raise UserError(_("Restricción Fiscal (Homologación): No se puede eliminar un documento en estado 'Publicado'."))
        return super(AccountMove, self).unlink()

    def get_vet_timestamp(self):
        """Devuelve la fecha de creación convertida a la zona horaria de Venezuela."""
        self.ensure_one()
        if not self.create_date:
            return ''
        import pytz
        # Odoo almacena en UTC (naive)
        utc_dt = self.create_date.replace(tzinfo=pytz.UTC)
        vet_tz = pytz.timezone('America/Caracas')
        vet_dt = utc_dt.astimezone(vet_tz)
        return vet_dt.strftime('%d/%m/%Y %I:%M %p')
