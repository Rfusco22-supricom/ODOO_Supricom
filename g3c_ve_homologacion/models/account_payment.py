from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = 'account.payment'
    
    debit_note_igtf_id = fields.Many2one(
        'account.move',
        'Nota de Débito IGTF',
        readonly=True,
        help="Nota de débito generada automáticamente por el IGTF aplicado al pago"
    )

    homologacion_activa = fields.Boolean(
        related='company_id.homologacion_activa',
        string='Homologación Activa',
    )

    igtf_invoice_ids = fields.Many2many(
        'account.move',
        string="Facturas Origen IGTF",
        help="Facturas que originan este pago y la nota de débito por IGTF"
    )

    # Compatibility field for removed digiflex_bank_file submodule views
    sent_to_bank = fields.Boolean(
        string='Enviado a Banco (Compat)',
        compute='_compute_dummy_sent_to_bank',
        store=False,
    )

    def _compute_dummy_sent_to_bank(self):
        for rec in self:
            rec.sent_to_bank = False

    
    @api.depends('currency_id_dif', 'currency_id', 'amount', 'tax_today', 'igtf_invoice_ids')
    def _currency_equal(self):
        # Llamar al super para los cálculos básicos de dual currency
        super()._currency_equal()
        for rec in self:
            if rec.aplicar_igtf_divisa and rec.currency_id.name == 'USD':
                # IGTF calculable sobre Base Imponible + IVA (rec.amount ya los incluye)
                igtf_base = rec.amount
                
                rec.mount_igtf = rec.currency_id.round(igtf_base * rec.igtf_divisa_porcentage / 100)
                # El "Total Pagar" mostrado es Base + IGTF
                rec.amount_total_pagar = igtf_base + rec.mount_igtf
            else:
                rec.mount_igtf = 0
                rec.amount_total_pagar = rec.amount

    def register_move_igtf_divisa_payment(self):
        """Sobrescribimos la creación del asiento de IGTF para asignar la cuenta por cobrar/pagar del partner"""
        res = super(AccountPayment, self).register_move_igtf_divisa_payment()
        for payment in self:
            _logger.info("INICIO register_move_igtf_divisa_payment para pago %s. move_id_igtf_divisa: %s", payment.name, payment.move_id_igtf_divisa.id if payment.move_id_igtf_divisa else 'None')
            if payment.move_id_igtf_divisa:
                payment.move_id_igtf_divisa.button_draft()
                account_igtf_bridge = payment.company_id.account_debit_wh_igtf_id if payment.payment_type == 'inbound' else payment.company_id.account_credit_wh_igtf_id
                _logger.info("Buscando lineas con account_id_bridge: %s", account_igtf_bridge.id if account_igtf_bridge else 'None')
                
                line_to_modify = payment.move_id_igtf_divisa.line_ids.filtered(lambda l: l.account_id == account_igtf_bridge)
                _logger.info("line_to_modify encontrada: %s", line_to_modify)
                
                # Solo reemplazar por la cuenta de CxC o CxP si la configuracion permite pagar la nota de debito
                if line_to_modify and payment.partner_id and payment.company_id.igtf_debit_note_paid:
                    # En Odoo 17, el payment.destination_account_id ya contiene la cuenta de CxC o CxP respectiva de manera segura.
                    new_account = payment.destination_account_id
                    
                    if not new_account:
                        # Fallback en caso de que esté vacía
                        partner = payment.partner_id.commercial_partner_id.with_company(payment.company_id)
                        new_account = partner.property_account_receivable_id if payment.payment_type == 'inbound' else partner.property_account_payable_id
                        
                    _logger.info("new_account evaluado (destination_account_id): %s para partner %s", new_account.id if new_account else 'None', payment.partner_id.name)
                    
                    if new_account:
                        try:
                            line_to_modify.with_context(check_move_validity=False).write({
                                'account_id': new_account.id,
                                'partner_id': payment.partner_id.id
                            })
                            _logger.info("WRITE realizado exitosamente en la linea del IGTF. account_id=%s, partner_id=%s", new_account.id, payment.partner_id.id)
                        except Exception as e:
                            _logger.error("Error realizando el write en la linea de IGTF: %s", str(e))
                elif not payment.company_id.igtf_debit_note_paid:
                    _logger.info("Omitiendo reemplazo de cuenta puente por CXC/CXP por configuracion 'igtf_debit_note_paid' = False")
                    # Para que no tenga efecto contable, asignamos la misma cuenta a la otra linea del asiento
                    other_lines = payment.move_id_igtf_divisa.line_ids - line_to_modify
                    if other_lines and account_igtf_bridge:
                        try:
                            other_lines.with_context(check_move_validity=False).write({
                                'account_id': account_igtf_bridge.id
                            })
                            _logger.info("Linea de banco/caja del IGTF reemplazada por cuenta puente para anular el efecto contable.")
                        except Exception as e:
                            _logger.error("Error anulando efecto contable en linea de IGTF: %s", str(e))
                else:
                    _logger.warning("No se encontró line_to_modify o payment.partner_id es falso. line_to_modify=%s, partner_id=%s", line_to_modify, payment.partner_id)
                
                try:
                    payment.move_id_igtf_divisa.action_post()
                    _logger.info("move_id_igtf_divisa (BANEP) posteado exitosamente.")
                except Exception as e:
                    _logger.error("Error al hacer action_post en BANEP: %s", str(e))
                
        return res

    def action_post(self):
        """Sobrescribir para generar nota de débito por IGTF en pagos e imputar asientos"""
        # Asegurar cálculo correcto del IGTF antes de postear
        for payment in self:
            if payment.aplicar_igtf_divisa and payment.currency_id.name == 'USD':
                igtf_base = payment.amount
                
                payment.mount_igtf = payment.currency_id.round(igtf_base * payment.igtf_divisa_porcentage / 100)

        res = super(AccountPayment, self).action_post()
        
        for payment in self:
            # Para pagos con IGTF aplicado (clientes y proveedores)
            if payment.payment_type in ('inbound', 'outbound') and payment.aplicar_igtf_divisa and payment.mount_igtf > 0:
                _logger.info("Revisando Notas de Debito para pago %s. debit_note_igtf_id=%s", payment.name, payment.debit_note_igtf_id.id if payment.debit_note_igtf_id else 'None')
                # Evitar duplicados si ya tiene una ND asignada
                if not payment.debit_note_igtf_id:
                    # Crear nota de débito por IGTF
                    try:
                        payment._create_igtf_debit_note()
                        _logger.info("Factura/ND de IGTF creada: %s", payment.debit_note_igtf_id.name)
                    except Exception as e:
                        _logger.error("Error al crear la Nota de Débito por IGTF: %s", str(e))
                        raise UserError(_("Error al crear la Nota de Débito por IGTF: %s") % str(e))
                
                # Reconciliación Automática: Imputar asiento del IGTF del pago con la Nota de Débito
                if payment.company_id.igtf_debit_note_paid and payment.move_id_igtf_divisa and payment.debit_note_igtf_id:
                    account_type = 'asset_receivable' if payment.payment_type == 'inbound' else 'liability_payable'
                    
                    move_line_payment = payment.move_id_igtf_divisa.line_ids.filtered(lambda l: l.account_id.account_type == account_type)
                    move_line_invoice = payment.debit_note_igtf_id.line_ids.filtered(lambda l: l.account_id.account_type == account_type)
                    
                    _logger.info("Intento de Reconciliacion: move_line_payment=%s, move_line_invoice=%s", move_line_payment, move_line_invoice)
                    
                    if move_line_payment and move_line_invoice:
                        lines_to_reconcile = move_line_payment + move_line_invoice
                        if not lines_to_reconcile.filtered(lambda l: l.reconciled):
                            try:
                                lines_to_reconcile.reconcile()
                                _logger.info("Reconciliacion EXITOSA para pago %s", payment.name)
                            except Exception as e:
                                _logger.error("Error al conciliar lineas: %s", str(e))
                    else:
                        _logger.warning("No se pudo conciliar porque falta una linea. payment_lines: %s | invoice_lines: %s", move_line_payment, move_line_invoice)
                elif not payment.company_id.igtf_debit_note_paid:
                    _logger.info("Reconciliacion omitida para pago %s por configuracion 'igtf_debit_note_paid' = False", payment.name)
        
        return res
    
    def action_cancel(self):
        """Sobrescribir para cancelar la nota de débito IGTF si existe"""
        for payment in self:
            if payment.debit_note_igtf_id and payment.debit_note_igtf_id.state == 'posted':
                payment.debit_note_igtf_id.button_cancel()
        
        return super(AccountPayment, self).action_cancel()
    
    def action_draft(self):
        """Sobrescribir para poner en borrador la nota de débito IGTF si existe"""
        for payment in self:
            if payment.debit_note_igtf_id and payment.debit_note_igtf_id.state == 'cancel':
                payment.debit_note_igtf_id.button_draft()
        
        return super(AccountPayment, self).action_draft()
    
    def _create_igtf_debit_note(self):
        """Crea una nota de débito por el IGTF aplicado al pago"""
        self.ensure_one()
        
        expected_move_type = 'out_invoice' if self.payment_type == 'inbound' else 'in_invoice'
        
        # 1. Intentar obtener desde el campo igtf_invoice_ids (llenado por el wizard)
        reconciled_invoices = self.igtf_invoice_ids.filtered(
            lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
        )
        
        # 2. Si está vacío, intentar obtener las facturas reconciliadas (si ya se reconcilió)
        if not reconciled_invoices:
            reconciled_invoices = self.reconciled_invoice_ids.filtered(
                lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
            )
        
        # 3. Como último recurso, buscar en los apuntes contables
        if not reconciled_invoices:
            # En Odoo 17, a veces reconciled_invoice_ids no se refresca inmediatamente después de action_post
            # Buscamos manualmente a través de los apuntes contables del pago
            reconciled_invoices = self.move_id.line_ids.matched_debit_ids.debit_move_id.move_id.filtered(
                lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
            ) | self.move_id.line_ids.matched_credit_ids.credit_move_id.move_id.filtered(
                lambda inv: inv.move_type == expected_move_type and inv.state == 'posted'
            )
        
        if not reconciled_invoices:
            # Si aún así no hay facturas, no podemos vincular la ND legalmente
            return
        
        # Usar la primera factura como origen para debit_origin_id
        origin_invoice = reconciled_invoices[0]
        
        # Obtener el producto configurado para IGTF
        igtf_product = self.company_id.igtf_product_id
        if not igtf_product:
            raise UserError(_(
                "Error al generar Nota de Débito por IGTF:\n\n"
                "No se ha configurado el producto para Recargo IGTF.\n"
                "Por favor, configure el producto en: Configuración > Contabilidad > Producto IGTF"
            ))
        
        # Preparar descripción detallada si hay múltiples facturas
        invoice_names = ", ".join(reconciled_invoices.mapped('name'))
        line_description = f"Recargo IGTF - {invoice_names}" if len(reconciled_invoices) > 1 else f"Recargo IGTF - {origin_invoice.name}"

        # Obtener el diario designado para Notas de Débito IGTF
        journal_type_domain = 'sale' if self.payment_type == 'inbound' else 'purchase'
        igtf_journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('is_igtf_debit_note', '=', True),
            ('type', '=', journal_type_domain)
        ], limit=1)
        
        # Si no hay diario designado, usar el de la factura de origen (comportamiento anterior)
        journal = igtf_journal or origin_invoice.journal_id

        # Preparar valores para la nota de débito
        debit_note_vals = {
            'move_type': expected_move_type,
            'partner_id': self.partner_id.id,
            'journal_id': journal.id,
            'invoice_date': self.date,
            'date': self.date,
            'currency_id': self.currency_id.id,
            'tax_today': self.tax_today,
            'edit_trm': self.custom_rate,
            'debit_origin_id': origin_invoice.id,
            'ref': f"ND IGTF - Pago {self.name}",
            'invoice_line_ids': [(0, 0, {
                'product_id': igtf_product.id,
                'name': line_description,
                'quantity': 1,
                'price_unit': self.mount_igtf,
                'tax_ids': [(6, 0, [])],  # Las ND de IGTF no suelen llevar IVA adicional sobre el impuesto
            })],
        }
        
        # Crear la nota de débito
        debit_note = self.env['account.move'].create(debit_note_vals)
        
        # Guardar referencia
        self.write({'debit_note_igtf_id': debit_note.id})
        
        # Publicar la nota de débito automáticamente
        debit_note.action_post()
        
        return debit_note
