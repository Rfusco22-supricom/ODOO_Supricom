from odoo import models, fields, api, _

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    journal_currency_id = fields.Many2one('res.currency', related='journal_id.currency_id', readonly=True)
    
    hide_igtf_check = fields.Boolean(compute='_compute_hide_igtf_check', store=False)

    @api.depends('journal_id', 'company_id')
    def _compute_hide_igtf_check(self):
        for wizard in self:
            # Si el módulo no está activo o el contacto no es de Venezuela, ocultar siempre
            is_venezuela = wizard.partner_id.country_id and wizard.partner_id.country_id.code == 'VE'
            if not wizard.company_id.supricom_fl_igtf_enabled or not is_venezuela:
                wizard.hide_igtf_check = True
                continue

            journal_currency = wizard.journal_id.currency_id or wizard.company_id.currency_id
            
            # IGTF aplica cuando el diario es en divisa (no VEF/VES)
            is_journal_vef = journal_currency.name in ('VEF', 'VES', 'VED')
            wizard.hide_igtf_check = is_journal_vef

    @api.onchange('journal_id', 'currency_id')
    def _onchange_journal_igtf_enforcement(self):
        for wizard in self:
            is_venezuela = wizard.partner_id.country_id and wizard.partner_id.country_id.code == 'VE'
            if not wizard.company_id.supricom_fl_igtf_enabled or not is_venezuela:
                return

            if not wizard.journal_id:
                continue
                
            journal_currency = wizard.journal_id.currency_id or wizard.company_id.currency_id
            
            # IGTF obligatorio solo si el diario NO es en VEF/VES
            is_journal_vef = journal_currency.name in ('VEF', 'VES', 'VED')
            
            if not is_journal_vef:
                wizard.aplicar_igtf_divisa = True
            else:
                 wizard.aplicar_igtf_divisa = False
            
            wizard.hide_igtf_check = is_journal_vef

    @api.onchange('aplicar_igtf_divisa')
    def _onchange_enforce_igtf_check(self):
        for wizard in self:
            is_venezuela = wizard.partner_id.country_id and wizard.partner_id.country_id.code == 'VE'
            if not wizard.company_id.supricom_fl_igtf_enabled or not is_venezuela:
                return

            if not wizard.journal_id:
                 return

            journal_currency = wizard.journal_id.currency_id or wizard.company_id.currency_id
            
            # Solo forzar si el diario NO es VEF/VES
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
        is_venezuela = self.partner_id.country_id and self.partner_id.country_id.code == 'VE'
        if self.company_id.supricom_fl_igtf_enabled and getattr(self, 'aplicar_igtf_divisa', False) and is_venezuela:
            lines = batch_result['lines']
            res['igtf_invoice_ids'] = [(6, 0, lines.move_id.filtered(lambda m: m.is_invoice()).ids)]
        return res

    @api.onchange('aplicar_igtf_divisa', 'amount', 'currency_id')
    def _mount_igtf(self):
        for wizard in self:
            if not wizard.company_id.supricom_fl_igtf_enabled:
                return

            is_venezuela = wizard.partner_id.country_id and wizard.partner_id.country_id.code == 'VE'
            if wizard.aplicar_igtf_divisa and wizard.currency_id.name == 'USD' and is_venezuela:
                # IGTF se calcula sobre Base Imponible + IVA (wizard.amount ya incluye ambos)
                igtf_base = wizard.amount
                
                wizard.mount_igtf = wizard.currency_id.round(igtf_base * wizard.igtf_divisa_porcentage / 100)
                wizard.amount_total_pagar = igtf_base + wizard.mount_igtf
            else:
                wizard.mount_igtf = 0
                wizard.amount_total_pagar = wizard.amount
