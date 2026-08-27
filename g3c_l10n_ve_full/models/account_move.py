# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    sin_cred = fields.Boolean(
        string="Excluir este documento del libro fiscal",
        readonly=False,
        store=True,
        help="Configúrelo verdadero si la factura está exenta de IVA (exención de impuestos)",
        default=False,
        copy=False,
    )

    customer_invoice_number = fields.Char(
        string="Número de factura cliente",
        store=True,
        help="Referencia de factura cliente.",
        copy=False,
    )
    supplier_invoice_number = fields.Char(
        string="Supplier Invoice Number",
        store=True,
        help="Referencia de factura del proveedor.",
        copy=False,
    )
    nro_ctrl = fields.Char(
        string="Número de Control",
        size=32,
        help="Número utilizado para gestionar facturas preimpresas, por ley Necesito poner aquí este"
        " número para poder declarar Informes fiscales correctamente.",
        copy=False,
        store=True,
        # The domain was incorrectly placed here, it should be on the field definition itself, not inside the help string.
        # Assuming the user intended to remove it or it was a copy-paste error in the instruction.
        # Keeping the original structure for now, but noting this potential issue.
        # domain="['|',('move_type', '=', 'out_invoice'),('move_type', '=', 'out_refund')]",
    )

    def activar_secuenciadores(self):
        for record in self:
            if not record.sin_cred:
                if record.move_type in ("out_invoice", "out_refund", "out_receipt"):
                    if not record.customer_invoice_number:
                        record.customer_invoice_number = self.env[
                            "ir.sequence"
                        ].next_by_code("g3c.customer.invoice.number")
                    if not record.nro_ctrl:
                        record.nro_ctrl = self.env["ir.sequence"].next_by_code(
                            "g3c.nro.ctrl"
                        )

    def compute_sin_cred(self):
        """Inicializa sin_cred=False y activa los secuenciadores fiscales.
        Este método ya no es un campo compute; se llama explícitamente cuando sea necesario."""
        self.ensure_one()
        self.sin_cred = False
        if self.move_type in ("out_invoice", "out_refund", "out_receipt"):
            if not self.date:
                self.date = fields.Date.today()
            if not self.invoice_date:
                self.invoice_date = fields.Date.today()
            if not self.invoice_date_due:
                self.invoice_date_due = fields.Date.today()
            self.activar_secuenciadores()
        return True

    # @api.depends("sin_cred")
    # def _compute_sequences(self):
    #     self.activar_secuenciadores()

    def write(self, vals):
        if vals.get("customer_invoice_number", False):
            customer_invoice_number_id = self._unique_invoice_per_partner(
                "customer_invoice_number", vals.get("customer_invoice_number", False)
            )
            if not customer_invoice_number_id:
                self.customer_invoice_number = False
                return {
                    "warning": {
                        "title": "Advertencia!",
                        "message": "  El Número de la Factura del Cliente ya Existe  ",
                    }
                }
        return super(AccountMove, self).write(vals)

    @api.onchange("customer_invoice_number")
    def onchange_customer_invoice_number(self):
        if self.customer_invoice_number:
            customer_invoice_number_id = self._unique_invoice_per_partner(
                "customer_invoice_number", self.customer_invoice_number
            )
            if not customer_invoice_number_id:
                self.customer_invoice_number = False
                return {
                    "warning": {
                        "title": "Advertencia!",
                        "message": "  El Número de la Factura del Cliente ya Existe  ",
                    }
                }

    def ret_and_reconcile(self, pay_amount, pay_account_id,
                          pay_journal_id, writeoff_acc_id,
                          writeoff_journal_id, date,
                          name, to_wh, type_retencion,
                          invoice_date=None):
        # Si no me pasan invoice_date, uso la misma fecha que 'date'
        invoice_date = invoice_date or date

        module_dual_currency = self.env['ir.module.module'].sudo().search([
            ('name', '=', 'account_dual_currency'),
            ('state', '=', 'installed'),
        ])
        rp_obj = self.env['res.partner']
        move_obj = self.env['account.move']

        assert len(self) == 1, "Solo puede pagar una factura a la vez"
        invoice = self

        src_account_id = pay_account_id.id

        types = {'out_invoice': -1, 'in_invoice': 1, 'out_refund': 1, 'in_refund': -1}
        direction = types[invoice.move_type]

        l1 = {
            'debit':  direction * pay_amount > 0 and direction * pay_amount,
            'credit': direction * pay_amount < 0 and -direction * pay_amount,
            'account_id': src_account_id,
            'partner_id': rp_obj._find_accounting_partner(invoice.partner_id).id,
            'ref': invoice.name,
            'date': date,
            'currency_id': invoice.company_currency_id.id,
            'name': name,
        }
        lines = [(0, 0, l1)]

        if type_retencion == 'wh_iva':
            l2 = self._get_move_lines1(to_wh, pay_journal_id,
                                      writeoff_acc_id, writeoff_journal_id,
                                      date, name)
        elif type_retencion == 'wh_islr':
            l2 = self._get_move_lines2(to_wh, pay_journal_id,
                                      writeoff_acc_id, writeoff_journal_id,
                                      date, name)
        elif type_retencion == 'wh_muni':
            l2 = self._get_move_lines3(to_wh, pay_journal_id,
                                      writeoff_acc_id, writeoff_journal_id,
                                      date, name)
        else:
            l2 = []

        if not l2:
            raise UserError(
                "Advertencia!\n"
                "No se crearon movimientos contables.\n"
                "Por favor, verifique si hay impuestos/conceptos para retener."
            )

        deb, cred = l2[0][2]['debit'], l2[0][2]['credit']
        if deb < 0:
            l2[0][2]['debit'] = deb * direction
        if cred < 0:
            l2[0][2]['credit'] = cred * direction

        lines += l2

        move_vals = {
            'ref':        f"{name} de {invoice.name}",
            'line_ids':   lines,
            'journal_id': pay_journal_id,
            'date':       date,
            'invoice_date': invoice_date,
            'state':      'draft',
            'type_name':  'entry',
        }
        if module_dual_currency:
            move_vals['tax_today'] = invoice.tax_today

        move = move_obj.create(move_vals)
        move._post(soft=False)

        to_rec = invoice.line_ids.filtered_domain([
            ('account_id', '=', src_account_id),
            ('reconciled', '=', False),
        ])
        pay_lines = move.line_ids.filtered_domain([
            ('account_id', '=', src_account_id),
            ('reconciled', '=', False),
        ])
        if module_dual_currency:
            pay_lines.amount_residual_usd = pay_lines.amount_residual / invoice.tax_today

        results = (pay_lines + to_rec).reconcile()
        # Corrijo monto_usd si quedó en cero
        if module_dual_currency and results and 'partials' in results:
            part = results['partials']
            if part.amount_usd == 0:
                part.write({'amount_usd': abs(pay_lines.amount_residual_usd)})
        return move

    def action_post(self):
        for move in self:
            if move.partner_id.company_type == 'company':
                if not move.partner_id.rif and not move.partner_id.vat:
                    raise UserError(f"Advertencia! \nEl Proveedor/Cliente no posee Documento Fiscal. Por favor diríjase a la configuación de {move.partner_id.name}, y realice el registro correctamente para poder continuar.")
            
            if move.partner_id.company_type == 'person':
                if not move.partner_id.identification_id and not move.partner_id.vat:
                    raise UserError(f"Advertencia! \nEl Proveedor/Cliente no posee Documento Fiscal. Por favor diríjase a la configuación de {move.partner_id.name}, y realice el registro correctamente para poder continuar")
            
        res = super(AccountMove, self).action_post()
        # Asignar automáticamente al libro fiscal si la empresa es venezolana
        # y la factura no está excluida del libro fiscal (sin_cred=False)
        self._auto_assign_fiscal_book()
        return res