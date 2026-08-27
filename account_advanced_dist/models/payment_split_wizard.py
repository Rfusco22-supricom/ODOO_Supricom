# models/payment_split_wizard.py
from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class PaymentSplitWizard(models.TransientModel):
    _name = "account.payment.split.wizard"
    _description = "Asistente de Distribución Avanzada y Multi-Compañía"

    # --- Lógica Multi-Factura ---
    line_ids = fields.One2many(
        "account.payment.split.line", "wizard_id", string="Facturas a Pagar"
    )

    # Campo auxiliar para recibir la selección desde el Action
    selected_invoice_ids = fields.Many2many(
        "account.move", string="Facturas Seleccionadas"
    )

    # --- Contexto Principal ---
    invoice_id = fields.Many2one(
        "account.move",
        string="Factura Inicial",
        required=False,
        # Domain simple por compatibilidad, la lógica fuerte va en el onchange
        domain=[
            ("move_type", "in", ("out_invoice", "in_invoice")),
            ("state", "=", "posted"),
        ],
    )

    # Estos campos de filtro determinan qué facturas buscar
    filter_partner_id = fields.Many2one(
        "res.partner",
        string="Cliente/Proveedor Destino",
        compute="_compute_filters",
        store=True,
        compute_sudo=True,
        readonly=False,
    )
    filter_company_id = fields.Many2one(
        "res.company",
        string="Compañía Destino",
        compute="_compute_filters",
        store=True,
        compute_sudo=True,
        readonly=False,
    )

    # --- Selección de Pago y Búsqueda Global ---
    search_mode = fields.Boolean(string="Activar Búsqueda Global (Terceros)")
    search_ref = fields.Char(string="Buscar por Referencia / Memo")

    payment_id = fields.Many2one(
        "account.payment",
        string="Pago Seleccionado",
        required=False,
    )
    payment_company_id = fields.Many2one(
        related="payment_id.company_id", string="Cía. Pago", store=False
    )

    # --- Detección de Escenarios (Flags) ---
    is_third_party_payment = fields.Boolean(
        compute="_compute_scenarios", string="Es Pago de Tercero", store=True, compute_sudo=True
    )
    is_inter_company = fields.Boolean(
        compute="_compute_scenarios", string="Es Inter-Compañía", store=True, compute_sudo=True
    )

    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )

    # --- Saldos y Cálculos ---
    payment_currency_id = fields.Many2one("res.currency", string="Moneda del Pago")

    payment_amount_available = fields.Monetary(
        string="Saldo Disponible del Pago", currency_field="payment_currency_id"
    )

    # Este campo ahora es la suma de las líneas
    amount_to_apply = fields.Monetary(
        string="Total a Aplicar",
        compute="_compute_amount_to_apply",
        store=True,
        compute_sudo=True,
        currency_field="payment_currency_id",
    )

    # NUEVO: Req 2 - Total Convertido
    total_amount_converted = fields.Monetary(
        string="Total con Conversión",
        compute="_compute_amount_to_apply",
        store=True,
        compute_sudo=True,
        currency_field="currency_id",  # Moneda de la factura (o compañia si mixto)
    )

    # NUEVO: Req 1 - Filtro de Tipo de Pago
    payment_type_filter = fields.Selection(
        [("inbound", "Entrante"), ("outbound", "Saliente")],
        string="Filtro Tipo Pago",
        compute="_compute_filters",
        store=True,
        compute_sudo=True,
    )

    # --- Feedback Visual (Proyecciones) ---
    remaining_payment_balance = fields.Monetary(
        string="Saldo Restante Pago",
        compute="_compute_projected_balances",
        currency_field="payment_currency_id",
    )

    progress_html = fields.Html(
        string="Estado de Asignación", compute="_compute_progress_bar"
    )

    # -------------------------------------------------------------------------
    # COMPUTED FIELDS
    # -------------------------------------------------------------------------

    @api.depends("invoice_id", "partner_id", "search_mode", "selected_invoice_ids")
    def _compute_filters(self):
        for w in self:
            # Inicializar valores para evitar errores de caché
            w.filter_partner_id = False
            w.filter_company_id = False
            w.payment_type_filter = False

            # Si se abre desde una factura, tomamos sus datos por defecto
            if w.invoice_id:
                w.filter_partner_id = w.invoice_id.partner_id
                w.filter_company_id = w.invoice_id.company_id

                # Determine Payment Type Filter
                # Customer Invoice (out_invoice) -> Receives Money (inbound)
                # Vendor Bill (in_invoice) -> Sends Money (outbound)
                # Refunds are opposite.
                m_type = w.invoice_id.move_type
                if m_type == "out_invoice":
                    w.payment_type_filter = "inbound"
                elif m_type == "in_invoice":
                    w.payment_type_filter = "outbound"
                elif m_type == "out_refund":
                    w.payment_type_filter = "outbound"  # Pay back customer
                elif m_type == "in_refund":
                    w.payment_type_filter = "inbound"  # Receive refund from vendor
                else:
                    w.payment_type_filter = False
            else:
                w.payment_type_filter = False

            # Si cambiamos a search mode, permitimos editar
            if w.search_mode and not w.filter_partner_id:
                w.filter_partner_id = False  # Usuario debe elegir

            # Si viene del contexto de multiselección (invoice_id puede ser False)
            if not w.filter_partner_id and w.selected_invoice_ids:
                w.filter_partner_id = w.selected_invoice_ids[0].partner_id
                w.filter_company_id = w.selected_invoice_ids[0].company_id

    # Helpers legacy para vistas
    partner_id = fields.Many2one(related="invoice_id.partner_id")
    invoice_company_id = fields.Many2one(related="invoice_id.company_id")
    currency_id = fields.Many2one(related="invoice_id.currency_id")
    invoice_amount_residual = fields.Monetary(
        related="invoice_id.amount_residual", currency_field="currency_id"
    )

    @api.depends("payment_id", "filter_partner_id", "filter_company_id")
    def _compute_scenarios(self):
        for w in self:
            if w.payment_id:
                target_company = (
                    w.filter_company_id or w.invoice_id.company_id or w.env.company
                )
                target_partner = w.filter_partner_id or w.invoice_id.partner_id

                w.is_inter_company = w.payment_company_id != target_company
                if target_partner:
                    w.is_third_party_payment = w.payment_id.partner_id != target_partner
                else:
                    w.is_third_party_payment = False
            else:
                w.is_inter_company = False
                w.is_third_party_payment = False

    @api.depends("line_ids.amount_to_pay", "line_ids.amount_converted")
    def _compute_amount_to_apply(self):
        for w in self:
            w.amount_to_apply = sum(line.amount_to_pay for line in w.line_ids)

            # REQ: El total convertido debe mostrar el VALOR HISTORICO de la deuda matada
            total_hist = 0.0
            for line in w.line_ids:
                if line.amount_to_pay:
                    if line.invoice_id.currency_id != w.payment_currency_id:
                        # Use Invoice Date for Historical Value
                        c_date = (
                            line.invoice_id.invoice_date or fields.Date.context_today(w)
                        )
                        val = w.payment_currency_id._convert(
                            line.amount_to_pay,
                            line.invoice_id.currency_id,
                            w.env.company,
                            c_date,
                        )
                        total_hist += val
                    else:
                        total_hist += line.amount_to_pay

            w.total_amount_converted = total_hist

    @api.onchange("payment_id")
    def _onchange_payment_id_force_values(self):
        if self.payment_id:
            self.payment_currency_id = self.payment_id.currency_id
            # total_amount = self.payment_id.amount # Ya no se usa para el calculo manual

            payment_lines = self.payment_id.line_ids.filtered(
                lambda l: l.account_type in ("asset_receivable", "liability_payable")
            )

            _logger.info(f"[WIZARD-ONCHANGE] Payment: {self.payment_id.name}")
            _logger.info(f"[WIZARD-ONCHANGE] Payment Lines count: {len(payment_lines)}")
            
            # IMPORTANTE: Siempre usar amount_residual (moneda de la compañía, Bs.F)
            # porque nuestro sistema de diferenciales opera en moneda local.
            # El amount_residual_currency puede estar desincronizado debido a las correcciones de partials.
            current_residual = 0.0
            for line in payment_lines:
                _logger.info(f"[WIZARD-ONCHANGE] Line ID: {line.id}, Account: {line.account_id.code}, Debit: {line.debit}, Credit: {line.credit}")
                _logger.info(f"[WIZARD-ONCHANGE] Line amount_residual: {line.amount_residual}, amount_residual_currency: {line.amount_residual_currency}")
                _logger.info(f"[WIZARD-ONCHANGE] Line matched_debit_ids: {line.matched_debit_ids.ids}, matched_credit_ids: {line.matched_credit_ids.ids}")
                
                # Usar siempre amount_residual (moneda compañía) para evitar discrepancias
                current_residual += abs(line.amount_residual)

            _logger.info(f"[WIZARD-ONCHANGE] Calculated current_residual: {current_residual}")
            
            if abs(current_residual) < 0.01:
                current_residual = 0.0
            self.payment_amount_available = current_residual
        else:
            self.payment_amount_available = 0.0
            self.payment_currency_id = False

    @api.depends("amount_to_apply", "payment_amount_available")
    def _compute_projected_balances(self):
        for w in self:
            w.remaining_payment_balance = w.payment_amount_available - w.amount_to_apply

    @api.depends("amount_to_apply", "payment_amount_available")
    def _compute_progress_bar(self):
        for w in self:
            if w.payment_amount_available > 0:
                percent = (w.amount_to_apply / w.payment_amount_available) * 100
                percent = min(max(percent, 0), 100)
            else:
                percent = 0

            color_class = "bg-danger" if percent > 100 else "bg-success"
            w.progress_html = f"""
            <div style="margin-top: 10px;">
                <div class="d-flex justify-content-between mb-1">
                    <span class="text-muted small">Uso del Pago</span>
                    <span class="text-muted small">{int(percent)}%</span>
                </div>
                <div class="progress" style="height: 10px;">
                    <div class="progress-bar {color_class}" role="progressbar" style="width: {percent}%;" 
                         aria-valuenow="{percent}" aria-valuemin="0" aria-valuemax="100"></div>
                </div>
            </div>"""

    # -------------------------------------------------------------------------
    # CARGA DE FACTURAS
    # -------------------------------------------------------------------------
    @api.onchange(
        "filter_partner_id",
        "filter_company_id",
        "invoice_id",
        "selected_invoice_ids",
        "payment_id",
    )
    def _onchange_load_lines(self):
        """
        Carga las facturas en la lista. Prioriza la selección múltiple explícita.
        """
        # 1. Definir qué facturas cargar
        invoices_to_load = self.env["account.move"]

        if self.selected_invoice_ids:
            # Caso A: Vengo de selección múltiple -> Solo muestro esas
            invoices_to_load = self.selected_invoice_ids.filtered(
                lambda x: x.payment_state in ("not_paid", "partial")
            )
        else:
            # Caso B: Vengo de un cambio de partner o modo normal -> Busco todas las abiertas
            target_partner = self.filter_partner_id or self.invoice_id.partner_id
            target_company = self.filter_company_id or self.invoice_id.company_id

            if not target_partner:
                self.line_ids = [Command.clear()]
                return

            domain = [
                ("partner_id", "=", target_partner.id),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("move_type", "in", ("out_invoice", "in_invoice")),
            ]
            if target_company:
                domain.append(("company_id", "=", target_company.id))

            invoices_to_load = self.env["account.move"].search(
                domain, order="invoice_date asc"
            )

        # 2. Construir líneas del wizard
        lines = [Command.clear()]

        # Asegurar moneda de pago
        payment_currency = self.payment_currency_id
        if self.payment_id and not payment_currency:
            payment_currency = self.payment_id.currency_id

        # Asegurar fecha de pago (para conversión)
        payment_date = self.payment_id.date or fields.Date.context_today(self)

        # --- LOGICA DE AUTO-LLENADO CON SALDO ---
        running_balance = 0.0
        if self.payment_id:
            # Calcular saldo inicial disponible del pago
            # IMPORTANTE: Siempre usar amount_residual (moneda compañía, Bs) para consistencia
            payment_lines = self.payment_id.line_ids.filtered(
                lambda l: l.account_type in ("asset_receivable", "liability_payable")
            )
            current_residual = 0.0
            for line in payment_lines:
                # Usar siempre amount_residual (moneda compañía) para evitar discrepancias
                current_residual += abs(line.amount_residual)

            if abs(current_residual) < 0.01:
                current_residual = 0.0
            running_balance = current_residual

        for inv in invoices_to_load:
            # Lógica de pre-llenado de monto
            amount_initial = 0.0
            amount_converted_initial = 0.0  # Nuevo campo a calcular

            # Si es la factura principal O si venimos de selección multiple,
            # asumimos que queremos pagar el saldo completo de estas facturas seleccionadas
            is_target = False
            if self.selected_invoice_ids and inv in self.selected_invoice_ids:
                is_target = True
            elif self.invoice_id and inv.id == self.invoice_id.id:
                is_target = True

            if is_target:
                try:
                    if payment_currency and inv.currency_id != payment_currency:
                        # IMPORTANTE: Usar la fecha del PAGO para la conversión
                        # porque queremos saber cuántos Bs (moneda pago) equivalen al residual USD
                        # Si la factura tiene $50 y el pago es @ 350, debemos mostrar 17,500 Bs
                        p_date = payment_date
                        conversion_date = p_date  # Siempre usar fecha del pago

                        amount_initial = inv.currency_id._convert(
                            inv.amount_residual,
                            payment_currency,
                            self.env.company,
                            conversion_date,
                        )

                        # --- SMART ROUNDING ---
                        # Evitar residuos pequeños (ej. 1,699,998 -> 1,700,000)
                        # Check proximity to integer
                        rounded_int = round(amount_initial)
                        if abs(amount_initial - rounded_int) < 0.1:  # Tolerancia visual
                            amount_initial = float(rounded_int)

                        # Check proximity to tens/hundreds for high-value currencies (e.g. VEF, COP)
                        # Example: 1,699,998 -> 1,700,000 (+2 diff)
                        # Only apply if value is large (>1000)
                        if abs(amount_initial) > 1000:
                            # Try rounding to 10s
                            rounded_10 = round(amount_initial, -1)
                            if (
                                abs(amount_initial - rounded_10) < 5.0
                            ):  # Tolerancia de 5 unidades
                                amount_initial = rounded_10

                            # Try rounding to 100s if very close (e.g. 998 -> 1000)
                            rounded_100 = round(amount_initial, -2)
                            if (
                                abs(amount_initial - rounded_100) < 5.0
                            ):  # Tolerancia estricta para redondeo grande
                                amount_initial = rounded_100

                    else:
                        amount_initial = inv.amount_residual
                except:
                    amount_initial = 0.0

            # --- APLICAR CAP DE SALDO DISPONIBLE ---
            if self.payment_id:
                # 1. SNAP UP: Si el saldo disponible es POCO MAS que el monto deuda,
                # preferimos matar todo el saldo del pago para que no sobren moneditas.
                # Ej: Deuda 1.699.989, Saldo 1.700.000 -> Diferencia 10.11 -> Usar 1.700.000
                if running_balance > amount_initial:
                    diff = running_balance - amount_initial
                    # Tolerancia: 50 unidades (para cubrir VEF) o 0.01% del monto (para montos grandes)
                    # OJO: Solo si es menor a cierta cantidad absoluta para no regalar plata en monedas fuertes
                    is_small_diff = (
                        diff < 20.0
                    )  # Tolerancia absoluta simple para el caso del usuario (10.10)

                    if is_small_diff:
                        amount_initial = running_balance

                # 2. CAP DOWN: Si el monto calculado es MAYOR al saldo, limitamos.
                # PERO si la diferencia es minuscula (rounding error), permitimos pasar para matar el pago.
                if (
                    amount_initial > running_balance
                    and (amount_initial - running_balance) < 0.05
                ):
                    amount_initial = running_balance
                else:
                    amount_initial = min(amount_initial, running_balance)

                running_balance -= amount_initial
                # Evitar negativos por decimales
                if running_balance < 0:
                    running_balance = 0.0

            # --- CALCULO INVERSO PARA "EQUIVALENTE" ---
            # Una vez fijado amount_initial (en moneda pago), calculamos cuanto representa en la factura
            # REQ: Usar Tasa Histórica (Factura)
            if amount_initial > 0:
                if payment_currency and inv.currency_id != payment_currency:
                    # Linea: Usar Tasa ACTUAL (Payment strictly)
                    p_date = payment_date
                    conversion_date = p_date

                    val = payment_currency._convert(
                        amount_initial,
                        inv.currency_id,
                        self.env.company,
                        conversion_date,
                    )

                    # Capping Visual REMOVED: User wants to see real converted value (e.g. 3000 VEF)
                    # even if it exceeds residual (700 VEF), to understand the massive exchange diff.
                    # resid = abs(inv.amount_residual)
                    # if abs(val) > resid + 0.01:
                    #     amount_converted_initial = resid * (1 if val >= 0 else -1)
                    # else:
                    amount_converted_initial = val
                else:
                    amount_converted_initial = amount_initial

            if amount_initial > 0:
                pass 

            lines.append(
                Command.create(
                    {
                        "invoice_id": inv.id,
                        "currency_id": inv.currency_id.id,
                        "payment_currency_id": (
                            payment_currency.id if payment_currency else False
                        ),
                        "payment_date": payment_date,
                        "amount_residual": inv.amount_residual,
                        "amount_to_pay": amount_initial,
                        "amount_converted": amount_converted_initial,
                    }
                )
            )

        self.line_ids = lines

    @api.onchange("search_ref", "payment_id", "filter_partner_id")
    def _onchange_search_ref(self):
        # DOMINIO DINÁMICO
        base_domain = [
            ("state", "=", "posted"),
            ("is_reconciled", "=", False),
        ]

        # Si NO es búsqueda global, restringir por Partner seleccionado
        if not self.search_mode and self.filter_partner_id:
            base_domain.append(("partner_id", "=", self.filter_partner_id.id))

        # NUEVO: Filtro por Tipo de Pago (Entrante/Saliente)
        # Esto evita pagos de proveedores en wizard de clientes
        if self.payment_type_filter:
            base_domain.append(("payment_type", "=", self.payment_type_filter))

        if self.search_ref:
            base_domain.append(("ref", "ilike", self.search_ref))

        return {"domain": {"payment_id": base_domain}}

    # -------------------------------------------------------------------------
    # EJECUCIÓN
    # -------------------------------------------------------------------------

    def action_confirm_split(self):
        self.ensure_one()
        if self.amount_to_apply <= 0:
            raise UserError(_("Debe asignar un monto a al menos una factura."))
        if self.remaining_payment_balance < -0.01:
            raise UserError(
                _(
                    "Fondos Insuficientes. El saldo restante del pago no puede ser negativo."
                )
            )

        if self.is_inter_company:
            _logger.info("Routing to Inter-Company Transfer")
            return self._process_inter_company_transfer()
        if self.is_third_party_payment:
            _logger.info("Routing to Third Party / Reclassification")
            return self._process_third_party_reclassification()

        _logger.info("Routing to Standard Partial Reconciliation")
        return self._process_standard_partial_reconciliation()

    def _create_manual_exchange_move(self, invoice_line, payment_line, partial):
        """
        Crea un asiento de diferencial cambiario manualmente para pagos parciales.
        LOGICA MODIFICADA: 
        El diferencial NO se aplica directo a la cuenta por cobrar/pagar. 
        Se envía a una CUENTA DE TRÁNSITO configurada en la compañía.
        Este asiento queda 'en el aire' (Open) hasta que se aplique manualmente a la factura.
        """
        if not partial:
            return

        _logger.info(f"[MANUAL-EXCH] Start for Invoice: {invoice_line.move_id.name}, Payment: {payment_line.move_id.name}")

        # 3. Calcular Diferencial
        amount_paid_company = partial.amount
        company = self.env.company
        invoice_currency = invoice_line.currency_id or company.currency_id
        
        _logger.info(f"[MANUAL-EXCH] Processing partial: {partial.id} Amount: {amount_paid_company}")
        
        # Obtener el residual de la factura EN MONEDA EXTRANJERA antes de esta conciliación
        # Este es el monto en USD que el usuario realmente está pagando
        invoice_residual_currency = abs(invoice_line.amount_residual_currency)
        
        _logger.info(f"[MANUAL-EXCH] Invoice Residual (foreign currency): {invoice_residual_currency}")
        
        if invoice_currency != company.currency_id:
            if invoice_line.debit > 0:
                amount_paid_curr = partial.debit_amount_currency
            else:
                amount_paid_curr = partial.credit_amount_currency
            
            _logger.info(f"[MANUAL-EXCH] Partial currency amount from Odoo: {amount_paid_curr}")
            
            # IMPORTANTE: Si el usuario está aplicando el residual completo de la factura,
            # debemos usar el residual en USD de la factura, no la conversión de Odoo
            # porque Odoo convierte usando la tasa del día, no la tasa del pago
            
            # Verificar si el monto en Bs pagado cubre aproximadamente el residual de la factura
            # Usamos el residual de la factura en USD para el cálculo
            if invoice_residual_currency > 0:
                # Convertir el residual de la factura a Bs usando la tasa del PAGO
                payment_date = payment_line.date or fields.Date.context_today(self)
                invoice_residual_at_payment_rate = invoice_currency._convert(
                    invoice_residual_currency,
                    company.currency_id,
                    company,
                    payment_date
                )
                
                _logger.info(f"[MANUAL-EXCH] Invoice residual at payment date rate: {invoice_residual_at_payment_rate} Bs")
                
                # Si el monto pagado (Bs) es cercano al residual convertido, están pagando el residual completo
                tolerance = abs(invoice_residual_at_payment_rate) * 0.05  # 5% tolerancia
                if abs(amount_paid_company - invoice_residual_at_payment_rate) <= tolerance:
                    # El usuario está pagando el residual completo, usar el monto USD correcto
                    _logger.info(f"[MANUAL-EXCH] Detected FULL residual payment. Using invoice residual currency: {invoice_residual_currency}")
                    amount_paid_curr = invoice_residual_currency
                elif not amount_paid_curr or abs(amount_paid_curr) < 0.01:
                    # Fallback: convertir Bs a USD usando tasa del pago
                    _logger.warning("[MANUAL-EXCH] Partial has 0.0 currency amount. Calculating fallback.")
                    amount_paid_curr = company.currency_id._convert(
                        amount_paid_company,
                        invoice_currency,
                        company,
                        payment_date
                    )
                    _logger.info(f"[MANUAL-EXCH] Fallback calculated amount_paid_curr: {amount_paid_curr}")

        else:
            if payment_line.debit > 0:
                amount_paid_curr = partial.debit_amount_currency
            else:
                amount_paid_curr = partial.credit_amount_currency
        
        if not amount_paid_curr: 
            _logger.warning("[MANUAL-EXCH] Zero amount_paid_curr after fallback. Skipping.")
            return

        _logger.info(f"[MANUAL-EXCH] Final amount_paid_curr (foreign): {amount_paid_curr}")

        # Valor Real Histórico
        invoice_date = invoice_line.move_id.invoice_date or invoice_line.date or fields.Date.context_today(self)
        currency_to_check = invoice_line.currency_id or company.currency_id
        if currency_to_check == company.currency_id:
            return 

        expected_company_amount = currency_to_check._convert(
                amount_paid_curr, 
                company.currency_id, 
                company, 
                invoice_date
        )
        
        diff = amount_paid_company - expected_company_amount
        
        _logger.info(f"[MANUAL-EXCH] Calculation: Paid(Bs)={amount_paid_company} - Expected(Bs)={expected_company_amount} = Diff={diff}")

        if abs(diff) < 0.01:
            _logger.info("[MANUAL-EXCH] Diff negligible. Skipping.")
            return

        _logger.info(f"[MANUAL-EXCH] Diff Detected: {diff}")

        # 4. Determinar Cuentas
        is_payable = invoice_line.account_id.account_type == 'liability_payable'
        is_receivable = invoice_line.account_id.account_type == 'asset_receivable'
        
        exchange_journal = company.currency_exchange_journal_id or self.env['account.journal'].search([('type','=','general'), ('company_id','=',company.id)], limit=1)
        
        account_gain = company.income_currency_exchange_account_id
        account_loss = company.expense_currency_exchange_account_id
        
        transit_account = company.exchange_diff_transit_account_id
        
        if not account_gain or not account_loss:
            _logger.warning("[MANUAL-EXCH] Missing Exchange Accounts configuration.")
            return

        if not transit_account:
            raise UserError(_("Debe configurar la Cuenta de Tránsito para Diferencial Cambiario en los ajustes de la Compañía."))

        # LOGICA CUENTAS:
        # Ganancia: Debit Transit / Credit Gain (STANDARD)
        # BUT we want to Reconcile with Payment (Inv Account / CXC / CXP)
        # So:
        # Ganancia (Payment has surplus):
        # We need to DEBIT the CXP (Vendor) to reduce the debt/surplus. 
        # So instead of Debit Transit, we Debit CXP.
        # But we want the Gain to sit in Transit until applied to invoice.
        # So: Debit CXP / Credit Transit.
        
        # Pérdida (Payment has deficit?):
        # We need to CREDIT CXP (Vendor) to increase debt.
        # So: Debit Transit / Credit CXP.
        
        debit_acc = False
        credit_acc = False
        
        if diff > 0:
            # Ganancia (Para Receivables customer pagó más BsF)
            if is_receivable:
                # Cliente pagó más: Ganancia
                # CXC increases? No. Customer paid more Bs.
                # We owe customer the difference?
                # Let's say Inv=$100 (3000 Bs). Pmt=$100 (5000 Bs).
                # Partial = 3000 Bs. Pmt Remaining = 2000 Bs.
                # Diff = 2000 Bs Gain.
                # We create entry to CONSUME the 2000 Bs from Payment.
                # Payment is Credit 5000. 
                # We need a DEBIT on CXC to reconcile with Payment Credit.
                # Debit CXC 2000 / Credit Transit 2000.
                debit_acc = invoice_line.account_id.id
                credit_acc = transit_account.id
            else:
                # Proveedor pagamos más: Pérdida (o Ganancia en diferencial?)
                # Inv=$100 (3000 Bs). Pmt=$100 (3500 Bs).
                # Partial 3000. Pmt Remaining = 500.
                # Payment is Debit 3500.
                # We need a CREDIT on CXP to reconcile with Payment Debit.
                # Debit Transit 500 / Credit CXP 500.
                debit_acc = transit_account.id
                credit_acc = invoice_line.account_id.id
        else:
            # Diferencia negativa
            if is_receivable:
                # Cliente pagó menos: Pérdida
                debit_acc = transit_account.id
                credit_acc = invoice_line.account_id.id
            else:
                # Proveedor pagamos menos: Ganancia
                debit_acc = invoice_line.account_id.id
                credit_acc = transit_account.id

        # 5. Crear Asiento
        exchange_date = invoice_line.move_id.invoice_date or invoice_line.move_id.date or fields.Date.context_today(self)
        
        move_vals = {
            'journal_id': exchange_journal.id,
            'date': exchange_date,
            'ref': f'Diferencial Manual: {invoice_line.move_id.name} [partial_id:{partial.id}]',
            'move_type': 'entry',
            'tax_today': 0, # Force Dual Currency 0
        }
        
        partner_id = invoice_line.partner_id.id
        
        line_1_vals = {
            'name': _('Diferencial Cambiario'),
            'account_id': debit_acc,
            'debit': abs(diff),
            'credit': 0,
            'partner_id': partner_id,
            'debit_usd': 0, 'credit_usd': 0,
            'tax_today': 0,
        }
        
        line_2_vals = {
            'name': _('Diferencial Cambiario'),
            'account_id': credit_acc,
            'debit': 0,
            'credit': abs(diff),
            'partner_id': partner_id,
            'debit_usd': 0, 'credit_usd': 0,
            'tax_today': 0,
        }

        move_vals['line_ids'] = [
            Command.create(line_1_vals),
            Command.create(line_2_vals)
        ]
        
        # Force Context to trigger account_dual_currency override
        move = self.env['account.move'].with_context(force_no_dual_currency_exchange=True).create(move_vals)
        move.action_post()
        
        _logger.info(f"[MANUAL-EXCH] Created Transit Exchange Move: {move.name}")
        
        # --- NUEVA LÓGICA DE RECONCILIACIÓN (FIX RESIDUALS) ---
        # 1. Asegurar que el 'partial' base tenga el monto de la Factura (Histórico)
        if partial.amount != expected_company_amount:
            try:
                partial.write({'amount': expected_company_amount})
                _logger.info(f"[MANUAL-EXCH] Corrected Partial Amount to: {expected_company_amount}")
                
                # FORCE RECOMPUTE OF RESIDUAL on Invoice Line
                # Since we modified the partial directly via SQL or write, the line might not know it needs to update residual immediately in UI.
                invoice_line._compute_amount_residual()
                payment_line._compute_amount_residual()
                
            except Exception as e:
                _logger.warning(f"[MANUAL-EXCH] Could not update partial amount: {e}")

        # 2. Reconciliar el diferencial con el PAGO.
        #    Buscamos la línea del asiento nuevo que pegó contra la cuenta de la factura (CXC/CXP)
        
        rec_line = move.line_ids.filtered(lambda l: l.account_id == invoice_line.account_id)
        
        if rec_line:
            try:
                _logger.info(f"[MANUAL-EXCH] Attempting to reconcile Transit line (id={rec_line.id}, debit={rec_line.debit}, credit={rec_line.credit}) with Payment line (id={payment_line.id}, debit={payment_line.debit}, credit={payment_line.credit})")
                _logger.info(f"[MANUAL-EXCH] Payment residual BEFORE reconcile: {payment_line.amount_residual}")
                
                (payment_line + rec_line).reconcile()
                
                # Invalidate cache to refresh residuals
                payment_line.invalidate_recordset(['amount_residual', 'amount_residual_currency', 'reconciled'])
                
                _logger.info(f"[MANUAL-EXCH] Payment residual AFTER reconcile: {payment_line.amount_residual}")
                _logger.info(f"[MANUAL-EXCH] Reconciled Exchange Line with Payment Line.")
            except Exception as e:
                _logger.warning(f"[MANUAL-EXCH] Failed to reconcile Transit with Payment: {e}")
                
        # NO CONCILIAR CON LA FACTURA. 
        # La diferencia queda en la cuenta tránsito esperando aplicación manual (o ya se usó para ajustar el pago).

        # --- AUTOMATION: APPLY DIFFERENCE IMMEDIATELY ---
        # Objetivo: Cerrar la cuenta de tránsito contra Ganancia/Pérdida automáticamente.
        # Y vincular este segundo asiento al mismo partial_id para que el unlink del partial borre ambos.
        
        _logger.info("[MANUAL-EXCH] Starting Automated Application of Difference...")
        
        # 1. Determinar si el asiento de tránsito (move) generó Saldo Deudor o Acreedor en la cuenta tránsito.
        transit_line_origin = move.line_ids.filtered(lambda l: l.account_id == transit_account)
        if not transit_line_origin:
            _logger.warning("[MANUAL-EXCH] No transit line found in origin move. Skipping automation.")
            return

        # Si transit_line_origin tiene DEBIT > 0 -> Es una 'Pérdida' acumulada en tránsito (o reducción de ganancia).
        # Si transit_line_origin tiene CREDIT > 0 -> Es una 'Ganancia' acumulada en tránsito.
        
        # Lógica de cierre:
        # Si Origin es DEBIT (Saldo +): Necesitamos un CREDIT en tránsito para matarlo.
        #   Contrapartida: DEBIT en Gasto (Pérdida).
        # Si Origin es CREDIT (Saldo -): Necesitamos un DEBIT en tránsito para matarlo.
        #   Contrapartida: CREDIT en Ingreso (Ganancia).
        
        acc_gain = company.income_currency_exchange_account_id
        acc_loss = company.expense_currency_exchange_account_id
        
        if not acc_gain or not acc_loss:
            _logger.warning("[MANUAL-EXCH] Missing Gain/Loss accounts. Skipping automation.")
            return

        app_debit_acc = False
        app_credit_acc = False
        app_amount = abs(diff) # El monto es el mismo del diferencial
        
        # Análisis de saldo en origen
        if transit_line_origin.credit > 0:
            # Origen fue CREDIT (Ganancia). Necesitamos DEBIT Transit / CREDIT Gain.
            app_debit_acc = transit_account.id
            app_credit_acc = acc_gain.id
            diff_type_label = "Ganancia (Auto)"
        else:
            # Origen fue DEBIT (Pérdida). Necesitamos DEBIT Loss / CREDIT Transit.
            app_debit_acc = acc_loss.id
            app_credit_acc = transit_account.id
            diff_type_label = "Pérdida (Auto)"
            
        # Crear Asiento de Aplicación
        # IMPORTANTE: Usar el MISMO tag [partial_id:...] en la referencia
        app_ref = f'Aplicación Auto: {invoice_line.move_id.name} [partial_id:{partial.id}]'
        
        app_move_vals = {
            'journal_id': exchange_journal.id,
            'date': exchange_date,
            'ref': app_ref,
            'move_type': 'entry',
            'tax_today': 0,
        }
        
        app_line_1 = {
            'name': diff_type_label,
            'account_id': app_debit_acc,
            'debit': app_amount,
            'credit': 0,
            'partner_id': partner_id,
            'debit_usd': 0, 'credit_usd': 0,
            'tax_today': 0,
        }
        
        app_line_2 = {
            'name': 'Cierre Tránsito',
            'account_id': app_credit_acc,
            'debit': 0,
            'credit': app_amount,
            'partner_id': partner_id,
            'debit_usd': 0, 'credit_usd': 0,
            'tax_today': 0,
        }
        
        app_move_vals['line_ids'] = [
            Command.create(app_line_1),
            Command.create(app_line_2)
        ]
        
        try:
            app_move = self.env['account.move'].with_context(force_no_dual_currency_exchange=True).create(app_move_vals)
            app_move.action_post()
            _logger.info(f"[MANUAL-EXCH] Created Application Move: {app_move.name}")
            
            # 2. Reconciliar Tránsito vs Tránsito
            # Origin Transit Line (from 'move') vs Application Transit Line (from 'app_move')
            transit_line_app = app_move.line_ids.filtered(lambda l: l.account_id == transit_account)
            
            if transit_line_origin and transit_line_app:
                (transit_line_origin + transit_line_app).reconcile()
                _logger.info("[MANUAL-EXCH] Reconciled Transit Account lines.")
                
        except Exception as e:
            _logger.error(f"[MANUAL-EXCH] Failed to create automation move: {e}")

    def _process_standard_partial_reconciliation(self):
        lines_to_process = self.line_ids.filtered(lambda l: l.amount_to_pay > 0)

        if not lines_to_process:
            raise UserError(_("No hay montos asignados."))

        payment_lines = self.payment_id.line_ids.filtered(
            lambda l: l.account_type in ("asset_receivable", "liability_payable")
            and not l.reconciled
        )
        if not payment_lines:
            raise UserError(_("El pago ya no tiene líneas conciliables."))

        payment_line = payment_lines[0]
        message_body = "💰 <b>Pago Distribuido:</b><ul>"

        company = self.env.company
        p_date = self.payment_id.date or fields.Date.context_today(self)

        for line in lines_to_process:
            invoice_line = line.invoice_id.line_ids.filtered(
                lambda l: l.account_type in ("asset_receivable", "liability_payable")
                and not l.reconciled
            )
            if not invoice_line:
                continue

            # --- INTENTO DE CONCILIACIÓN NATIVA ---
            # Si el usuario aplica un pago completo (coincidiendo con el saldo de factura o pago),
            # priorizamos el uso del método nativo reconcile(). Esto garantiza que las diferencias
            # de cambio y los cruces de monedas sean manejados por el motor estándar, asegurando fiabilidad.

            resid_invoice = (
                abs(invoice_line.amount_residual_currency)
                if invoice_line.currency_id
                else abs(invoice_line.amount_residual)
            )
            resid_payment = (
                abs(payment_line.amount_residual_currency)
                if payment_line.currency_id
                else abs(payment_line.amount_residual)
            )

            # Verificar si estamos saldando completamente el lado del pago o de la factura.
            # Usamos chequeos independientes para soportar discrepancias entre monedas (ej. 1.5M VEF vs 5k USD).
            # CRÍTICO: Solo usamos Nativo si es MISMA MONEDA. En cruce de monedas (VEF->USD),
            # Odoo nativo calcula los montos al tipo de cambio *actual*, lo cual puede dejar residuos no deseados.
            # Para cruce de monedas, preferimos la lógica manual ajustada (con tope histórico) de abajo.

            # is_full_payment_usage logic:
            # Does the Amount we are applying match the remaining amount of the payment?
            is_full_payment_usage = abs(line.amount_to_pay - resid_payment) < 0.01

            # is_full_invoice_payment logic:
            # Does the Amount we are applying (in Payment Currency) match the Invoice Residual?
            # PROBLEM: If Payment is Bs.F and Invoice is USD, numerical comparison fails (1.6M vs 3500).
            # FIX: Convert Invoice Residual to Payment Currency for comparison
            # OR better: Check if the 'equivalent amount' calculated matches the invoice residual in ITS currency.

            # Helper to check equivalence
            is_full_invoice_payment = False

            # 1. Simple Case: Same Currency (Values match directly)
            if abs(line.amount_to_pay - resid_invoice) < 0.01:
                is_full_invoice_payment = True

            # 2. Cross Currency Case:
            # If Payment is in BsF but Invoice is USD.
            # line.amount_to_pay is BsF. resid_invoice is USD.
            # We must convert line.amount_to_pay to USD to check if it covers the invoice.
            # We use the RATE captured in the wizard line line.exchange_rate (implied).
            else:
                # Check if the intended payment amount covers the invoice's residual currency
                # line.amount_to_pay (Payment Coin)
                # We need to know what that represents in Invoice Coin.
                # Actually, we can just try Native Reconcile if the currencies differ
                # and we are reasonably close.
                # The 'reconcile' method handles partials fine if we just pass the lines.
                # The REAL heuristic is: Do we WANT native behavior?
                # If currencies differ, Native behavior IS desired to fix exchange diffs.
                if line.invoice_id.currency_id != self.payment_currency_id:
                    # If currencies differ, assume we want Native Reconcile to trigger exchange diffs
                    # UNLESS it's a very small partial payment?
                    # Let's trust Odoo's reconcile() to decide if it's full or partial.
                    # We just need to know if we should ATTEMPT it.
                    # Attempt it if the user is paying approx the full value.
                    # Let's perform a rough conversion check.
                    conv_residual = line.invoice_id.currency_id._convert(
                        resid_invoice, self.payment_currency_id, company, p_date
                    )
                    # If amount_to_pay is close to converted residual, it's a full payment attempt.
                    if abs(line.amount_to_pay - conv_residual) < (
                        conv_residual * 0.05
                    ):  # 5% tolerance
                        is_full_invoice_payment = True

            if is_full_payment_usage or is_full_invoice_payment:
                try:
                    (invoice_line + payment_line).reconcile()

                    estimated_amt = line.amount_to_pay
                    sym = self.payment_currency_id.symbol or "$"
                    message_body += f"<li>{line.invoice_id.name}: {estimated_amt} {sym} (Coincidencia Estándar)</li>"
                    continue
                except Exception:
                    # Si la conciliación estándar falla (ej. bloqueos inesperados),
                    # recurrimos a la lógica parcial manual más abajo.
                    pass

            # --- CONCILIACIÓN PARCIAL MANUAL (RESTORED FIX) ---
            _logger.info(f"[STD-REC] Processing Line: {line.invoice_id.name}")

            i_date = (
                line.invoice_id.invoice_date
                or line.invoice_id.date
                or fields.Date.context_today(self)
            )

            amount_payment_curr = line.amount_to_pay
            amount_company = 0.0

            # 1. Determinar Tasa para el Asiento
            # PRIORIDAD: Usar tasa de la fecha del pago (Tabla) para corregir valoraciones incorrectas (ej. 1:1).
            # Si el pago original se registró mal (1 USD = 1 BsF), al aplicarlo ahora queremos
            # reconocer la GANANCIA/PERDIDA cambiaria real (1 USD = 300 BsF).
            p_date = self.payment_id.date or fields.Date.context_today(self)

            # Calculamos Amount Company usando la tasa oficial de la fecha del pago
            if self.payment_currency_id != company.currency_id:
                amount_company = self.payment_currency_id._convert(
                    amount_payment_curr, company.currency_id, company, p_date
                )
            else:
                amount_company = amount_payment_curr

            # Fallback legacy: Si la conversion da 0 o fallo, intentar implicita
            if amount_company == 0 and payment_line.amount_currency:
                ratio = abs(payment_line.balance) / abs(payment_line.amount_currency)
                amount_company = amount_payment_curr * ratio

            amount_company = company.currency_id.round(amount_company)
            _logger.info(f"[STD-REC] Amount Company: {amount_company}")

            # 2. Calcular Importe en Divisa para el Asiento
            (debit_move, credit_move) = (
                (invoice_line, payment_line)
                if invoice_line.debit > 0
                else (payment_line, invoice_line)
            )

            # --- REGLA DE ORO: Si moneda destino != moneda pago, usar 'amount_converted' del wizard ---
            # Esto garantiza que lo que vio el usuario (ej. 300 BsF) sea lo que se aplique.

            # Ajuste de Amount Company si la factura es en moneda local
            # Caso: Factura VEF, Pago USD. Wizard dice 300 BsF.
            # Amount Company debe ser 300 BsF.
            if line.invoice_id.currency_id == company.currency_id:
                amount_company = line.amount_converted
                _logger.info(
                    f"[STD-REC] Override Amount Company from Wizard: {amount_company}"
                )

            # Lado Débito
            if debit_move.currency_id:
                if debit_move == payment_line:
                    debit_amt_curr = amount_payment_curr
                else:
                    if debit_move.currency_id == self.payment_currency_id:
                        debit_amt_curr = amount_payment_curr
                    else:
                        # Usar valor explícito del wizard
                        debit_amt_curr = line.amount_converted
            else:
                debit_amt_curr = 0.0

            _logger.info(f"[STD-REC] Debit Amt Curr: {debit_amt_curr}")

            # Lado Crédito
            if credit_move.currency_id:
                if credit_move == payment_line:
                    credit_amt_curr = amount_payment_curr
                else:
                    if credit_move.currency_id == self.payment_currency_id:
                        credit_amt_curr = amount_payment_curr
                    else:
                        # Usar valor explícito del wizard
                        credit_amt_curr = line.amount_converted
            else:
                credit_amt_curr = 0.0

            partial = self.env["account.partial.reconcile"].create(
                {
                    "debit_move_id": debit_move.id,
                    "credit_move_id": credit_move.id,
                    "amount": amount_company,
                    "debit_amount_currency": debit_amt_curr,
                    "credit_amount_currency": credit_amt_curr,
                }
            )

            # --- DISPARADOR DE DIFERENCIA EN CAMBIO ---
            _logger.info("[STD-REC] Invalidating Cache to ensure status update...")
            (debit_move + credit_move).invalidate_recordset(
                ["reconciled", "amount_residual", "amount_residual_currency"]
            )

            _logger.info("[STD-REC] Checking Full Reconcile...")
            if hasattr(debit_move, "check_full_reconcile"):
                (debit_move + credit_move).check_full_reconcile()

            # 2. Fallback
            # Re-read status after check_full_reconcile potential update
            (debit_move + credit_move).invalidate_recordset(["reconciled"])
            is_fully_reconciled = debit_move.reconciled and credit_move.reconciled
            _logger.info(f"[STD-REC] Fully Reconciled? {is_fully_reconciled}")

            if not is_fully_reconciled:
                # INSPECTION BLOCK
                _logger.info("--- INSPECTING METHODS ---")
                move_attrs = dir(self.env["account.move"])
                partial_attrs = dir(partial)

                # Filter for relevant names to avoid massive logs
                keywords = ["exchange", "diff", "rate", "entry"]
                ex_move_methods = [
                    m for m in move_attrs if any(k in m for k in keywords)
                ]
                ex_partial_methods = [
                    m for m in partial_attrs if any(k in m for k in keywords)
                ]

                _logger.info(
                    f"[INSPECT] account.move methods matching keywords: {ex_move_methods}"
                )
                _logger.info(
                    f"[INSPECT] partial methods matching keywords: {ex_partial_methods}"
                )

                # if hasattr(
                #     self.env["account.move"], "_create_exchange_difference_move"
                # ):
                #     _logger.info("[STD-REC] Forcing _create_exchange_difference_move")
            #     self.env["account.move"]._create_exchange_difference_move(partial)
                # elif hasattr(partial, "create_exchange_rate_entry"):
                #     partial.create_exchange_rate_entry()

                # --- MANUAL FALLBACK FOR PARTIAL PAYMENTS ---
                # CONDITIONAL:
                # If we are using a PARTIAL amount of the payment (Wizard Amount < Payment Balance),
                # Odoo's standard logic usually works (creates the 675 BsF standard entry).
                # In that case, we SKIP our manual entry to avoid duplication.
                # If we are using the FULL remaining balance, Odoo sometimes misses it, so we force ours.
                
                # Check residual before this reconciliation? No, 'partial' is already created.
                # We can check if the payment is now fully reconciled.
                # Or compare the amount we just applied (amount_payment_curr) vs the payment residual BEFORE this.
                # Better heuristic based on user input:
                # If amount_payment_curr (what we applied) < payment_line.amount_currency (original/residual)?
                
                # Let's trust the User's observation: "cuando se edita el monto... es menor al saldo disponible".
                # We need to fetch the residual of the payment line.
                # WARNING: 'payment_line' recordset might be stale? We invalidated cache above.
                
                # --- MANUAL FALLBACK FOR PARTIAL PAYMENTS ---
                # UNIFIED STRATEGY (User Approved):
                # Always force our Manual Exchange Move (mathematically correct).
                # If Odoo generates a standard move (often inaccurate or duplicate), 
                # _create_manual_exchange_move handles the "Search and Destroy" cleanup.
                
                _logger.info(f"[STD-REC] Conciliation Done. Triggering Unified Manual Exchange Logic.")
                (debit_move + credit_move).invalidate_recordset(["reconciled"])
                self._create_manual_exchange_move(invoice_line, payment_line, partial)

            # Log más detallado
            msg_curr = ""
            if self.payment_currency_id != company.currency_id:
                msg_curr = f" ({amount_payment_curr} {self.payment_currency_id.symbol})"
            message_body += f"<li>{line.invoice_id.name}: {amount_company} {company.currency_id.symbol}{msg_curr}</li>"

        message_body += "</ul>"
        self.payment_id.message_post(body=message_body)

        return {"type": "ir.actions.act_window_close"}

    def _process_third_party_reclassification(self):
        total_amount = self.amount_to_apply
        journal = self.env.company.intercompany_payment_journal_id
        if not journal:
            journal = self.env["account.journal"].search(
                [("type", "=", "general"), ("company_id", "=", self.env.company.id)],
                limit=1,
            )
        if not journal:
            raise UserError(_("Falta Diario General (o configurado en la compañía)."))

        # --- CONVERSION MONEDA (FIX) ---
        company = self.env.company
        p_date = self.payment_id.date or fields.Date.context_today(self)
        payment_currency = (
            self.payment_currency_id
            or self.payment_id.currency_id
            or company.currency_id
        )

        # Calcular monto en Moneda Compañía (VEF)
        # Esto es lo que realmente vale el movimiento contablemente
        total_amount_company = total_amount
        if payment_currency != company.currency_id:
            total_amount_company = payment_currency._convert(
                total_amount, company.currency_id, company, p_date
            )

        # Detectar si es Cliente o Proveedor para dirección del asiento
        is_supplier = self.payment_id.partner_type == "supplier"

        if is_supplier:
            # PROVEEDOR (Payable)
            account_A = self.payment_id.partner_id.property_account_payable_id.id
            account_B = self.filter_partner_id.property_account_payable_id.id

            # Asiento:
            # Linea 1 (vs Pago): Credit
            # Linea 2 (vs Factura): Debit
            debit_A, credit_A = 0, total_amount_company
            debit_B, credit_B = total_amount_company, 0

            # Signos para amount_currency
            amt_curr_A = -total_amount
            amt_curr_B = total_amount

            target_acc_type = "liability_payable"
        else:
            # CLIENTE (Receivable)
            account_A = self.payment_id.partner_id.property_account_receivable_id.id
            account_B = self.filter_partner_id.property_account_receivable_id.id

            # Asiento:
            # Linea 1 (vs Pago): Debit
            # Linea 2 (vs Factura): Credit
            debit_A, credit_A = total_amount_company, 0
            debit_B, credit_B = 0, total_amount_company

            # Signos para amount_currency
            amt_curr_A = total_amount
            amt_curr_B = -total_amount

            target_acc_type = "asset_receivable"

        move_vals = {
            "journal_id": journal.id,
            "date": p_date,  # Usar fecha de pago para mantener coherencia cambiaria
            "ref": f"Reclasif Global: {self.payment_id.name}",
            "move_type": "entry",
            "line_ids": [
                Command.create(
                    {
                        "partner_id": self.payment_id.partner_id.id,
                        "account_id": account_A,
                        "debit": debit_A,
                        "credit": credit_A,
                        "name": "Traslado Global (Origen)",
                        "currency_id": payment_currency.id,
                        "amount_currency": amt_curr_A,
                    }
                ),
                Command.create(
                    {
                        "partner_id": self.filter_partner_id.id,
                        "account_id": account_B,
                        "debit": debit_B,
                        "credit": credit_B,
                        "name": "Recepción Global (Destino)",
                        "currency_id": payment_currency.id,
                        "amount_currency": amt_curr_B,
                    }
                ),
            ],
        }
        bridge = self.env["account.move"].create(move_vals)
        bridge.action_post()

        # 2. Conciliar PAGO vs PUENTE (Lado A)
        payment_line = self.payment_id.line_ids.filtered(
            lambda l: l.account_type == target_acc_type
        )
        if payment_line:
            (payment_line + bridge.line_ids[0]).reconcile()

        # 3. Conciliar PUENTE (Lado B) vs MÚLTIPLES FACTURAS
        bridge_contra_line = bridge.line_ids[1]
        lines_to_process = self.line_ids.filtered(lambda l: l.amount_to_pay > 0)

        for line in lines_to_process:
            invoice_lines = line.invoice_id.line_ids.filtered(
                lambda l: l.account_type == target_acc_type and not l.reconciled
            )
            if not invoice_lines:
                continue

            # --- FIXED LOGIC FOR CROSS-CURRENCY EXCHANGE DIFFERENCE (THIRD PARTY) ---

            # 1. Determine Valuation Date (Historical)
            i_date = (
                line.invoice_id.invoice_date
                or line.invoice_id.date
                or fields.Date.context_today(self)
            )

            amount_payment_curr = line.amount_to_pay
            amount_company_line = 0.0

            # 2. Calculate Amount in Company Currency (Historical Rate)
            if payment_currency != company.currency_id:
                amount_company_line = payment_currency._convert(
                    amount_payment_curr, company.currency_id, company, i_date
                )
            else:
                amount_company_line = amount_payment_curr

            amount_company_line = company.currency_id.round(amount_company_line)

            # Determining lines
            debit_line = (
                invoice_lines[0] if invoice_lines[0].debit > 0 else bridge_contra_line
            )
            credit_line = (
                bridge_contra_line
                if bridge_contra_line.credit > 0
                else invoice_lines[0]
            )

            # 3. Assign Amount Currencies Logic & Capping
            debit_amt_curr = 0.0
            credit_amt_curr = 0.0

            # DEBIT SIDE
            if debit_line.currency_id:
                if debit_line == bridge_contra_line:
                    debit_amt_curr = amount_payment_curr
                else:
                    if debit_line.currency_id == payment_currency:
                        debit_amt_curr = amount_payment_curr
                    else:
                        debit_amt_curr = company.currency_id._convert(
                            amount_company_line, debit_line.currency_id, company, i_date
                        )
                        resid = abs(debit_line.amount_residual_currency)
                        if debit_amt_curr > resid and resid > 0.01:
                            debit_amt_curr = resid

            # CREDIT SIDE
            if credit_line.currency_id:
                if credit_line == bridge_contra_line:
                    credit_amt_curr = amount_payment_curr
                else:
                    if credit_line.currency_id == payment_currency:
                        credit_amt_curr = amount_payment_curr
                    else:
                        credit_amt_curr = company.currency_id._convert(
                            amount_company_line,
                            credit_line.currency_id,
                            company,
                            i_date,
                        )
                        resid = abs(credit_line.amount_residual_currency)
                        if credit_amt_curr > resid and resid > 0.01:
                            credit_amt_curr = resid

            _logger.info(f"[WIZARD] PROCESSING LINE {line.invoice_id.name}")
            _logger.info(f"[WIZARD] Amount Company (VEF): {amount_company_line}")
            _logger.info(f"[WIZARD] Debit Amt Curr (USD): {debit_amt_curr}")

            # TRY NATIVE RECONCILE FIRST
            # This ensures Odoo handles exchange differences automatically if possible.
            try:
                _logger.info("[3RD-PTY] Attempting Native Reconcile...")
                (debit_line + credit_line).reconcile()
                continue
            except Exception as e:
                _logger.info(
                    f"[3RD-PTY] Native Reconcile Failed: {e}. Falling back to manual..."
                )

            partial = self.env["account.partial.reconcile"].create(
                {
                    "debit_move_id": debit_line.id,
                    "credit_move_id": credit_line.id,
                    "amount": amount_company_line,
                    "debit_amount_currency": debit_amt_curr,
                    "credit_amount_currency": credit_amt_curr,
                }
            )

            # 4. Trigger Exchange Difference
            if hasattr(debit_line, "check_full_reconcile"):
                _logger.info("[WIZARD] Calling check_full_reconcile()")
                (debit_line + credit_line).check_full_reconcile()

            # Fallback Trigger with Manual Move
            # Ensure we update status first
            (debit_line + credit_line).invalidate_recordset(["reconciled"])
            is_fully_reconciled = debit_line.reconciled and credit_line.reconciled

            if not is_fully_reconciled:
                 _logger.info(
                    "[3RD-PTY] Not fully reconciled after manual partial. Attempting manual exchange move..."
                )
                 self._create_manual_exchange_move(debit_line, credit_line, partial)

            # Fallback Trigger

            # Fallback Trigger
            is_fully_reconciled = debit_line.reconciled and credit_line.reconciled
            _logger.info(
                f"[WIZARD] Reconciled Status -> Debit: {debit_line.reconciled}, Credit: {credit_line.reconciled}"
            )

            # NOTE: Exchange difference logic already handled by _create_manual_exchange_move
            # at line 1291. Removed redundant/incorrect call to _create_exchange_difference_move
            # which expects a dict, not a partial record.

        return {"type": "ir.actions.act_window_close"}

    def _process_inter_company_transfer(self):
        comp_A, comp_B = self.payment_company_id, self.filter_company_id

        if not comp_A:
            raise UserError(_("No se ha detectado la Compañía del Pago."))
        if not comp_B:
            raise UserError(_("No se ha detectado la Compañía Destino (Facturas)."))

        amount_total = self.amount_to_apply
        p_date = self.payment_id.date or fields.Date.context_today(self)
        payment_currency = self.payment_currency_id or self.payment_id.currency_id

        # --- OBTENER TASA DEL PAGO ORIGINAL ---
        payment_move = self.payment_id.move_id
        tax_today = getattr(payment_move, 'tax_today', 0.0)
        
        # Calcular montos en moneda de cada compañía
        # En Co A (donde está el pago)
        total_amount_company_A = amount_total
        if payment_currency != comp_A.currency_id:
            if tax_today > 0:
                total_amount_company_A = comp_A.currency_id.round(amount_total * tax_today)
            else:
                total_amount_company_A = payment_currency._convert(
                    amount_total, comp_A.currency_id, comp_A, p_date
                )

        # En Co B (donde están las facturas)
        total_amount_company_B = amount_total
        if payment_currency != comp_B.currency_id:
            # Si Co B tiene la misma moneda que Co A, usamos el mismo monto
            if comp_B.currency_id == comp_A.currency_id:
                total_amount_company_B = total_amount_company_A
            else:
                total_amount_company_B = payment_currency._convert(
                    amount_total, comp_B.currency_id, comp_B, p_date
                )

        # --- MONTOS USD (DUALIDAD) ---
        # Si el pago es en USD, el monto USD es amount_total.
        # Si no, usamos tax_today para obtener el equivalente USD.
        amount_usd = amount_total
        if payment_currency.name != 'USD':
            amount_usd = (amount_total / tax_today) if tax_today > 0 else 0.0

        # Determinar flujo (Inbound/Outbound) segun partner_type
        is_supplier = self.payment_id.partner_type == "supplier"

        if is_supplier:
            # OUTBOUND: A paga algo por B
            acc_A_payable = self.payment_id.partner_id.with_company(comp_A).property_account_payable_id.id
            acc_B_payable = self.filter_partner_id.with_company(comp_B).property_account_payable_id.id
            acc_B_in_A = comp_A.intercompany_receivable_account_id.id
            acc_A_in_B = comp_B.intercompany_payable_account_id.id

            # Move A
            vals_A_L1 = {
                "account_id": acc_A_payable,
                "debit": 0,
                "credit": total_amount_company_A,
                "partner_id": self.payment_id.partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": -amount_total,
                "debit_usd": 0.0,
                "credit_usd": amount_usd,
            }
            vals_A_L2 = {
                "account_id": acc_B_in_A,
                "debit": total_amount_company_A,
                "credit": 0,
                "partner_id": comp_B.partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": amount_total,
                "debit_usd": amount_usd,
                "credit_usd": 0.0,
            }

            # Move B
            vals_B_L1 = {
                "account_id": acc_A_in_B,
                "debit": 0,
                "credit": total_amount_company_B,
                "partner_id": comp_A.partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": -amount_total,
                "debit_usd": 0.0,
                "credit_usd": amount_usd,
            }
            vals_B_L2 = {
                "account_id": acc_B_payable,
                "debit": total_amount_company_B,
                "credit": 0,
                "partner_id": self.filter_partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": amount_total,
                "debit_usd": amount_usd,
                "credit_usd": 0.0,
            }
            target_acc_type = "liability_payable"
        else:
            # INBOUND: A cobra algo para B
            acc_A_receivable = self.payment_id.partner_id.with_company(comp_A).property_account_receivable_id.id
            acc_B_receivable = self.filter_partner_id.with_company(comp_B).property_account_receivable_id.id
            acc_B_in_A = comp_A.intercompany_payable_account_id.id
            acc_A_in_B = comp_B.intercompany_receivable_account_id.id

            # Move A
            vals_A_L1 = {
                "account_id": acc_A_receivable,
                "debit": total_amount_company_A,
                "credit": 0,
                "partner_id": self.payment_id.partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": amount_total,
                "debit_usd": amount_usd,
                "credit_usd": 0.0,
            }
            vals_A_L2 = {
                "account_id": acc_B_in_A,
                "debit": 0,
                "credit": total_amount_company_A,
                "partner_id": comp_B.partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": -amount_total,
                "debit_usd": 0.0,
                "credit_usd": amount_usd,
            }

            # Move B
            vals_B_L1 = {
                "account_id": acc_A_in_B,
                "debit": total_amount_company_B,
                "credit": 0,
                "partner_id": comp_A.partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": amount_total,
                "debit_usd": amount_usd,
                "credit_usd": 0.0,
            }
            vals_B_L2 = {
                "account_id": acc_B_receivable,
                "debit": 0,
                "credit": total_amount_company_B,
                "partner_id": self.filter_partner_id.id,
                "currency_id": payment_currency.id,
                "amount_currency": -amount_total,
                "debit_usd": 0.0,
                "credit_usd": amount_usd,
            }
            target_acc_type = "asset_receivable"

        # --- VALIDACIONES DE CUENTAS GLOBALES ---
        if not acc_B_in_A:
            raise UserError(_(f"Falta configurar Cuentas Inter-Cía en la Configuración de '{comp_A.name}'."))
        if not acc_A_in_B:
            raise UserError(_(f"Falta configurar Cuentas Inter-Cía en la Configuración de '{comp_B.name}'."))

        # --- CREACION ASIENTO A ---
        journal_A = comp_A.intercompany_payment_journal_id or self.env["account.journal"].search([("type", "=", "general"), ("company_id", "=", comp_A.id)], limit=1)
        
        vals_move_A = {
            "journal_id": journal_A.id,
            "company_id": comp_A.id,
            "move_type": "entry",
            "ref": f"InterCo Global -> {comp_B.name}",
            "date": p_date,
            "line_ids": [Command.create(vals_A_L1), Command.create(vals_A_L2)],
        }
        if tax_today > 0:
            vals_move_A.update({'tax_today': tax_today, 'edit_trm': True})

        move_A = self.env["account.move"].sudo().create(vals_move_A)
        move_A.action_post()

        # Conciliar A: Linea 0 vs Pago
        payment_line = self.payment_id.line_ids.filtered(lambda l: l.account_type == target_acc_type)
        if payment_line:
            (payment_line + move_A.line_ids[0]).reconcile()

        # --- CREACION ASIENTO B ---
        journal_B = comp_B.intercompany_payment_journal_id or self.env["account.journal"].search([("type", "=", "general"), ("company_id", "=", comp_B.id)], limit=1)
        
        vals_move_B = {
            "journal_id": journal_B.id,
            "company_id": comp_B.id,
            "move_type": "entry",
            "ref": f"InterCo Global <- {comp_A.name}",
            "date": p_date,
            "line_ids": [Command.create(vals_B_L1), Command.create(vals_B_L2)],
        }
        if tax_today > 0:
            vals_move_B.update({'tax_today': tax_today, 'edit_trm': True})

        move_B = self.env["account.move"].with_company(comp_B).sudo().create(vals_move_B)
        move_B.action_post()

        # Conciliar B: Linea 1 vs Facturas
        transfer_contra_line = move_B.line_ids[1]
        lines_to_process = self.line_ids.filtered(lambda l: l.amount_to_pay > 0)

        for line in lines_to_process:
            invoice_lines = line.invoice_id.line_ids.filtered(
                lambda l: l.account_type == target_acc_type and not l.reconciled
            )
            if not invoice_lines: continue

            # Monto en moneda de la compañía B para esta factura
            ratio = line.amount_to_pay / amount_total if amount_total else 0
            amount_line_company_B = comp_B.currency_id.round(total_amount_company_B * ratio)

            if invoice_lines[0].debit > 0:
                debit_line, credit_line = invoice_lines[0], transfer_contra_line
            else:
                debit_line, credit_line = transfer_contra_line, invoice_lines[0]

            # Amount Currencies: Siempre intentar pasar el monto en divisa si el campo currency_id está seteado
            debit_amt_curr = 0.0
            if debit_line.currency_id:
                debit_amt_curr = line.amount_converted if debit_line == invoice_lines[0] else line.amount_to_pay

            credit_amt_curr = 0.0
            if credit_line.currency_id:
                credit_amt_curr = line.amount_converted if credit_line == invoice_lines[0] else line.amount_to_pay

            # Amount USD Parcial (Dualidad)
            # Intentamos usar la valoracion de la FACTURA para que en el widget de dualidad
            # el pago cubra exactamente lo que se debe. El diferencial de cambio queda en el asiento.
            if line.currency_id.name == 'USD':
                amount_line_usd = abs(line.amount_converted)
            else:
                inv_rate = line.invoice_id.tax_today or 1.0
                amount_line_usd = abs(amount_line_company_B / inv_rate) if inv_rate > 0 else 0.0

            self.env["account.partial.reconcile"].create({
                "debit_move_id": debit_line.id,
                "credit_move_id": credit_line.id,
                "amount": amount_line_company_B,
                "amount_usd": amount_line_usd, # CAMPO DUALIDAD
                "debit_amount_currency": debit_amt_curr,
                "credit_amount_currency": credit_amt_curr,
            })

        return {"type": "ir.actions.act_window_close"}


class PaymentSplitLine(models.TransientModel):
    _name = "account.payment.split.line"
    _description = "Línea de Distribución de Pago"

    wizard_id = fields.Many2one("account.payment.split.wizard")
    invoice_id = fields.Many2one("account.move", string="Factura", required=True)

    currency_id = fields.Many2one(related="invoice_id.currency_id")

    amount_residual = fields.Monetary(
        string="Saldo Pendiente", currency_field="currency_id", readonly=True
    )

    # Este es el campo clave: Monto a aplicar a ESTA factura (Moneda del Pago)
    amount_to_pay = fields.Monetary(
        string="Aplicar (Moneda Pago)", currency_field="payment_currency_id"
    )
    # MODIFICADO: Dejamos de usar related para evitar problemas en onchange de one2many
    # payment_currency_id = fields.Many2one(related="wizard_id.payment_currency_id")
    payment_currency_id = fields.Many2one("res.currency", string="Moneda de Pago")

    # NUEVO: Fecha del pago para el ratio de conversion
    payment_date = fields.Date(string="Fecha del Pago")

    # Nuevo: Monto equivalente en la moneda de la factura
    amount_converted = fields.Monetary(
        string="Equivalente (Moneda Factura)", currency_field="currency_id"
    )

    @api.onchange("amount_to_pay")
    def _onchange_amount_to_pay(self):
        for r in self:
            if not r.amount_to_pay:
                r.amount_converted = 0.0
                continue

            payment_curr = r.payment_currency_id
            invoice_curr = r.currency_id

            if payment_curr and invoice_curr and payment_curr != invoice_curr:
                # Linea: Usar Tasa ACTUAL (Payment Date strictly)
                # Fallback: Try fetching from Wizard Parent if Line Date is missing (Client side issue)
                p_date = r.payment_date
                if not p_date and r.wizard_id and r.wizard_id.payment_id:
                     p_date = r.wizard_id.payment_id.date
                
                # Final Fallback
                p_date = p_date or fields.Date.context_today(r)

                conversion_date = p_date

                val = payment_curr._convert(
                    r.amount_to_pay, invoice_curr, r.env.company, conversion_date
                )

                # Capping Visual REMOVED
                # resid = abs(r.amount_residual)
                # if abs(val) > resid + 0.01:
                #     r.amount_converted = resid * (1 if val >= 0 else -1)
                # else:
                r.amount_converted = val
            else:
                r.amount_converted = r.amount_to_pay

    @api.onchange("amount_converted")
    def _onchange_amount_converted(self):
        for r in self:
            if not r.amount_converted:
                # Si borran este, no borramos el principal por seguridad, o si?
                # Mejor asumimos que quieren borrarlo.
                # r.amount_to_pay = 0.0
                continue

            payment_curr = r.payment_currency_id
            invoice_curr = r.currency_id

            if payment_curr and invoice_curr and payment_curr != invoice_curr:
                # Inversa: Convertir de Factura -> Pago
                # MODIFICADO: Usar fecha local
                # REVERTIDO: Usar Tasa Actual (Max) para que el monto a pagar sea correcto a hoy.
                # Si el usuario pone 10$, quiere pagar 10$ a tasa de hoy (ej. 300), no a tasa vieja.
                p_date = r.payment_date or fields.Date.context_today(r)
                i_date = r.invoice_id.invoice_date or p_date
                conversion_date = max(p_date, i_date)

                # OJO: La conversión inversa directa puede tener diferencias de redondeo
                r.amount_to_pay = invoice_curr._convert(
                    r.amount_converted, payment_curr, r.env.company, conversion_date
                )
            else:
                r.amount_to_pay = r.amount_converted

            r._compute_est_exchange_diff()

    # Nuevo Campo para mostrar el diferencial estimado
    est_exchange_diff = fields.Monetary(
        string="Dif. Cambio Est.",
        currency_field="company_currency_id",
        compute="_compute_est_exchange_diff",
        help="Diferencia estimada entre el valor del pago y el valor de la deuda original en moneda base.",
    )
    company_currency_id = fields.Many2one(
        "res.currency", related="wizard_id.company_id.currency_id"
    )

    @api.depends("amount_to_pay", "amount_converted", "payment_date", "invoice_id")
    def _compute_est_exchange_diff(self):
        for r in self:
            if not r.amount_to_pay or not r.amount_converted:
                r.est_exchange_diff = 0.0
                continue

            # Valor del Pago en Moneda Base (VEF) - Tasa Pago
            val_payment = r.amount_to_pay
            if r.payment_currency_id and r.payment_currency_id != r.company_currency_id:
                p_date = r.payment_date or fields.Date.context_today(r)
                val_payment = r.payment_currency_id._convert(
                    r.amount_to_pay, r.company_currency_id, r.env.company, p_date
                )

            # Valor de la Factura Cancelada en Moneda Base (VEF) - Tasa Factura
            val_invoice = r.amount_converted
            if r.currency_id and r.currency_id != r.company_currency_id:
                i_date = (
                    r.invoice_id.invoice_date
                    or r.invoice_id.date
                    or fields.Date.context_today(r)
                )
                val_invoice = r.currency_id._convert(
                    r.amount_converted, r.company_currency_id, r.env.company, i_date
                )

            r.est_exchange_diff = val_payment - val_invoice
