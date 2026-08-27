from odoo import api, fields, models


class L10nFRSendVatReportBankAccountLine(models.TransientModel):
    _name = 'l10n_fr_reports.send.vat.report.bank.account.line'
    _description = "Bank Account Line for French Vat Report"

    company_partner_id = fields.Many2one(
        comodel_name='res.partner',
        default=lambda self: self.env.company.partner_id,
    )
    bank_partner_id = fields.Many2one(
        comodel_name='res.partner.bank',
        domain="[('partner_id', '=', company_partner_id), ('partner_id.country_code', '=', 'FR')]",
    )
    bank_id = fields.Many2one(
        comodel_name='res.bank',
        related='bank_partner_id.bank_id',
        store=True,
        readonly=False,
    )
    account_number = fields.Char(
        string="IBAN",
        related='bank_partner_id.acc_number',
    )
    bank_bic = fields.Char(
        string="BIC Code",
        related='bank_id.bic',
    )
    l10n_fr_send_vat_report_id = fields.Many2one('l10n_fr_reports.send.vat.report')
    currency_id = fields.Many2one('res.currency', related="l10n_fr_send_vat_report_id.currency_id")
    vat_amount = fields.Monetary()
    is_wrongly_configured = fields.Boolean(compute="_compute_is_wrongly_configured")

    @api.depends('account_number', 'bank_bic')
    def _compute_is_wrongly_configured(self):
        for line in self:
            line.is_wrongly_configured = line.bank_partner_id and (not line.bank_bic or not line.account_number)
