from odoo import models, fields, api
from odoo.exceptions import UserError
from collections import defaultdict


class CommissionSettlement(models.Model):
    _name = "commission.settlement"
    _description = "Liquidación de Comisiones"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    use_margin = fields.Boolean(
        compute="_compute_use_margin",
        store=True,
        help="Technical field to show/hide profitability columns.",
    )

    @api.depends("company_id.commission_base_type")
    def _compute_use_margin(self):
        for record in self:
            record.use_margin = record.company_id.commission_base_type == 'margin'


    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        readonly=True,
        default="Nuevo",
        help="Referencia única de la liquidación.",
    )
    salesperson_id = fields.Many2one(
        "res.users",
        string="Vendedor",
        required=True,
        tracking=True,
        help="Vendedor al que corresponde esta liquidación.",
    )
    date_from = fields.Date(
        string="Fecha Inicio",
        required=True,
        tracking=True,
        help="Inicio del periodo liquidado.",
    )
    date_to = fields.Date(
        string="Fecha Fin",
        required=True,
        tracking=True,
        help="Fin del periodo liquidado.",
    )

    total_collected = fields.Monetary(
        string="Total Cobrado",
        currency_field="currency_id",
        default=0.0,
        help="Total cobrado en este periodo.",
    )
    total_invoiced = fields.Monetary(
        string="Total Facturado (Meta)",
        currency_field="currency_id",
        default=0.0,
        help="Total facturado que computa para la meta en este periodo.",
    )
    target_amount = fields.Monetary(
        string="Meta Mensual",
        currency_field="currency_id",
        default=0.0,
        help="Meta establecida para el vendedor en este periodo.",
    )
    achievement_pct = fields.Float(
        string="% Cumplimiento",
        default=0.0,
        help="Porcentaje de cumplimiento de la meta (Facturado / Meta).",
    )
    total_commission = fields.Monetary(
        string="Total Comisión",
        currency_field="currency_id",
        default=0.0,
        help="Monto total a pagar al vendedor.",
    )

    # USD Sum from Lines (Historical)
    currency_id_usd = fields.Many2one(
        "res.currency",
        string="Moneda Ref ($)",
        compute="_compute_currency_id_usd", 
        store=True,
    )
    commission_amount_usd = fields.Monetary(
        string="Total Comisión ($)",
        currency_field="currency_id_usd",
        compute="_compute_commission_amount_usd",
        store=True,
        help="Suma de las comisiones en USD (histórico líneas).",
    )

    def _compute_currency_id_usd(self):
        usd = self.env.ref("base.USD", raise_if_not_found=False)
        for record in self:
            record.currency_id_usd = usd

    @api.depends("line_ids.commission_amount_usd")
    def _compute_commission_amount_usd(self):
        for record in self:
            record.commission_amount_usd = sum(record.line_ids.mapped("commission_amount_usd"))

    # DUAL CURRENCY FIELDS
    currency_id_ref = fields.Many2one(
        "res.currency",
        string="Moneda Ref.",
        compute="_compute_currency_ref",
        help="Moneda de referencia para visualización.",
    )
    target_amount_ref = fields.Monetary(
        string="Meta (Ref.)",
        currency_field="currency_id_ref",
        compute="_compute_amounts_ref",
    )
    total_collected_ref = fields.Monetary(
        string="Cobrado (Ref.)",
        currency_field="currency_id_ref",
        compute="_compute_amounts_ref",
    )
    total_invoiced_ref = fields.Monetary(
        string="Facturado (Ref.)",
        currency_field="currency_id_ref",
        compute="_compute_amounts_ref",
    )
    total_commission_ref = fields.Monetary(
        string="Comisión (Ref.)",
        currency_field="currency_id_ref",
        compute="_compute_amounts_ref",
    )

    # ORIGINAL TARGET (To preserve display)
    target_amount_prospect = fields.Monetary(
        string="Meta Original",
        currency_field="target_currency_id",
        help="El monto original de la meta en su moneda de origen.",
    )
    target_currency_id = fields.Many2one(
        "res.currency",
        string="Moneda Meta Original",
        help="Moneda en la que se definió la meta.",
    )

    @api.depends("currency_id")
    def _compute_currency_ref(self):
        # Logic: If Company is USD, Ref is VES. Else Ref is USD.
        usd = self.env.ref("base.USD", raise_if_not_found=False)
        # Search for VES/VEF/Bs.
        ves = self.env["res.currency"].search([("name", "in", ["VES", "VEF", "Bs."])], limit=1, order="id desc")
        
        for record in self:
            if usd and record.currency_id == usd:
                record.currency_id_ref = ves or record.currency_id
            else:
                record.currency_id_ref = usd or record.currency_id


    @api.depends("currency_id", "currency_id_ref", "target_amount", "total_collected", "total_invoiced", "total_commission", "date_to", "target_amount_prospect", "target_currency_id")
    def _compute_amounts_ref(self):
        for record in self:
            if not record.currency_id_ref or record.currency_id_ref == record.currency_id:
                record.target_amount_ref = record.target_amount
                record.total_collected_ref = record.total_collected
                record.total_invoiced_ref = record.total_invoiced
                record.total_commission_ref = record.total_commission
                continue

            date = record.date_to or fields.Date.today()
            company = record.company_id or self.env.company
            
            # Conversion: Company -> Ref
            
            # Target: Prefer original if available and correct currency
            if record.target_amount_prospect and record.target_currency_id == record.currency_id_ref:
                 record.target_amount_ref = record.target_amount_prospect
            else:
                 record.target_amount_ref = record.currency_id._convert(record.target_amount, record.currency_id_ref, company, date)
            
            record.total_collected_ref = record.currency_id._convert(record.total_collected, record.currency_id_ref, company, date)
            record.total_invoiced_ref = record.currency_id._convert(record.total_invoiced, record.currency_id_ref, company, date)
            record.total_commission_ref = record.currency_id._convert(record.total_commission, record.currency_id_ref, company, date)


    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
        help="Moneda de la liquidación.",
    )
    company_id = fields.Many2one(
        "res.company", string="Compañía", default=lambda self: self.env.company
    )
    is_ve_company = fields.Boolean(
        compute="_compute_is_ve_company",
        string="Es Empresa VE",
        store=True,
        help="Indica si la empresa usa el sistema de doble moneda (Ref != Moneda).",
    )

    @api.depends("currency_id", "currency_id_ref", "company_id")
    def _compute_is_ve_company(self):
        for record in self:
            is_ve = False
            # Si el módulo de homologación está instalado, el campo existirá
            if 'homologacion_activa' in record.company_id._fields:
                is_ve = record.company_id.homologacion_activa
            
            # Si no está instalado o está inactivo, usar la lógica de fallback por moneda
            if not is_ve:
                is_ve = bool(record.currency_id_ref and record.currency_id and record.currency_id_ref != record.currency_id)
                
            record.is_ve_company = is_ve


    state = fields.Selection(
        [("draft", "Borrador"), ("done", "Validado")],
        string="Estado",
        default="draft",
        tracking=True,
        help="Estado del documento de liquidación.",
    )

    line_ids = fields.One2many(
        "commission.settlement.line", "settlement_id", string="Detalle de Comisiones"
    )
    current_month_line_ids = fields.Many2many(
        "commission.settlement.line",
        relation="comm_settlement_curr_rel",
        compute="_compute_split_lines",
        string="Facturas del Mes",
    )
    previous_month_line_ids = fields.Many2many(
        "commission.settlement.line",
        relation="comm_settlement_prev_rel",
        compute="_compute_split_lines",
        string="Cobranza Meses Anteriores",
    )
    grouped_line_ids = fields.One2many(
        "commission.settlement.grouped.line",
        "settlement_id",
        string="Pagos Comisionados Agrupados",
        compute="_compute_grouped_line_ids",
        store=True,
    )

    @api.depends("line_ids", "line_ids.is_previous_month")
    def _compute_split_lines(self):
        for rec in self:
            rec.current_month_line_ids = rec.line_ids.filtered(lambda l: not l.is_previous_month)
            rec.previous_month_line_ids = rec.line_ids.filtered(lambda l: l.is_previous_month)

    @api.depends(
        "line_ids",
        "line_ids.is_excluded",
        "line_ids.amount_paid",
        "line_ids.actual_amount_paid",
        "line_ids.commission_amount",
        "line_ids.commission_amount_usd",
        "line_ids.invoice_id",
        "line_ids.date",
    )
    def _compute_grouped_line_ids(self):
        for rec in self:
            commissioned_lines = rec.line_ids.filtered(lambda l: not l.is_excluded)
            grouped_data = {}
            for line in commissioned_lines:
                inv_key = line.invoice_id.id if line.invoice_id else f"line_{line.id}"
                if inv_key not in grouped_data:
                    inv_untaxed = 0.0
                    if line.invoice_id:
                        inv = line.invoice_id
                        inv_untaxed = inv.amount_untaxed
                        if inv.currency_id and rec.currency_id and inv.currency_id != rec.currency_id:
                            inv_untaxed = inv.currency_id._convert(
                                inv_untaxed,
                                rec.currency_id,
                                rec.company_id or self.env.company,
                                inv.invoice_date or inv.date or fields.Date.today(),
                            )

                    grouped_data[inv_key] = {
                        "client_id": line.client_id.id if line.client_id else False,
                        "invoice_id": line.invoice_id.id if line.invoice_id else False,
                        "is_credit": line.is_credit,
                        "invoice_date": line.invoice_date,
                        "date": line.date,
                        "invoice_untaxed_amount": inv_untaxed,
                        "amount_paid": 0.0,
                        "actual_amount_paid": 0.0,
                        "days_overdue": line.days_overdue,
                        "mora_penalty_factor": line.mora_penalty_factor,
                        "commission_pct": line.commission_pct,
                        "commission_amount": 0.0,
                        "commission_amount_usd": 0.0,
                    }
                else:
                    if line.date and (not grouped_data[inv_key]["date"] or line.date > grouped_data[inv_key]["date"]):
                        grouped_data[inv_key]["date"] = line.date

                grouped_data[inv_key]["amount_paid"] += line.amount_paid
                grouped_data[inv_key]["actual_amount_paid"] += getattr(line, "actual_amount_paid", 0.0)
                grouped_data[inv_key]["commission_amount"] += line.commission_amount
                grouped_data[inv_key]["commission_amount_usd"] += line.commission_amount_usd

            rec.grouped_line_ids.unlink()
            rec.grouped_line_ids = [(0, 0, vals) for vals in grouped_data.values()]
    min_price_penalty_pct = fields.Float(
        string="Penalización Precio Mínimo (%)",
        default=0.0,
        help="Porcentaje de penalización aplicado a ventas con precio mínimo.",
    )

    @api.model
    def create(self, vals):
        if vals.get("name", "Nuevo") == "Nuevo":
            vals["name"] = (
                self.env["ir.sequence"].next_by_code("commission.settlement") or "Nuevo"
            )
        return super(CommissionSettlement, self).create(vals)

    def action_validate(self):
        self.write({"state": "done"})
        # Snapshot Logic: create or update monthly closing
        for record in self:
            # Check if it covers a full month?? Or just overwrite for that month.
            # Requirement: "Congele el nivel de meta".
            # We assume the settlement is for a specific month.
            # We use date_from's first day as key.
            # If dates span multiple months, this might be tricky, but assuming Monthly Settlement.
            if not record.date_from:
                continue

            # Key Date: 1st of the month of the settlement.
            # If settlement is 1-30 Sept, key is 1st Sept.
            # If settlement is 15-30 Sept, key is still Sept?
            # Standard: Settlement should be full month.
            month_start = record.date_from.replace(day=1)

            # Check if exists
            closing = self.env["commission.monthly.closing"].search(
                [
                    ("salesperson_id", "=", record.salesperson_id.id),
                    ("date", "=", month_start),
                ],
                limit=1,
            )

            vals = {
                "salesperson_id": record.salesperson_id.id,
                "date": month_start,
                "target_amount": record.target_amount,
                "total_collected": record.total_collected,
                "total_invoiced": record.total_invoiced,
                "achievement_pct": record.achievement_pct,
            }

            if closing:
                closing.write(vals)
            else:
                self.env["commission.monthly.closing"].create(vals)

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_recalculate_commission(self):
        """Recalcula las comisiones y líneas de las liquidaciones seleccionadas en lote de forma optimizada."""
        if any(record.state != "draft" for record in self):
            raise UserError("Solo se pueden recalcular liquidaciones en estado Borrador.")

        grouped_settlements = defaultdict(lambda: self.env["commission.settlement"])
        for record in self:
            key = (
                record.date_from,
                record.date_to,
                record.min_price_penalty_pct,
                record.company_id.id if record.company_id else False,
            )
            grouped_settlements[key] |= record

        all_created_temp = self.env["commission.settlement"]

        for (date_from, date_to, min_price_penalty_pct, company_id), settlements in grouped_settlements.items():
            company = self.env["res.company"].browse(company_id) if company_id else self.env.company
            wizard = self.env["commission.settlement.wizard"].with_company(company).create({
                "company_id": company.id,
                "date_from": date_from,
                "date_to": date_to,
                "min_price_penalty_pct": min_price_penalty_pct,
            })

            res = wizard.action_generate_settlement()
            created_ids = res.get("domain", [("id", "in", [])])[0][2]
            created_settlements = self.browse(created_ids)
            all_created_temp |= created_settlements

            created_by_salesperson = {
                s.salesperson_id.id: s for s in created_settlements
            }

            for record in settlements:
                new_settlement = created_by_salesperson.get(record.salesperson_id.id)
                if new_settlement:
                    record.line_ids.unlink()
                    new_settlement.line_ids.write({"settlement_id": record.id})
                    record.write({
                        "target_amount": new_settlement.target_amount,
                        "total_collected": new_settlement.total_collected,
                        "total_invoiced": new_settlement.total_invoiced,
                        "achievement_pct": new_settlement.achievement_pct,
                        "total_commission": new_settlement.total_commission,
                        "target_amount_prospect": new_settlement.target_amount_prospect,
                        "target_currency_id": new_settlement.target_currency_id.id if new_settlement.target_currency_id else False,
                    })
                else:
                    record.line_ids.unlink()
                    record.write({
                        "total_collected": 0.0,
                        "total_invoiced": 0.0,
                        "achievement_pct": 0.0,
                        "total_commission": 0.0,
                    })

        if all_created_temp:
            all_created_temp.unlink()

        return True

    def action_export_excel_consolidated(self):
        self.ensure_one()
        import io
        import base64
        try:
            import xlsxwriter
        except ImportError:
            raise Exception("La librería xlsxwriter no está instalada en el servidor.")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        bold = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        money = workbook.add_format({'num_format': '#,##0.00'})

        def write_sheet(sheet_name, lines):
            sheet = workbook.add_worksheet(sheet_name)
            headers = ['Factura', 'Cliente', 'Fecha Factura', 'Fecha Pago', 'Días Mora', 'Factor Mora (%)', 'Monto Factura (Base)', 'Base Pagada', 'Monto Cobrado', 'Comisión Calculada', 'Estado / Observación']
            for col, head in enumerate(headers):
                sheet.write(0, col, head, bold)
                sheet.set_column(col, col, 18)
            sheet.set_column(1, 1, 35) # Client column wider
            sheet.set_column(10, 10, 40) # Status column wider

            # Consolidate by invoice ID to avoid merging "Sin Factura" or clashing names
            consolidated = {}
            for line in lines:
                inv_key = line.invoice_id.id if line.invoice_id else f"line_{line.id}"
                inv_name = line.invoice_id.name if line.invoice_id else "Sin Factura"
                
                estado = "Normal"
                if line.is_excluded:
                    estado = f"Excluida: {line.exclude_reason or ''}"
                elif line.is_min_price_sale:
                    estado = "Penalizada: Precio Mínimo"
                elif line.is_overdue:
                    estado = "Factura Vencida (Pago Tardío)"

                inv_untaxed = 0.0
                if line.invoice_id:
                    inv = line.invoice_id
                    inv_untaxed = inv.amount_untaxed
                    if inv.currency_id and self.currency_id and inv.currency_id != self.currency_id:
                        inv_untaxed = inv.currency_id._convert(
                            inv_untaxed,
                            self.currency_id,
                            self.company_id or self.env.company,
                            inv.invoice_date or inv.date or fields.Date.today(),
                        )

                if inv_key not in consolidated:
                    consolidated[inv_key] = {
                        'name': inv_name,
                        'client': line.client_id.name or '',
                        'invoice_date': str(line.invoice_date or ''),
                        'pay_date': str(line.date or ''),
                        'days_overdue': line.days_overdue,
                        'mora_penalty_factor': line.mora_penalty_factor,
                        'invoice_untaxed': inv_untaxed,
                        'amount_paid': 0.0,
                        'actual_amount_paid': 0.0,
                        'commission_amount': 0.0,
                        'estado': estado
                    }
                else:
                    if estado != "Normal" and estado not in consolidated[inv_key]['estado']:
                        if consolidated[inv_key]['estado'] == "Normal":
                            consolidated[inv_key]['estado'] = estado
                        else:
                            consolidated[inv_key]['estado'] += f" | {estado}"

                consolidated[inv_key]['amount_paid'] += line.amount_paid
                consolidated[inv_key]['actual_amount_paid'] += getattr(line, 'actual_amount_paid', 0.0)
                consolidated[inv_key]['commission_amount'] += line.commission_amount

            row = 1
            for key, data in consolidated.items():
                sheet.write(row, 0, data['name'])
                sheet.write(row, 1, data['client'])
                sheet.write(row, 2, data['invoice_date'])
                sheet.write(row, 3, data['pay_date'])
                sheet.write(row, 4, data['days_overdue'])
                mora_pct_val = data['mora_penalty_factor'] * 100 if data['mora_penalty_factor'] <= 1.0 else data['mora_penalty_factor']
                sheet.write(row, 5, f"{mora_pct_val:.0f}%")
                sheet.write(row, 6, data['invoice_untaxed'], money)
                sheet.write(row, 7, data['amount_paid'], money)
                sheet.write(row, 8, data.get('actual_amount_paid', 0.0), money)
                sheet.write(row, 9, data['commission_amount'], money)
                sheet.write(row, 10, data['estado'])
                row += 1

        # Tab 1: Current Month
        current_lines = self.line_ids.filtered(lambda l: not l.is_previous_month)
        write_sheet('Facturas del Mes', current_lines)

        # Tab 2: Previous Month (only if lines exist to avoid empty tab error)
        previous_lines = self.line_ids.filtered(lambda l: l.is_previous_month)
        if previous_lines:
            write_sheet('Meses Anteriores', previous_lines)
        elif not current_lines:
             # Fallback if both are empty so xlsxwriter doesn't crash
             write_sheet('Sin Datos', self.line_ids)

        # Tab 3: Comisionados (solo pagos de facturas comisionadas)
        commissioned_lines = self.line_ids.filtered(lambda l: not l.is_excluded)
        if commissioned_lines:
            write_sheet('Pagos Comisionados', commissioned_lines)

        workbook.close()
        output.seek(0)
        
        safe_name = self.name.replace('/', '_')
        attachment = self.env['ir.attachment'].create({
            'name': f'Consolidado_{safe_name}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class CommissionSettlementLine(models.Model):
    _name = "commission.settlement.line"
    _description = "Línea de Liquidación de Comisión"

    use_margin = fields.Boolean(
        compute="_compute_use_margin",
        store=True,
        help="Technical field to show/hide profitability columns.",
    )

    @api.depends("settlement_id.use_margin")
    def _compute_use_margin(self):
        for record in self:
            record.use_margin = record.settlement_id.use_margin or False

    settlement_id = fields.Many2one(
        "commission.settlement",
        string="Liquidación",
        ondelete="cascade",
        help="Documento padre de liquidación.",
    )
    is_previous_month = fields.Boolean(
        string="Es Mes Anterior",
        compute="_compute_is_previous_month",
    )
    date = fields.Date(
        string="Fecha", help="Fecha del pago o evento que genera comisión."
    )

    @api.depends("invoice_date", "settlement_id.date_from")
    def _compute_is_previous_month(self):
        for record in self:
            if record.invoice_date and record.settlement_id.date_from:
                record.is_previous_month = record.invoice_date < record.settlement_id.date_from
            else:
                record.is_previous_month = False
    client_id = fields.Many2one(
        "res.partner", string="Cliente", help="Cliente asociado a la venta."
    )
    product_id = fields.Many2one(
        "product.product", string="Producto", help="Producto vendido."
    )
    invoice_id = fields.Many2one(
        "account.move", string="Factura", help="Factura origen de la comisión."
    )
    invoice_payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Término de Pago",
        help="Término de pago de la factura.",
    )

    amount_paid = fields.Monetary(
        string="Base Pagada",
        currency_field="currency_id",
        help="Parte de la base de comisión cubierta por el pago.",
    )
    actual_amount_paid = fields.Monetary(
        string="Monto Cobrado",
        currency_field="currency_id",
        help="Monto real cobrado en el pago para esta factura comisionada.",
    )
    profitability = fields.Float(
        string="Rentabilidad (%)",
        group_operator="avg",
        help="Margen de ganancia o rentabilidad de la línea.",
    )  # Margin or Cost/Price relation
    cost = fields.Float(
        string="Costo", help="Costo asociado a la cantidad pagada/vendida."
    )

    commission_pct = fields.Float(
        string="% Comisión", help="Porcentaje de comisión aplicado."
    )
    deduction_pct = fields.Float(
        string="% Deducción", help="Porcentaje de deducción por gastos fijos."
    )
    penalty_pct = fields.Float(
        string="% Penalización", help="Porcentaje de penalización por precio mínimo."
    )

    commission_amount = fields.Monetary(
        string="Monto Comisión",
        currency_field="currency_id",
        help="Monto final de comisión para esta línea.",
    )

    is_min_price_sale = fields.Boolean(
        string="Venta Precio Mínimo", help="Indica si esta línea tuvo precio mínimo."
    )
    is_overdue = fields.Boolean(
        string="Vencida",
        help="Indica si la factura estaba vencida al momento del pago y no tenía autorización manual."
    )
    is_excluded = fields.Boolean(
        string="Excluida",
        help="Indica si esta línea no generó comisión."
    )
    exclude_reason = fields.Char(
        string="Razón de Exclusión",
        help="Motivo por el cual la factura fue excluida del cálculo de comisión."
    )
    is_credit = fields.Boolean(
        string="Es Crédito",
        help="Indica si la factura original es a crédito."
    )

    # Dashboard Fields
    invoice_date = fields.Date(string="Fecha Factura")
    invoice_date_due = fields.Date(string="Fecha Vencimiento")
    days_credit = fields.Integer(string="Días Crédito")
    days_paid = fields.Integer(string="Días Pago")
    days_overdue = fields.Integer(
        string="Días de Retraso",
        help="Días transcurridos entre la fecha de vencimiento y la fecha de pago."
    )
    mora_penalty_factor = fields.Float(
        string="Factor Mora (%)",
        default=1.0,
        help="Porcentaje de comisión reconocido según la Matriz de Cobranza (ej. 100%, 50%, 30%, 0%)."
    )
    manager_commission = fields.Monetary(
        string="Comisión Gerente",
        currency_field="currency_id",
        help="Comisión calculada para la gerencia sobre esta línea."
    )


    country_id = fields.Char(
        related="client_id.country_id.code", string="País", store=True
    )
    # Or strict relation:
    country_rel_id = fields.Many2one(
        "res.country", related="client_id.country_id", string="País (Rel)", store=True
    )

    salesperson_id = fields.Many2one(
        "res.users",
        related="settlement_id.salesperson_id",
        string="Vendedor",
        store=True,
    )
    currency_id = fields.Many2one("res.currency", related="settlement_id.currency_id")
    is_ve_company = fields.Boolean(
        related="settlement_id.is_ve_company",
        string="Es Empresa VE",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="settlement_id.company_id",
        string="Compañía",
        store=True,
        readonly=True,
    )

    # Fields for USD (Historical) Analysis
    currency_id_usd = fields.Many2one(
        "res.currency",
        string="Moneda Ref ($)",
        default=lambda self: self.env.ref(
            "base.USD", False
        ),  # Assuming 'base.USD' xmlid exists, else manually.
        help="Moneda de referencia (USD) para análisis histórico.",
    )
    commission_amount_usd = fields.Monetary(
        string="Monto Comisión ($)",
        currency_field="currency_id_usd",
        help="Monto de comisión convertido a USD usando la tasa histórica de la factura.",
    )


class CommissionSettlementGroupedLine(models.Model):
    _name = "commission.settlement.grouped.line"
    _description = "Línea Agrupada de Comisión por Factura"
    _order = "invoice_date desc, id desc"

    settlement_id = fields.Many2one(
        "commission.settlement",
        string="Liquidación",
        ondelete="cascade",
        required=True,
    )
    client_id = fields.Many2one("res.partner", string="Cliente")
    invoice_id = fields.Many2one("account.move", string="Factura")
    is_credit = fields.Boolean(string="Es Crédito")
    invoice_date = fields.Date(string="Fecha Factura")
    date = fields.Date(string="Fecha Pago")

    invoice_untaxed_amount = fields.Monetary(
        string="Monto Factura (Base Imponible)",
        currency_field="currency_id",
        help="Base imponible total de la factura original en la moneda de la liquidación.",
    )
    amount_paid = fields.Monetary(
        string="Monto Pagado Agrupado",
        currency_field="currency_id",
        help="Suma de la base pagada computada para comisión de esta factura en esta liquidación.",
    )
    actual_amount_paid = fields.Monetary(
        string="Monto Cobrado Agrupado",
        currency_field="currency_id",
        help="Monto real cobrado acumulado para esta factura.",
    )
    days_overdue = fields.Integer(string="Días Mora")
    mora_penalty_factor = fields.Float(string="Factor Mora (%)")
    commission_pct = fields.Float(string="% Comisión")

    commission_amount = fields.Monetary(
        string="Monto Comisión",
        currency_field="currency_id",
        help="Suma total de la comisión de esta factura.",
    )
    commission_amount_usd = fields.Monetary(
        string="Monto Comisión ($)",
        currency_field="currency_id_usd",
        help="Suma total de la comisión en USD.",
    )

    currency_id = fields.Many2one("res.currency", related="settlement_id.currency_id", store=True)
    currency_id_usd = fields.Many2one("res.currency", related="settlement_id.currency_id_usd", store=True)
    is_ve_company = fields.Boolean(related="settlement_id.is_ve_company", store=True)
    use_margin = fields.Boolean(related="settlement_id.use_margin", store=True)
