from odoo import models, fields, api, _

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # Campo auxiliar para la vista
    journal_currency_id = fields.Many2one('res.currency', related='journal_id.currency_id', readonly=True)
    
    homologacion_activa = fields.Boolean(
        related='company_id.homologacion_activa',
        string='Homologación Activa',
    )

    # Campo para controlar visibilidad en XML
    # Si falso -> Ocultar IGTF
    hide_igtf_check = fields.Boolean(compute='_compute_hide_igtf_check', store=False)

    @api.depends('journal_id', 'company_id')
    def _compute_hide_igtf_check(self):
        for wizard in self:
            # Solo aplica IGTF para empresas venezolanas
            if not (wizard.company_id.homologacion_activa and getattr(wizard.company_id, 'is_ve_company', False)):
                wizard.hide_igtf_check = True
                continue

            company_currency = wizard.company_id.currency_id
            journal_currency = wizard.journal_id.currency_id or company_currency

            # IGTF aplica cuando el diario es en divisas (NO VEF/VES/VED)
            is_journal_vef = journal_currency.name in ('VEF', 'VES', 'VED')
            # Ocultar el check cuando el diario ES VEF (no aplica IGTF)
            wizard.hide_igtf_check = is_journal_vef

    @api.onchange('journal_id', 'currency_id')
    def _onchange_journal_igtf_enforcement(self):
        for wizard in self:
            if not wizard.journal_id:
                continue

            # Solo forzar IGTF para empresas venezolanas
            if not (wizard.company_id.homologacion_activa and getattr(wizard.company_id, 'is_ve_company', False)):
                wizard.aplicar_igtf_divisa = False
                wizard.hide_igtf_check = True
                continue

            company_currency = wizard.company_id.currency_id
            journal_currency = wizard.journal_id.currency_id or company_currency

            # IGTF aplica cuando el diario es en divisas (NO VEF/VES/VED)
            is_journal_vef = journal_currency.name in ('VEF', 'VES', 'VED')

            # Activar IGTF si el diario es en divisa extranjera (USD, EUR, etc.)
            wizard.aplicar_igtf_divisa = not is_journal_vef
            wizard.hide_igtf_check = is_journal_vef

    @api.onchange('aplicar_igtf_divisa')
    def _onchange_enforce_igtf_check(self):
        for wizard in self:
            if not wizard.journal_id:
                return

            # Solo restringir IGTF para empresas venezolanas
            if not (wizard.company_id.homologacion_activa and getattr(wizard.company_id, 'is_ve_company', False)):
                return

            company_currency = wizard.company_id.currency_id
            journal_currency = wizard.journal_id.currency_id or company_currency

            # La restricción aplica cuando el diario es en divisas (NO VEF/VES/VED)
            is_journal_vef = journal_currency.name in ('VEF', 'VES', 'VED')

            if not is_journal_vef and not wizard.aplicar_igtf_divisa:
                wizard.aplicar_igtf_divisa = True
                return {
                    'warning': {
                        'title': _("Restricción Fiscal"),
                        'message': _("El pago desde cuentas en divisas requiere la aplicación de IGTF obligatoria.")
                    }
                }

    def _create_payment_vals_from_wizard(self, batch_result):
        res = super()._create_payment_vals_from_wizard(batch_result)
        # Pasar las facturas al pago para que action_post las tenga disponibles para la ND de IGTF
        if self.aplicar_igtf_divisa:
            lines = batch_result['lines']
            res['igtf_invoice_ids'] = [(6, 0, lines.move_id.filtered(lambda m: m.is_invoice()).ids)]
        return res

    @api.onchange('aplicar_igtf_divisa', 'amount', 'currency_id')
    def _mount_igtf(self):
        for wizard in self:
            if wizard.aplicar_igtf_divisa and wizard.currency_id.name == 'USD':
                # IGTF se calcula sobre Base Imponible + IVA (wizard.amount ya incluye ambos)
                igtf_base = wizard.amount
                
                wizard.mount_igtf = wizard.currency_id.round(igtf_base * wizard.igtf_divisa_porcentage / 100)
                wizard.amount_total_pagar = igtf_base + wizard.mount_igtf
            else:
                wizard.mount_igtf = 0
                wizard.amount_total_pagar = wizard.amount
