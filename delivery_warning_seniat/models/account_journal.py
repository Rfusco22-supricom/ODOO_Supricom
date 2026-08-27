from odoo import models, fields, api
from odoo.exceptions import UserError
import datetime

class AccountChangeLockDate(models.TransientModel):
    _inherit = 'account.change.lock.date'

    # Campo computado para mostrar el mensaje de advertencia
    warning_message = fields.Char(compute='_compute_warning_message')

    @api.depends('fiscalyear_lock_date')
    def _compute_warning_message(self):
        for record in self:
            if not self.env.company.homologacion_activa or not self.env.company.is_ve_company:
                record.warning_message = False
                continue
            warning, orders_details = self._check_delivery_orders(record.fiscalyear_lock_date)
            record.warning_message = warning if warning else False

    @api.model
    def create(self, vals):
        result = super(AccountChangeLockDate, self).create(vals)
        if vals.get('fiscalyear_lock_date'):
            result.send_email_if_pending_orders(vals['fiscalyear_lock_date'])
        return result

    def write(self, vals):
        result = super(AccountChangeLockDate, self).write(vals)
        if vals.get('fiscalyear_lock_date'):
            self.send_email_if_pending_orders(vals['fiscalyear_lock_date'])
        return result

    def send_email_if_pending_orders(self, date_str):
        if not self.env.company.homologacion_activa or not self.env.company.is_ve_company:
            return
        # Convertir la fecha de cadena a objeto datetime.date si es necesario
        if isinstance(date_str, str):
            date = fields.Date.from_string(date_str)  # Convertir cadena a fecha
        else:
            date = date_str  # Usar directamente si ya es un objeto de fecha

        warning_msg, orders_details = self._check_delivery_orders(date)
        if warning_msg:
            self._send_email_to_seniat(date, orders_details)

    def _check_delivery_orders(self, date_str):
        if isinstance(date_str, str):
            date = fields.Date.from_string(date_str)
        else:
            date = date_str

        delivery_orders = self.env['stock.picking'].search([
            ('scheduled_date', '<=', date),
            ('picking_type_id.code', '=', 'outgoing'),  # solo salidas
            ('sale_id', '!=', False)  # asegurarse que venga de una venta
        ])

        filtered_orders = []
        for picking in delivery_orders:
            # Entregado y no facturado
            if picking.state == 'done' and picking.sale_id.invoice_status != 'invoiced':
                filtered_orders.append(picking)
            # No entregado y no facturado
            elif picking.state != 'done' and picking.sale_id.invoice_status != 'invoiced':
                filtered_orders.append(picking)

        if filtered_orders:
            warning_msg = (
                "🔔Advertencia Importante:🔔 \n\n"
                "Antes de cerrar el mes, verifique que todas las Órdenes de Entrega hayan sido facturadas.\n\n"
                "Según el Art. 20 de la Providencia SNAT/2011/0071, deben facturarse en el mismo período. "
                "El incumplimiento podría generar sanciones.\n\n"
                f"⚠️ Existen {len(filtered_orders)} órdenes de entrega pendientes por entregar o sin facturar "
                f"en o antes del {date.strftime('%Y-%m-%d')}. "
                "Dicha acción será notificada al SENIAT ⚠️"
            )
            return warning_msg, {order.name: order.scheduled_date for order in filtered_orders}
        return False, {}

    def _send_email_to_seniat(self, date, orders_details):
        mail_template = self.env.ref('delivery_warning_seniat.mail_template_notify_seniat')
        if not mail_template:
            raise UserError("Email template not found.")
        
        formatted_date = date.strftime("%Y-%m-%d")
        
        # Convertimos dict a lista de dicts para QWeb
        orders_details_list = [
            {'name': name, 'date': scheduled_date.strftime("%Y-%m-%d")}
            for name, scheduled_date in orders_details.items()
        ]
        
        ctx = {
            'date': formatted_date,
            'orders_details': orders_details_list
        }
        subject = f"Órdenes de Entrega Pendientes - {formatted_date} - {self.env.company.name}"
        # Aquí pasamos el asunto directamente
        mail_template.with_context(ctx).send_mail(self.id, force_send=True, email_values={
            'email_from': 'ing.andresecas@gmail.com',
            'email_to': 'andresecas150801@gmail.com',
            'subject': subject,
        })