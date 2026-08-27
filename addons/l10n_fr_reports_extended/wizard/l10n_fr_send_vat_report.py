from lxml import etree

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import cleanup_xml_node, float_compare, float_repr, format_date


class L10nFrSendVatReport(models.TransientModel):
    _inherit = "l10n_fr_reports.send.vat.report"

    bank_account_line_ids = fields.One2many(comodel_name='l10n_fr_reports.send.vat.report.bank.account.line', inverse_name='l10n_fr_send_vat_report_id')
    bank_account_line_count = fields.Integer(compute='_compute_bank_account_line_count')
    has_wrongly_configured_account = fields.Boolean(compute='_compute_has_wrongly_configured_account')
    is_vat_due = fields.Boolean(compute='_compute_vat_amount')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    vat_amount = fields.Monetary(compute='_compute_vat_amount')
    computed_vat_amount = fields.Monetary(compute='_compute_computed_vat_amount')

    def _compute_vat_amount(self):
        vat_carried_forward_line = self.env.ref('l10n_fr.tax_report_27')
        vat_payable_line = self.env.ref('l10n_fr.tax_report_32')
        result_vat_lines = (vat_carried_forward_line + vat_payable_line)
        for wizard in self:
            options = wizard._generate_new_l10n_fr_options()
            _dt_from, _dt_to, report, lines = wizard._decompose_l10_fr_options(options)
            column_value = 0
            report_line_id = 0
            # Looking for the line that have data (either the VAT credit or the VAT due)
            # Only one of these lines could have a value, not both of them.
            for line in lines:
                report_line_id = report._get_model_info_from_id(line['id'])[-1]
                if report_line_id in result_vat_lines.ids:
                    column = next(col for col in line['columns'] if col['expression_label'] == 'balance')
                    column_value = column['no_format'] or 0
                    if column_value:
                        break

            wizard.vat_amount = column_value
            wizard.is_vat_due = result_vat_lines.filtered(lambda line: line.id == report_line_id).code == vat_payable_line.code

    @api.depends('bank_account_line_ids.vat_amount')
    def _compute_computed_vat_amount(self):
        for wizard in self:
            wizard.computed_vat_amount = sum(wizard.bank_account_line_ids.mapped('vat_amount'))

    @api.depends('bank_account_line_ids.bank_partner_id')
    def _compute_has_wrongly_configured_account(self):
        for wizard in self:
            wizard.has_wrongly_configured_account = wizard.bank_account_line_ids.filtered('is_wrongly_configured')

    @api.depends('bank_account_line_ids.bank_partner_id')
    def _compute_bank_account_line_count(self):
        for wizard in self:
            wizard.bank_account_line_count = len(wizard.bank_account_line_ids.filtered('bank_partner_id'))

    def _check_bank_accounts(self):
        self.ensure_one()
        if self.bank_account_line_count > 3:
            raise UserError(_("You can use maximum 3 accounts."))
        if self.bank_account_line_ids.filtered(lambda line: not line.account_number or not line.bank_bic):
            raise UserError(_("All the selected bank accounts should have an IBAN and a bic code."))

    def _check_vat_to_pay(self):
        self.ensure_one()
        if any(float_compare(line.vat_amount, 0, precision_digits=line.currency_id.decimal_places) <= 0 for line in self.bank_account_line_ids):
            raise UserError(_("You can't set an amount with a negative value or a value set to 0."))

    def _get_formatted_payment_values(self):
        self.ensure_one()
        options = self._generate_new_l10n_fr_options()
        dt_from, dt_to, _report, _lines = self._decompose_l10_fr_options(options)
        formatted_payment_values = []
        for bank_account_line, code in zip(self.bank_account_line_ids, ['A', 'B', 'C']):
            formatted_payment_values.extend([
                {
                    'id': f'G{code}',
                    'iban': bank_account_line.account_number.replace(' ', ''),
                    'bic': bank_account_line.bank_bic.replace(' ', ''),
                },
                {
                    'id': f'H{code}',
                    'value': float_repr(
                        bank_account_line.currency_id.round(bank_account_line.vat_amount),
                        bank_account_line.currency_id.decimal_places,
                    ).replace('.', ','),
                },
                {
                    'id': f'K{code}',
                    'value': f'TVA1-{dt_from.strftime("%Y%m%d")}-{dt_to.strftime("%Y%m%d")}-3310CA3',
                },
            ])
        return formatted_payment_values

    def _get_formatted_edi_values(self, report, lines):
        edi_values = super()._get_formatted_edi_values(report, lines)
        if self.currency_id.is_zero(self.vat_amount):
            edi_values.append({
                'id': "KF",
                'value': "X",
            })
        return edi_values

    def _create_carryover_reimbursement_move(self):
        """ Creates an account.move representing the carryover reimbursement.

            This move debits the receivable accounts from the present tax group in the VAT
            closing entry for the period selected in the report options and moves the amount
            to a special account. The special account is used to track the reimbursement
            requested from the administration.

            :param options: dict - Report options for the VAT period selection.
            :return: account.move - Represents the carryover reimbursement.
        """
        options = self._generate_new_l10n_fr_options()
        dt_from, dt_to, report, lines = self._decompose_l10_fr_options(options)
        options = report.get_options({'no_format': True, 'date': {'date_from': dt_from, 'date_to': dt_to}, 'unfold_all': True})
        tax_closing_entry = self.env[report.custom_handler_model_name]._get_periodic_vat_entries(options)
        tax_receivable_account_ids = self.env['account.tax.group'].search(
            [('tax_receivable_account_id', '!=', False)]
        ).tax_receivable_account_id
        tax_carried_forward_line_ids = tax_closing_entry.line_ids.filtered(
            lambda line: line.account_id in tax_receivable_account_ids
        )

        lines = []
        if amount_carried_forward := sum(tax_carried_forward_line_ids.mapped('balance')):
            ratio = self.computed_vat_amount / amount_carried_forward
            for tax_line in tax_carried_forward_line_ids:
                lines.append(Command.create({
                    'account_id': tax_line.account_id.id,
                    'debit': 0,
                    'credit': tax_line.balance * ratio,
                    'name': _("VAT receivable"),
                }))
        else:
            # Case where tax closing is empty for this month while amount is carried forward from previous months
            # We put the amount arbitrarily on the receivable account of the tax group of 20%
            receivable_account = (
                self.env['account.chart.template'].ref('tax_group_tva_20', raise_if_not_found=False)
                or self.env['account.tax.group'].search([*self.env['account.tax.group']._check_company_domain(self.env.company.id)], limit=1)
            ).tax_receivable_account_id
            lines.append(Command.create({
                'account_id': receivable_account.id,
                'debit': 0,
                'credit': self.computed_vat_amount,
                'name': _("VAT receivable"),
            }))

        return self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': tax_closing_entry.journal_id.id,
            'date': dt_to,
            'line_ids': [
                *lines,
                Command.create({
                    'account_id': self.env['account.chart.template'].ref('pcg_445671').id,
                    'debit': self.computed_vat_amount,
                    'credit': 0,
                }),
            ],
        })

    def _check_values_export(self, options):
        super()._check_values_export(options)
        self._check_bank_accounts()
        self._check_vat_to_pay()

    def send_vat_return(self):
        super().send_vat_return()
        options = self._generate_new_l10n_fr_options()
        dt_from, dt_to, _report, _lines = self._decompose_l10_fr_options(options)
        if not self.is_vat_due and self.computed_vat_amount:
            if external_value_26 := self.env.ref('l10n_fr.tax_report_26_external_tag', raise_if_not_found=False):
                # xml_id in module l10n_fr_account may not be updated yet
                self.env['account.report.external.value'].with_context(ignore_tax_lock_date=True).create({
                    'name': _(
                        "Carryover reimbursement from %(date_from)s to %(date_to)s",
                        date_from=format_date(self.env, dt_from),
                        date_to=format_date(self.env, dt_to)
                    ),
                    'value': self.computed_vat_amount,
                    'date': dt_to,
                    'target_report_expression_id': external_value_26.id,
                    'company_id': self.env.company.id,
                })
            origin_expression = self.env.ref('l10n_fr.tax_report_27_carryover')
            self.env['account.report.external.value'].with_context(ignore_tax_lock_date=True).create({
                'name': _(
                    "Carryover reimbursement from %(date_from)s to %(date_to)s",
                    date_from=format_date(self.env, dt_from),
                    date_to=format_date(self.env, dt_to)
                ),
                'value': -self.computed_vat_amount,
                'date': dt_to,
                'target_report_expression_id': self.env.ref('l10n_fr.tax_report_22_applied_carryover').id,
                'carryover_origin_expression_label': origin_expression.label,
                'carryover_origin_report_line_id': origin_expression.report_line_id.id,
                'company_id': self.env.company.id,
            })

            carryover_reimbursement_move = self._create_carryover_reimbursement_move()
            if not self.test_interchange:
                carryover_reimbursement_move._post()

            self._send_reimbursement_xml_to_aspone(options)

    def _send_reimbursement_xml_to_aspone(self, options):
        """ Create declaration 3519 for each reimbursement asked for a bank account and send it to AspOne"""
        dt_from, dt_to, report, _lines = self._decompose_l10_fr_options(options)
        writer_vals, debtor_vals, aspone_vals, identif_vals = self._get_common_edi_vals(options)
        sender_company = report._get_sender_company_for_export(options)

        is_neutralized = self.env['ir.config_parameter'].sudo().get_param('database.is_neutralized')

        if sender_company.country_code == 'FR':
            company_location_code = 'DD'
        elif sender_company.country_id in self.env.ref('base.europe').country_ids:
            company_location_code = 'DE'
        else:
            company_location_code = 'DF'

        for index, bank_account_line in enumerate(self.bank_account_line_ids):
            declarations = {
                'type': 'RBT',
                'reference': "INFENT000042",  # internal reference to the emitor
                'writer': writer_vals,
                'debtor': debtor_vals,
                'edi_partner': aspone_vals,
                'recipients': [{'designation': self.recipient}],
                # T-IDENTIF form
                'identif': {
                    'millesime': "25",
                    'zones': identif_vals,
                },
                # 3519
                'form': {
                    'millesime': "25",
                    'name': "3519",
                    'zones': [{
                        'id': 'AA',
                        'iban': bank_account_line.account_number.replace(' ', ''),
                        'bic': bank_account_line.bank_bic.replace(' ', ''),
                    }, {
                        'id': 'FK',
                        'value': 'X'
                    }, {
                        'id': 'DN',
                        'value': float_repr(
                            bank_account_line.currency_id.round(bank_account_line.vat_amount),
                            bank_account_line.currency_id.decimal_places,
                        ).replace('.', ',')
                    }, {
                        'id': company_location_code,
                        'value': 'X',
                    }],
                }
            }

            vals = {
                'date_from': dt_from.strftime("%Y%m%d"),
                'date_to': dt_to.strftime("%Y%m%d"),
                'is_test': '1' if self.test_interchange or is_neutralized else '0',
                'type': "INFENT",
                'declarations': [declarations],
            }

            xml_content = self.env['ir.qweb']._render('l10n_fr_reports.aspone_xml_edi', vals)
            try:
                xml_content.encode('ISO-8859-15')
            except UnicodeEncodeError as e:
                raise ValidationError(
                    _("The xml file generated contains an invalid character: '%s'", xml_content[e.start:e.end]))

            xml_content = etree.tostring(cleanup_xml_node(xml_content), encoding='ISO-8859-15', standalone='yes')
            report_common_name = self._get_vat_report_name(dt_from, dt_to)
            reimbursement_name = _('%(report_common_name)s_reimbursement_%(index)s', report_common_name=report_common_name, index=index)
            self._send_xml_to_aspone(xml_content, reimbursement_name, dt_from, dt_to)
