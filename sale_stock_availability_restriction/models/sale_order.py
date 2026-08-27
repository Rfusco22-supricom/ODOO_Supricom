from markupsafe import Markup
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, RedirectWarning

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    autorizar_despacho = fields.Boolean(string="Autorizar Despacho", copy=False)
    requiere_aprobacion = fields.Boolean(
        string="Requiere aprobación",
        compute='_compute_requiere_aprobacion',
        store=True,
        copy=False
    )
    excepcion_aprobada = fields.Boolean(string="Excepción aprobada", copy=False)

    @api.depends('partner_id', 'state', 'order_line', 'payment_term_id', 'amount_total')
    def _compute_requiere_aprobacion(self):
        for order in self:
            requiere = False
            if order.partner_id:
                partner = order.partner_id.commercial_partner_id
                
                # Skip approval check for cash clients (clientes de contado)
                # Check payment_term_id: name in ('Pago inmediato', 'Immediate Payment', 'Contado'), XML ID or line days == 0
                is_immediate = False
                if order.payment_term_id:
                    pt = order.payment_term_id
                    pt_name = (pt.name or '').strip().lower()
                    if pt_name in ('pago inmediato', 'immediate payment', 'pago al contado', 'contado'):
                        is_immediate = True
                    else:
                        ext_id = pt.get_external_id().get(pt.id, '') if hasattr(pt, 'get_external_id') else ''
                        if ext_id and 'account_payment_term_immediate' in ext_id:
                            is_immediate = True
                        elif pt.line_ids and all(getattr(l, 'nb_days', 0) == 0 for l in pt.line_ids):
                            is_immediate = True
                
                if is_immediate:
                    order.requiere_aprobacion = False
                    if 'x_studio_requiere_aprobacion' in order._fields:
                        order.x_studio_requiere_aprobacion = False
                    continue
                
                # Check credit limit exposure (Saldo actual + SOs pendientes por facturar + SO actual)
                credit = partner.credit if hasattr(partner, 'credit') else 0.0
                credit_limit = partner.credit_limit if hasattr(partner, 'credit_limit') else 0.0
                use_partner_credit_limit = partner.use_partner_credit_limit if hasattr(partner, 'use_partner_credit_limit') else False
                
                domain = [
                    ('partner_id.commercial_partner_id', '=', partner.id),
                    ('state', 'in', ['sale', 'done']),
                    ('invoice_status', '=', 'to invoice'),
                ]
                if isinstance(order.id, int):
                    domain.append(('id', '!=', order.id))
                    
                pending_so_exposure = sum(
                    self.env['sale.order'].search(domain).mapped('amount_total')
                )
                exposicion_total = credit + pending_so_exposure + order.amount_total

                if use_partner_credit_limit and credit_limit > 0 and exposicion_total > credit_limit:
                    requiere = True
                
                # Check overdue invoices
                if not requiere:
                    overdue_moves = self.env['account.move'].search_count([
                        ('partner_id', 'child_of', partner.id),
                        ('state', '=', 'posted'),
                        ('move_type', '=', 'out_invoice'),
                        ('payment_state', 'in', ['not_paid', 'partial']),
                        ('invoice_date_due', '<', fields.Date.context_today(self))
                    ])
                    if overdue_moves > 0:
                        requiere = True
                        
            order.requiere_aprobacion = requiere
            if 'x_studio_requiere_aprobacion' in order._fields:
                order.x_studio_requiere_aprobacion = requiere

    def action_check_credit_approval(self):
        """ Recalcula el estado de aprobacion y muestra una notificacion detallada con el estado de cuenta y credito """
        self.ensure_one()
        self._compute_requiere_aprobacion()

        partner = self.partner_id.commercial_partner_id if self.partner_id else False
        if not partner:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Verificación de Aprobación"),
                    'message': _("El pedido no tiene un cliente asignado."),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        pt_name = (self.payment_term_id.name or '').strip() if self.payment_term_id else 'Sin plazo asignado'

        # Verificar condición de contado
        is_immediate = False
        if self.payment_term_id:
            pt = self.payment_term_id
            name_lower = (pt.name or '').strip().lower()
            if name_lower in ('pago inmediato', 'immediate payment', 'pago al contado', 'contado'):
                is_immediate = True
            else:
                ext_id = pt.get_external_id().get(pt.id, '') if hasattr(pt, 'get_external_id') else ''
                if ext_id and 'account_payment_term_immediate' in ext_id:
                    is_immediate = True
                elif pt.line_ids and all(getattr(l, 'nb_days', 0) == 0 for l in pt.line_ids):
                    is_immediate = True

        credit = partner.credit if hasattr(partner, 'credit') else 0.0
        credit_limit = partner.credit_limit if hasattr(partner, 'credit_limit') else 0.0
        use_partner_credit_limit = partner.use_partner_credit_limit if hasattr(partner, 'use_partner_credit_limit') else False

        domain_so = [
            ('partner_id.commercial_partner_id', '=', partner.id),
            ('state', 'in', ['sale', 'done']),
            ('invoice_status', '=', 'to invoice'),
        ]
        if isinstance(self.id, int):
            domain_so.append(('id', '!=', self.id))
        pending_so_exposure = sum(self.env['sale.order'].search(domain_so).mapped('amount_total'))
        exposicion_total = credit + pending_so_exposure + self.amount_total

        overdue_moves = self.env['account.move'].search([
            ('partner_id', 'child_of', partner.id),
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date_due', '<', fields.Date.context_today(self))
        ])
        overdue_count = len(overdue_moves)

        currency_symbol = self.currency_id.symbol or '$'

        lines = []
        lines.append(f"• Cliente: {partner.name}")
        lines.append(f"• Plazo de pago: {pt_name}")
        if is_immediate:
            lines.append("• Condición: Contado (Exento de restricción de crédito)")
        else:
            lines.append(f"• Saldo contable adeudado: {currency_symbol} {credit:,.2f}")
            lines.append(f"• Pedidos confirmados por facturar: {currency_symbol} {pending_so_exposure:,.2f}")
            lines.append(f"• Monto del pedido actual: {currency_symbol} {self.amount_total:,.2f}")
            lines.append(f"• Exposición total calculada: {currency_symbol} {exposicion_total:,.2f}")
            if use_partner_credit_limit:
                lines.append(f"• Límite de crédito configurado: {currency_symbol} {credit_limit:,.2f}")
                if credit_limit > 0 and exposicion_total > credit_limit:
                    lines.append(f"⚠️ Excede límite por: {currency_symbol} {(exposicion_total - credit_limit):,.2f}")
            else:
                lines.append("• Límite de crédito específico: No configurado")

            if overdue_count > 0:
                inv_names = ', '.join(overdue_moves[:3].mapped('name'))
                if overdue_count > 3:
                    inv_names += f" y {overdue_count - 3} más"
                lines.append(f"⚠️ Facturas vencidas pendientes: {overdue_count} ({inv_names})")
            else:
                lines.append("• Facturas vencidas: Ninguna")

        lines.append("")
        if self.requiere_aprobacion:
            lines.append("Estado: ❌ REQUIERE APROBACIÓN")
        else:
            lines.append("Estado: ✅ APROBADO / NO REQUIERE APROBACIÓN")

        msg = "\n".join(lines)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Estado de Crédito y Aprobación (%s)") % self.name,
                'message': msg,
                'type': 'warning' if self.requiere_aprobacion else 'success',
                'sticky': True,
            }
        }

    def _check_stock_availability(self):
        for order in self:
            for line in order.order_line:
                if line.product_uom_qty > 0 and line.product_id.type == 'product':
                    location = order.warehouse_id.lot_stock_id
                    if not location:
                        continue
                    
                    # Obtenemos la Cantidad Disponible Real:
                    # Físico a mano (qty_available) - Salidas comprometidas (outgoing_qty)
                    product_with_context = line.product_id.with_context(location=location.id)
                    available_qty = product_with_context.qty_available - product_with_context.outgoing_qty
                    
                    # Convert required quantity to the product's base UoM
                    line_qty = line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
                    
                    # Evitamos la doble contabilización: cuando la orden YA está confirmada,
                    # sus movimientos ya están sumando en el outgoing_qty del producto.
                    # Por tanto, le sumamos a nuestra "disponibilidad" la cantidad que 
                    # nosotros mismos ya estamos reteniendo en nuestros propios movimientos válidos.
                    already_outgoing = sum(
                        m.product_qty 
                        for m in line.move_ids 
                        if m.state not in ('done', 'cancel')
                    )
                    available_qty += already_outgoing
                    
                    if available_qty < line_qty:
                        raise ValidationError(_(
                            "No se puede confirmar la venta ni Autorizar el Despacho.\n"
                            "El producto '%(product)s' no tiene suficiente disponibilidad en la ubicación de existencias '%(location)s' del almacén '%(warehouse)s'.\n"
                            "Cantidad requerida: %(required)s %(uom)s\n"
                            "Cantidad disponible: %(available)s %(uom)s"
                        ) % {
                            'product': line.product_id.display_name,
                            'location': location.display_name,
                            'warehouse': order.warehouse_id.name,
                            'required': line_qty,
                            'available': available_qty,
                            'uom': line.product_id.uom_id.name,
                        })

    def write(self, vals):
        # Bloquear autorizar despacho si el pedido no está confirmado
        if vals.get('autorizar_despacho'):
            for order in self:
                if order.state not in ('sale', 'done') and vals.get('state') not in ('sale', 'done'):
                    raise ValidationError(_(
                        "No se puede Autorizar el Despacho si el pedido no está confirmado. "
                        "Por favor, confirme primero la orden de venta."
                    ))
                
                # Verificar si los pickings están cancelados o no existen
                all_pickings = self.env['stock.picking'].sudo().search([('sale_id', '=', order.id)])
                valid_pickings = all_pickings.filtered(lambda p: p.state not in ('cancel',))
                if not valid_pickings and (order.state == 'sale' or vals.get('state') == 'sale'):
                    action = self.env.ref('sale_stock_availability_restriction.action_recreate_picking_wizard', raise_if_not_found=False)
                    if action:
                        raise RedirectWarning(
                            _("El despacho previamente generado se encuentra cancelado o no existe. "
                              "¿Desea generar nuevamente el despacho?"),
                            action.id,
                            _("Sí, Generar Despacho"),
                            additional_context={'default_sale_order_id': order.id}
                        )

        if 'excepcion_aprobada' in vals or 'x_studio_aprobacion_excepcion' in vals:
            val_excepcion = vals.get('excepcion_aprobada', vals.get('x_studio_aprobacion_excepcion'))
            for order in self:
                current_studio = getattr(order, 'x_studio_aprobacion_excepcion', False)
                if val_excepcion != order.excepcion_aprobada or val_excepcion != current_studio:
                    if not self.env.user.puede_aprobar_excepcion:
                        raise ValidationError(_(
                            "No tienes permiso para aprobar o quitar excepciones de ventas. "
                            "Solicita esto a un usuario autorizado."
                        ))
            
            if 'x_studio_aprobacion_excepcion' in self.env['sale.order']._fields and 'x_studio_aprobacion_excepcion' not in vals:
                vals['x_studio_aprobacion_excepcion'] = val_excepcion
            if 'excepcion_aprobada' not in vals:
                vals['excepcion_aprobada'] = val_excepcion

        res = super(SaleOrder, self).write(vals)

        now = fields.Datetime.now()
        user = self.env.user

        # Log in chatter when autorizar_despacho is changed
        if 'autorizar_despacho' in vals:
            for order in self:
                if vals['autorizar_despacho']:
                    body = Markup(_("<strong>✅ Autorizar Despacho activado</strong><br/>Usuario: %s<br/>Fecha y hora: %s")) % (user.name, now.strftime('%d/%m/%Y %H:%M:%S'))
                    # Unhide the pickings
                    pickings = self.env['stock.picking'].sudo().search([
                        ('sale_id', '=', order.id),
                        ('despacho_oculto', '=', True),
                    ])
                    if pickings:
                        pickings.write({'despacho_oculto': False})
                        # Only call action_assign on pickings that are not cancelled or done
                        pickings_to_assign = pickings.filtered(lambda p: p.state not in ('done', 'cancel'))
                        if pickings_to_assign:
                            pickings_to_assign.action_assign()
                else:
                    body = Markup(_("<strong>❌ Autorizar Despacho desactivado</strong><br/>Usuario: %s<br/>Fecha y hora: %s")) % (user.name, now.strftime('%d/%m/%Y %H:%M:%S'))
                    # Hide the pickings and unreserve stock
                    pickings = order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
                    if pickings:
                        pickings.write({'despacho_oculto': True})
                        pickings.do_unreserve()
                order.message_post(body=body, subtype_xmlid='mail.mt_note')

        # Log in chatter when excepcion_aprobada is changed
        if 'excepcion_aprobada' in vals:
            for order in self:
                if vals['excepcion_aprobada']:
                    body = Markup(_("<strong>✅ Excepción Aprobada</strong><br/>Usuario: %s<br/>Fecha y hora: %s")) % (user.name, now.strftime('%d/%m/%Y %H:%M:%S'))
                else:
                    body = Markup(_("<strong>❌ Excepción Aprobada removida</strong><br/>Usuario: %s<br/>Fecha y hora: %s")) % (user.name, now.strftime('%d/%m/%Y %H:%M:%S'))
                order.message_post(body=body, subtype_xmlid='mail.mt_note')

        return res

    def action_cancel(self):
        # Cancelar pickings ocultos bloqueados por permisos de la vista
        sudo_env = self.env['stock.picking'].sudo()
        for order in self:
            hidden_pickings = sudo_env.search([
                ('sale_id', '=', order.id),
                ('despacho_oculto', '=', True),
                ('state', 'not in', ('done', 'cancel'))
            ])
            if hidden_pickings:
                hidden_pickings.action_cancel()
        
        return super(SaleOrder, self).action_cancel()

    @api.depends('picking_ids')
    def _compute_picking_ids(self):
        super(SaleOrder, self)._compute_picking_ids()
        for order in self:
            hidden_pickings_count = self.env['stock.picking'].sudo().search_count([
                ('sale_id', '=', order.id),
                ('despacho_oculto', '=', True)
            ])
            if hidden_pickings_count:
                order.delivery_count += hidden_pickings_count

    def action_view_delivery(self):
        # Evitar IndexError cuando las entregas están ocultas (despacho_oculto=True)
        # Se obtiene el listado completo de pickings asociados a la orden
        pickings = self.env['stock.picking'].sudo().search([('sale_id', 'in', self.ids)])
        if pickings:
            return self._get_action_view_picking(pickings)
        
        # Si no hay pickings en la BD (delivery_count = 0), y el botón es visible,
        # Odoo por defecto arrojaría IndexError. En lugar de eso, retornamos 
        # la vista de lista vacía de entregas para que el usuario no tenga un error.
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_all")
        action['domain'] = [('sale_id', 'in', self.ids)]
        action['context'] = {
            'default_partner_id': self.partner_id.id,
            'default_origin': self.name
        }
        return action

    def action_confirm(self):
        for order in self:
            if not order.autorizar_despacho:
                order._check_stock_availability()
                        
        result = super(SaleOrder, self).action_confirm()

        # After confirmation, if autorizar_despacho is not active,
        # hide the generated pickings from inventory views
        for order in self:
            if not order.autorizar_despacho:
                pickings = order.picking_ids.filtered(
                    lambda p: p.state not in ('done', 'cancel')
                )
                if pickings:
                    pickings.write({'despacho_oculto': True})
                    pickings.do_unreserve()

        return result

    def _create_invoices(self, grouped=False, final=False, date=None):
        for order in self:
            requiere = order.requiere_aprobacion or getattr(order, 'x_studio_requiere_aprobacion', False)
            aprobada = order.excepcion_aprobada or getattr(order, 'x_studio_aprobacion_excepcion', False)
            if requiere and not aprobada:
                raise ValidationError(_(
                    "No se puede facturar el pedido de venta '%(order)s'.\n"
                    "El cliente ha excedido su límite de crédito o tiene facturas vencidas y requiere aprobación.\n"
                    "Por favor, solicite a un gerente/supervisor que apruebe la excepción ('Excepción aprobada')."
                ) % {'order': order.name})
        return super(SaleOrder, self)._create_invoices(grouped=grouped, final=final, date=date)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def write(self, vals):
        if any(f in vals for f in ('product_uom_qty', 'product_id', 'product_uom')):
            for line in self:
                if line.state in ('sale', 'done') and not self.env.context.get('skip_sale_stock_restriction'):
                    raise ValidationError(_(
                        "No puede modificar la cantidad, producto o unidad de medida "
                        "de una línea si el pedido ya está confirmado ('%s')."
                    ) % line.order_id.name)
        return super(SaleOrderLine, self).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('order_id'):
                order = self.env['sale.order'].browse(vals['order_id'])
                if order.state in ('sale', 'done') and not self.env.context.get('skip_sale_stock_restriction'):
                    # Si la cantidad pedida es 0 (líneas técnicas/automáticas de Odoo para despachos), no bloqueamos
                    if vals.get('product_uom_qty', 0) == 0:
                        continue
                    raise ValidationError(_(
                        "No puede agregar nuevos productos a un pedido que ya está confirmado ('%s')."
                    ) % order.name)
        return super(SaleOrderLine, self).create(vals_list)

    def unlink(self):
        for line in self:
            if line.state in ('sale', 'done') and not self.env.context.get('skip_sale_stock_restriction'):
                # Permitir borrar líneas automáticas/técnicas con cantidad ordenada = 0
                if line.product_uom_qty == 0:
                    continue
                raise ValidationError(_(
                    "No puede eliminar líneas de productos de un pedido que ya está confirmado ('%s')."
                ) % line.order_id.name)

        # Omitir la validación nativa de Odoo 17 (que impide borrar líneas en pedidos confirmados)
        # cambiando temporalmente el estado a 'draft' en la base de datos y la caché antes de borrar.
        zero_qty_lines = self.filtered(lambda l: l.product_uom_qty == 0 and l.state in ('sale', 'done'))
        if zero_qty_lines:
            self.env.cr.execute(
                "UPDATE sale_order_line SET state = 'draft' WHERE id IN %s",
                [tuple(zero_qty_lines.ids)]
            )
            zero_qty_lines.invalidate_recordset(['state'])

        return super(SaleOrderLine, self).unlink()
