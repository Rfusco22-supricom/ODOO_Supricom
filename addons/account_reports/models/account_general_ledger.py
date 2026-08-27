# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import csv
import io
import json

from odoo import models, fields, api, _
from odoo.tools.misc import format_date
from odoo.tools import float_repr, get_lang
from odoo.tools.misc import xlsxwriter
from odoo.exceptions import UserError

from datetime import timedelta
from collections import defaultdict


class GeneralLedgerCustomHandler(models.AbstractModel):
    _name = 'account.general.ledger.report.handler'
    _inherit = 'account.report.custom.handler'
    _description = 'General Ledger Custom Handler'

    def _get_custom_display_config(self):
        return {
            'templates': {
                'AccountReportLineName': 'account_reports.GeneralLedgerLineName',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        options['buttons'].append({
            'name': _("CSV"),
            'sequence': 50,
            'action': 'export_file',
            'action_param': 'generate_csv_export',
            'file_export_type': _('CSV'),
        })

        # Remove multi-currency columns if needed
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        if self.user_has_groups('base.group_multi_currency'):
            options['multi_currency'] = True
        else:
            options['columns'] = [
                column for column in options['columns']
                if column['expression_label'] != 'amount_currency'
            ]

        # Automatically unfold the report when printing it, unless some specific lines have been unfolded
        options['unfold_all'] = (options['export_mode'] == 'print' and not options.get('unfolded_lines')) or options['unfold_all']

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        lines = []
        date_from = fields.Date.from_string(options['date']['date_from'])
        company_currency = self.env.company.currency_id

        totals_by_column_group = defaultdict(lambda: {'debit': 0, 'credit': 0, 'balance': 0})
        for account, column_group_results in self._query_values(report, options):
            eval_dict = {}
            has_lines = False
            for column_group_key, results in column_group_results.items():
                account_sum = results.get('sum', {})
                account_un_earn = results.get('unaffected_earnings', {})

                account_debit = account_sum.get('debit', 0.0) + account_un_earn.get('debit', 0.0)
                account_credit = account_sum.get('credit', 0.0) + account_un_earn.get('credit', 0.0)
                account_balance = account_sum.get('balance', 0.0) + account_un_earn.get('balance', 0.0)

                eval_dict[column_group_key] = {
                    'amount_currency': account_sum.get('amount_currency', 0.0) + account_un_earn.get('amount_currency', 0.0),
                    'debit': account_debit,
                    'credit': account_credit,
                    'balance': account_balance,
                }

                max_date = account_sum.get('max_date')
                has_lines = has_lines or (max_date and max_date >= date_from)

                totals_by_column_group[column_group_key]['debit'] += account_debit
                totals_by_column_group[column_group_key]['credit'] += account_credit
                totals_by_column_group[column_group_key]['balance'] += account_balance

            lines.append(self._get_account_title_line(report, options, account, has_lines, eval_dict))

        # Report total line.
        for totals in totals_by_column_group.values():
            totals['balance'] = company_currency.round(totals['balance'])

        # Tax Declaration lines.
        journal_options = report._get_options_journals(options)
        if self._should_add_tax_declaration_lines(options, journal_options) and not self.env.context.get('skip_tax_declaration_lines'):
            lines += self._tax_declaration_lines(report, options, journal_options[0]['type'])

        # Total line
        lines.append(self._get_total_line(report, options, totals_by_column_group))

        return [(0, line) for line in lines]

    def _custom_unfold_all_batch_data_generator(self, report, options, lines_to_expand_by_function):
        account_ids_to_expand = []
        for line_dict in lines_to_expand_by_function.get('_report_expand_unfoldable_line_general_ledger', []):
            model, model_id = report._get_model_info_from_id(line_dict['id'])
            if model == 'account.account':
                account_ids_to_expand.append(model_id)

        limit_to_load = report.load_more_limit if report.load_more_limit and not options.get('export_mode') else None
        has_more_per_account_id = {}

        unlimited_aml_results_per_account_id = self._get_aml_values(report, options, account_ids_to_expand)[0]
        if limit_to_load:
            # Apply the load_more_limit.
            # load_more_limit cannot be passed to the call to _get_aml_values, otherwise it won't be applied per account but on the whole result.
            # We gain perf from batching, but load every result ; then we need to filter them.

            aml_results_per_account_id = {}
            for account_id, account_aml_results in unlimited_aml_results_per_account_id.items():
                account_values = {}
                for key, value in account_aml_results.items():
                    if len(account_values) == limit_to_load:
                        has_more_per_account_id[account_id] = True
                        break
                    account_values[key] = value
                aml_results_per_account_id[account_id] = account_values
        else:
            aml_results_per_account_id = unlimited_aml_results_per_account_id

        return {
            'initial_balances': self._get_initial_balance_values(report, account_ids_to_expand, options),
            'aml_results': aml_results_per_account_id,
            'has_more': has_more_per_account_id,
        }

    def _tax_declaration_lines(self, report, options, tax_type):
        labels_replacement = {
            'debit': _("Base Amount"),
            'credit': _("Tax Amount"),
        }

        rslt = [{
            'id': report._get_generic_line_id(None, None, markup='tax_decl_header_1'),
            'name': _('Tax Declaration'),
            'columns': [{} for column in options['columns']],
            'level': 1,
            'unfoldable': False,
            'unfolded': False,
        }, {
            'id': report._get_generic_line_id(None, None, markup='tax_decl_header_2'),
            'name': _('Name'),
            'columns': [{'name': labels_replacement.get(col['expression_label'], '')} for col in options['columns']],
            'level': 3,
            'unfoldable': False,
            'unfolded': False,
        }]

        # Call the generic tax report
        generic_tax_report = self.env.ref('account.generic_tax_report')
        tax_report_options = generic_tax_report.get_options({**options, 'selected_variant_id': generic_tax_report.id, 'forced_domain': [('tax_line_id.type_tax_use', '=', tax_type)]})
        tax_report_lines = generic_tax_report._get_lines(tax_report_options)
        tax_type_parent_line_id = generic_tax_report._get_generic_line_id(None, None, markup=tax_type)

        for tax_report_line in tax_report_lines:
            if tax_report_line.get('parent_id') == tax_type_parent_line_id:
                original_columns = tax_report_line['columns']
                row_column_map = {
                    'debit': original_columns[0],
                    'credit': original_columns[1],
                }

                tax_report_line['columns'] = [row_column_map.get(col['expression_label'], {}) for col in options['columns']]
                rslt.append(tax_report_line)

        return rslt

    def _query_values(self, report, options):
        """ Executes the queries, and performs all the computations.

        :return:    [(record, values_by_column_group), ...],  where
                    - record is an account.account record.
                    - values_by_column_group is a dict in the form {column_group_key: values, ...}
                        - column_group_key is a string identifying a column group, as in options['column_groups']
                        - values is a list of dictionaries, one per period containing:
                            - sum:                              {'debit': float, 'credit': float, 'balance': float}
                            - (optional) initial_balance:       {'debit': float, 'credit': float, 'balance': float}
                            - (optional) unaffected_earnings:   {'debit': float, 'credit': float, 'balance': float}
        """
        # Execute the queries and dispatch the results.
        query, params = self._get_query_sums(report, options)

        if not query:
            return []

        groupby_accounts = {}
        groupby_companies = {}

        self._cr.execute(query, params)
        for res in self._cr.dictfetchall():
            # No result to aggregate.
            if res['groupby'] is None:
                continue

            column_group_key = res['column_group_key']
            key = res['key']
            if key == 'sum':
                groupby_accounts.setdefault(res['groupby'], {col_group_key: {} for col_group_key in options['column_groups']})
                groupby_accounts[res['groupby']][column_group_key][key] = res

            elif key == 'initial_balance':
                groupby_accounts.setdefault(res['groupby'], {col_group_key: {} for col_group_key in options['column_groups']})
                groupby_accounts[res['groupby']][column_group_key][key] = res

            elif key == 'unaffected_earnings':
                groupby_companies.setdefault(res['groupby'], {col_group_key: {} for col_group_key in options['column_groups']})
                groupby_companies[res['groupby']][column_group_key] = res

        # Affect the unaffected earnings to the first fetched account of type 'account.data_unaffected_earnings'.
        # There is an unaffected earnings for each company but it's less costly to fetch all candidate accounts in
        # a single search and then iterate it.
        if groupby_companies:
            domain = [
                *([('id', 'in', options['account_ids'])] if options.get('account_ids') else []),
                *self.env['account.account']._check_company_domain(list(groupby_companies.keys())),
                ('account_type', '=', 'equity_unaffected'),
            ]
            equity_unaffected_account_ids_by_company = self.env['account.account'].browse(
                self.env['account.account']._name_search(options.get('filter_search_bar'), domain)
            ).grouped('company_id')

            for company_id, groupby_company in groupby_companies.items():
                if equity_unaffected_account := equity_unaffected_account_ids_by_company.get(self.env['res.company'].browse(company_id).root_id):
                    for column_group_key in options['column_groups']:
                        groupby_accounts.setdefault(equity_unaffected_account.id, {col_group_key: {'unaffected_earnings': {}} for col_group_key in options['column_groups']})

                        if unaffected_earnings := groupby_company.get(column_group_key):
                            if groupby_accounts[equity_unaffected_account.id][column_group_key].get('unaffected_earnings'):
                                for key in ['amount_currency', 'debit', 'credit', 'balance']:
                                    groupby_accounts[equity_unaffected_account.id][column_group_key]['unaffected_earnings'][key] += unaffected_earnings[key]
                            else:
                                groupby_accounts[equity_unaffected_account.id][column_group_key]['unaffected_earnings'] = unaffected_earnings

        # Retrieve the accounts to browse.
        # groupby_accounts.keys() contains all account ids affected by:
        # - the amls in the current period.
        # - the amls affecting the initial balance.
        # - the unaffected earnings allocation.
        # Note a search is done instead of a browse to preserve the table ordering.
        if groupby_accounts:
            accounts = self.env['account.account'].search([('id', 'in', list(groupby_accounts.keys()))])
        else:
            accounts = []

        return [(account, groupby_accounts[account.id]) for account in accounts]

    def _get_query_sums(self, report, options):
        """ Construct a query retrieving all the aggregated sums to build the report. It includes:
        - sums for all accounts.
        - sums for the initial balances.
        - sums for the unaffected earnings.
        - sums for the tax declaration.
        :return:                    (query, params)
        """
        options_by_column_group = report._split_options_per_column_group(options)

        params = []
        queries = []

        # Create the currency table.
        # As the currency table is the same whatever the comparisons, create it only once.
        ct_query = report._get_query_currency_table(options)

        # ============================================
        # 1) Get sums for all accounts.
        # ============================================
        for column_group_key, options_group in options_by_column_group.items():
            if not options.get('general_ledger_strict_range'):
                options_group = self._get_options_sum_balance(options_group)

            # Sum is computed including the initial balance of the accounts configured to do so, unless a special option key is used
            # (this is required for trial balance, which is based on general ledger)
            sum_date_scope = 'strict_range' if options_group.get('general_ledger_strict_range') else 'normal'

            query_domain = []

            if options.get('export_mode') == 'print':
                if search := options.get('filter_search_bar'):
                    if options.get('hierarchy'):
                        query_domain.extend(['|', ('account_id.group_id', 'ilike', search)])
                    query_domain.extend(['|', ('account_id', 'ilike', search), ('account_id.code', 'like', search)])
                if options.get('account_ids'):
                    query_domain.append(('account_id', 'in', options['account_ids']))

            if options_group.get('include_current_year_in_unaff_earnings'):
                query_domain += [('account_id.include_initial_balance', '=', True)]

            tables, where_clause, where_params = report._query_get(options_group, sum_date_scope, domain=query_domain)
            params.append(column_group_key)
            params += where_params
            queries.append(f"""
                SELECT
                    account_move_line.account_id                            AS groupby,
                    'sum'                                                   AS key,
                    MAX(account_move_line.date)                             AS max_date,
                    %s                                                      AS column_group_key,
                    COALESCE(SUM(account_move_line.amount_currency), 0.0)   AS amount_currency,
                    SUM(ROUND(account_move_line.debit * currency_table.rate, currency_table.precision))   AS debit,
                    SUM(ROUND(account_move_line.credit * currency_table.rate, currency_table.precision))  AS credit,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                FROM {tables}
                LEFT JOIN {ct_query} ON currency_table.company_id = account_move_line.company_id
                WHERE {where_clause}
                GROUP BY account_move_line.account_id
            """)

            # ============================================
            # 2) Get sums for the unaffected earnings.
            # ============================================
            if not options_group.get('general_ledger_strict_range') and not options_group.get('skip_unaffected_earnings'):
                unaff_earnings_domain = [('account_id.include_initial_balance', '=', False)]

                # The period domain is expressed as:
                # [
                #   ('date' <= fiscalyear['date_from'] - 1),
                #   ('account_id.include_initial_balance', '=', False),
                # ]

                new_options = self._get_options_unaffected_earnings(options_group)
                tables, where_clause, where_params = report._query_get(new_options, 'strict_range', domain=unaff_earnings_domain)
                params.append(column_group_key)
                params += where_params
                queries.append(f"""
                    SELECT
                        account_move_line.company_id                            AS groupby,
                        'unaffected_earnings'                                   AS key,
                        NULL                                                    AS max_date,
                        %s                                                      AS column_group_key,
                        COALESCE(SUM(account_move_line.amount_currency), 0.0)   AS amount_currency,
                        SUM(ROUND(account_move_line.debit * currency_table.rate, currency_table.precision))   AS debit,
                        SUM(ROUND(account_move_line.credit * currency_table.rate, currency_table.precision))  AS credit,
                        SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                    FROM {tables}
                    LEFT JOIN {ct_query} ON currency_table.company_id = account_move_line.company_id
                    WHERE {where_clause}
                    GROUP BY account_move_line.company_id
                """)

        return ' UNION ALL '.join(queries), params

    def _get_options_unaffected_earnings(self, options):
        ''' Create options used to compute the unaffected earnings.
        The unaffected earnings are the amount of benefits/loss that have not been allocated to
        another account in the previous fiscal years.
        The resulting dates domain will be:
        [
          ('date' <= fiscalyear['date_from'] - 1),
          ('account_id.include_initial_balance', '=', False),
        ]
        :param options: The report options.
        :return:        A copy of the options.
        '''
        new_options = options.copy()
        new_options.pop('filter_search_bar', None)
        fiscalyear_dates = self.env.company.compute_fiscalyear_dates(fields.Date.from_string(options['date']['date_from']))

        # Trial balance uses the options key, general ledger does not
        new_date_to = fields.Date.from_string(new_options['date']['date_to']) if options.get('include_current_year_in_unaff_earnings') else fiscalyear_dates['date_from'] - timedelta(days=1)

        new_options['date'] = {
            'mode': 'single',
            'date_to': fields.Date.to_string(new_date_to),
        }

        return new_options

    def _get_aml_values(self, report, options, expanded_account_ids, offset=0, limit=None):
        rslt = {account_id: {} for account_id in expanded_account_ids}
        aml_query, aml_params = self._get_query_amls(report, options, expanded_account_ids, offset=offset, limit=limit)
        self._cr.execute(aml_query, aml_params)
        aml_results_number = 0
        has_more = False
        for aml_result in self._cr.dictfetchall():
            aml_results_number += 1
            if aml_results_number == limit:
                has_more = True
                break

            if aml_result['ref']:
                aml_result['communication'] = f"{aml_result['ref']} - {aml_result['name']}"
            else:
                aml_result['communication'] = aml_result['name']

            # The same aml can return multiple results when using account_report_cash_basis module, if the receivable/payable
            # is reconciled with multiple payments. In this case, the date shown for the move lines actually corresponds to the
            # reconciliation date. In order to keep distinct lines in this case, we include date in the grouping key.
            aml_key = (aml_result['id'], aml_result['date'])

            account_result = rslt[aml_result['account_id']]
            if not aml_key in account_result:
                account_result[aml_key] = {col_group_key: {} for col_group_key in options['column_groups']}

            account_result[aml_key][aml_result['column_group_key']] = aml_result

        return rslt, has_more

    def _get_query_amls(self, report, options, expanded_account_ids, offset=0, limit=None):
        """ Construct a query retrieving the account.move.lines when expanding a report line with or without the load
        more.
        :param options:               The report options.
        :param expanded_account_ids:  The account.account ids corresponding to consider. If None, match every account.
        :param offset:                The offset of the query (used by the load more).
        :param limit:                 The limit of the query (used by the load more).
        :return:                      (query, params)
        """
        additional_domain = [('account_id', 'in', expanded_account_ids)] if expanded_account_ids is not None else None
        queries = []
        all_params = []
        lang = self.env.user.lang or get_lang(self.env).code
        journal_name = f"COALESCE(journal.name->>'{lang}', journal.name->>'en_US')" if \
            self.pool['account.journal'].name.translate else 'journal.name'
        account_name = f"COALESCE(account.name->>'{lang}', account.name->>'en_US')" if \
            self.pool['account.account'].name.translate else 'account.name'
        for column_group_key, group_options in report._split_options_per_column_group(options).items():
            # Get sums for the account move lines.
            # period: [('date' <= options['date_to']), ('date', '>=', options['date_from'])]
            tables, where_clause, where_params = report._query_get(group_options, domain=additional_domain, date_scope='strict_range')
            ct_query = report._get_query_currency_table(group_options)

            if self._context.get('general_ledger_csv_export'):
                order_by_clause = "account.code, company.sequence, company.name, account_move_line.date, move_name, account_move_line.id"
            else:
                order_by_clause = "account.code, account_move_line.date, company.sequence, company.name, move_name, account_move_line.id"

            query = f'''
                (SELECT
                    account_move_line.id,
                    account_move_line.date,
                    MIN(account_move_line.date_maturity)    AS date_maturity,
                    MIN(account_move_line.name)             AS name,
                    MIN(account_move_line.ref)              AS ref,
                    MIN(account_move_line.company_id)       AS company_id,
                    MIN(account_move_line.account_id)       AS account_id,
                    MIN(account_move_line.payment_id)       AS payment_id,
                    MIN(account_move_line.partner_id)       AS partner_id,
                    MIN(account_move_line.currency_id)      AS currency_id,
                    SUM(account_move_line.amount_currency)  AS amount_currency,
                    MIN(COALESCE(account_move_line.invoice_date, account_move_line.date))                 AS invoice_date,
                    account_move_line.date                                                                AS date,
                    SUM(ROUND(account_move_line.debit * currency_table.rate, currency_table.precision))   AS debit,
                    SUM(ROUND(account_move_line.credit * currency_table.rate, currency_table.precision))  AS credit,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance,
                    MIN(move.name)                          AS move_name,
                    MIN(company.currency_id)                AS company_currency_id,
                    MIN(partner.name)                       AS partner_name,
                    MIN(move.move_type)                     AS move_type,
                    MIN(account.code)                       AS account_code,
                    MIN({account_name})                     AS account_name,
                    MIN(journal.code)                       AS journal_code,
                    MIN({journal_name})                     AS journal_name,
                    MIN(full_rec.id)                        AS full_rec_name,
                    %s                                      AS column_group_key
                FROM {tables}
                JOIN account_move move                      ON move.id = account_move_line.move_id
                LEFT JOIN {ct_query}                        ON currency_table.company_id = account_move_line.company_id
                LEFT JOIN res_company company               ON company.id = account_move_line.company_id
                LEFT JOIN res_partner partner               ON partner.id = account_move_line.partner_id
                LEFT JOIN account_account account           ON account.id = account_move_line.account_id
                LEFT JOIN account_journal journal           ON journal.id = account_move_line.journal_id
                LEFT JOIN account_full_reconcile full_rec   ON full_rec.id = account_move_line.full_reconcile_id
                WHERE {where_clause}
                GROUP BY account.code, company.sequence, company.name, account_move_line.id, account_move_line.date
                ORDER BY {order_by_clause})
            '''

            queries.append(query)
            all_params.append(column_group_key)
            all_params += where_params

        full_query = " UNION ALL ".join(queries)

        if offset:
            full_query += ' OFFSET %s '
            all_params.append(offset)
        if limit:
            full_query += ' LIMIT %s '
            all_params.append(limit)

        return (full_query, all_params)

    def _get_initial_balance_values(self, report, account_ids, options):
        """
        Get sums for the initial balance.
        """
        queries = []
        params = []
        for column_group_key, options_group in report._split_options_per_column_group(options).items():
            new_options = self._get_options_initial_balance(options_group)
            ct_query = report._get_query_currency_table(options_group)
            domain = [('account_id', 'in', account_ids)]
            if new_options.get('include_current_year_in_unaff_earnings'):
                domain += [('account_id.include_initial_balance', '=', True)]
            tables, where_clause, where_params = report._query_get(new_options, 'normal', domain=domain)
            params.append(column_group_key)
            params += where_params
            queries.append(f"""
                SELECT
                    account_move_line.account_id                                                          AS groupby,
                    'initial_balance'                                                                     AS key,
                    NULL                                                                                  AS max_date,
                    %s                                                                                    AS column_group_key,
                    COALESCE(SUM(account_move_line.amount_currency), 0.0)                                 AS amount_currency,
                    SUM(ROUND(account_move_line.debit * currency_table.rate, currency_table.precision))   AS debit,
                    SUM(ROUND(account_move_line.credit * currency_table.rate, currency_table.precision))  AS credit,
                    SUM(ROUND(account_move_line.balance * currency_table.rate, currency_table.precision)) AS balance
                FROM {tables}
                LEFT JOIN {ct_query} ON currency_table.company_id = account_move_line.company_id
                WHERE {where_clause}
                GROUP BY account_move_line.account_id
            """)

        self._cr.execute(" UNION ALL ".join(queries), params)

        init_balance_by_col_group = {
            account_id: {column_group_key: {} for column_group_key in options['column_groups']}
            for account_id in account_ids
        }
        for result in self._cr.dictfetchall():
            init_balance_by_col_group[result['groupby']][result['column_group_key']] = result

        accounts = self.env['account.account'].browse(account_ids)
        return {
            account.id: (account, init_balance_by_col_group[account.id])
            for account in accounts
        }

    def _get_options_initial_balance(self, options):
        """ Create options used to compute the initial balances.
        The initial balances depict the current balance of the accounts at the beginning of
        the selected period in the report.
        The resulting dates domain will be:
        [
            ('date' <= options['date_from'] - 1),
            '|',
            ('date' >= fiscalyear['date_from']),
            ('account_id.include_initial_balance', '=', True)
        ]
        :param options: The report options.
        :return:        A copy of the options.
        """
        #pylint: disable=sql-injection
        new_options = options.copy()
        date_to = new_options['comparison']['periods'][-1]['date_from'] if new_options.get('comparison', {}).get('periods') else new_options['date']['date_from']
        new_date_to = fields.Date.from_string(date_to) - timedelta(days=1)

        # Date from computation
        # We have two case:
        # 1) We are choosing a date that starts at the beginning of a fiscal year and we want the initial period to be
        # the previous fiscal year
        # 2) We are choosing a date that starts in the middle of a fiscal year and in that case we want the initial period
        # to be the beginning of the fiscal year
        date_from = fields.Date.from_string(new_options['date']['date_from'])
        current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)

        if date_from == current_fiscalyear_dates['date_from']:
            # We want the previous fiscal year
            previous_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from - timedelta(days=1))
            new_date_from = previous_fiscalyear_dates['date_from']
            include_current_year_in_unaff_earnings = True
        else:
            # We want the current fiscal year
            new_date_from = current_fiscalyear_dates['date_from']
            include_current_year_in_unaff_earnings = False

        new_options['date'] = {
            'mode': 'range',
            'date_from': fields.Date.to_string(new_date_from),
            'date_to': fields.Date.to_string(new_date_to),
        }
        new_options['include_current_year_in_unaff_earnings'] = include_current_year_in_unaff_earnings

        return new_options

    def _get_options_sum_balance(self, options):
        new_options = options.copy()

        if not options.get('general_ledger_strict_range'):
            # Date from
            date_from = fields.Date.from_string(new_options['date']['date_from'])
            current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(date_from)
            new_date_from = current_fiscalyear_dates['date_from']

            new_date_to = new_options['date']['date_to']

            new_options['date'] = {
                'mode': 'range',
                'date_from': fields.Date.to_string(new_date_from),
                'date_to': new_date_to,
            }

        return new_options

    ####################################################
    # COLUMN/LINE HELPERS
    ####################################################
    def _get_account_title_line(self, report, options, account, has_lines, eval_dict):
        line_columns = []
        for column in options['columns']:
            col_value = eval_dict.get(column['column_group_key'], {}).get(column['expression_label'])
            col_expr_label = column['expression_label']

            value = None if col_value is None or (col_expr_label == 'amount_currency' and not account.currency_id) else col_value

            line_columns.append(report._build_column_dict(
                value,
                column,
                options=options,
                currency=account.currency_id if col_expr_label == 'amount_currency' else None,
            ))

        line_id = report._get_generic_line_id('account.account', account.id)
        is_in_unfolded_lines = any(
            report._get_res_id_from_line_id(line_id, 'account.account') == account.id
            for line_id in options.get('unfolded_lines')
        )
        return {
            'id': line_id,
            'name': f'{account.code} {account.name}',
            'columns': line_columns,
            'level': 1,
            'unfoldable': has_lines,
            'unfolded': has_lines and (is_in_unfolded_lines or options.get('unfold_all')),
            'expand_function': '_report_expand_unfoldable_line_general_ledger',
        }

    def _get_aml_line(self, report, parent_line_id, options, eval_dict, init_bal_by_col_group):
        line_columns = []
        for column in options['columns']:
            col_expr_label = column['expression_label']
            col_value = eval_dict[column['column_group_key']].get(col_expr_label)
            col_currency = None

            if col_value is not None:
                if col_expr_label == 'amount_currency':
                    col_currency = self.env['res.currency'].browse(eval_dict[column['column_group_key']]['currency_id'])
                    col_value = None if col_currency == self.env.company.currency_id else col_value
                elif col_expr_label == 'balance':
                    col_value += (init_bal_by_col_group[column['column_group_key']] or 0)

            line_columns.append(report._build_column_dict(
                col_value,
                column,
                options=options,
                currency=col_currency,
            ))

        aml_id = None
        move_name = None
        caret_type = None
        for column_group_dict in eval_dict.values():
            aml_id = column_group_dict.get('id', '')
            if aml_id:
                if column_group_dict.get('payment_id'):
                    caret_type = 'account.payment'
                else:
                    caret_type = 'account.move.line'
                move_name = column_group_dict['move_name']
                date = str(column_group_dict.get('date', ''))
                break

        return {
            'id': report._get_generic_line_id('account.move.line', aml_id, parent_line_id=parent_line_id, markup=date),
            'caret_options': caret_type,
            'parent_id': parent_line_id,
            'name': move_name,
            'columns': line_columns,
            'level': 3,
        }

    @api.model
    def _get_total_line(self, report, options, eval_dict):
        line_columns = []
        for column in options['columns']:
            col_value = eval_dict[column['column_group_key']].get(column['expression_label'])
            col_value = None if col_value is None else col_value

            line_columns.append(report._build_column_dict(col_value, column, options=options))

        return {
            'id': report._get_generic_line_id(None, None, markup='total'),
            'name': _('Total'),
            'level': 1,
            'columns': line_columns,
        }

    def caret_option_audit_tax(self, options, params):
        return self.env['account.generic.tax.report.handler'].caret_option_audit_tax(options, params)

    def _report_expand_unfoldable_line_general_ledger(self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None):
        def init_load_more_progress(line_dict):
            return {
                column['column_group_key']: line_col.get('no_format', 0)
                for column, line_col in  zip(options['columns'], line_dict['columns'])
                if column['expression_label'] == 'balance'
            }

        report = self.env.ref('account_reports.general_ledger_report')
        model, model_id = report._get_model_info_from_id(line_dict_id)

        if model != 'account.account':
            raise UserError(_("Wrong ID for general ledger line to expand: %s", line_dict_id))

        lines = []

        # Get initial balance
        if offset == 0:
            if unfold_all_batch_data:
                account, init_balance_by_col_group = unfold_all_batch_data['initial_balances'][model_id]
            else:
                account, init_balance_by_col_group = self._get_initial_balance_values(report, [model_id], options)[model_id]

            initial_balance_line = report._get_partner_and_general_ledger_initial_balance_line(options, line_dict_id, init_balance_by_col_group, account.currency_id)

            if initial_balance_line:
                lines.append(initial_balance_line)

                # For the first expansion of the line, the initial balance line gives the progress
                progress = init_load_more_progress(initial_balance_line)

        # Get move lines
        limit_to_load = report.load_more_limit + 1 if report.load_more_limit and options['export_mode'] != 'print' else None
        if unfold_all_batch_data:
            aml_results = unfold_all_batch_data['aml_results'][model_id]
            has_more = unfold_all_batch_data['has_more'].get(model_id, False)
        else:
            aml_results, has_more = self._get_aml_values(report, options, [model_id], offset=offset, limit=limit_to_load)
            aml_results = aml_results[model_id]

        next_progress = progress
        for aml_result in aml_results.values():
            new_line = self._get_aml_line(report, line_dict_id, options, aml_result, next_progress)
            lines.append(new_line)
            next_progress = init_load_more_progress(new_line)

        return {
            'lines': lines,
            'offset_increment': report.load_more_limit,
            'has_more': has_more,
            'progress': next_progress,
        }

    def _should_add_tax_declaration_lines(self, report_options, journal_options):
        return len(report_options['column_groups']) == 1 and len(journal_options) == 1 and journal_options[0]['type'] in ('sale', 'purchase')

    def export_to_xlsx(self, options, response=None):
        def add_worksheet_unique_name(workbook, sheet_name):
            existing_names = set(workbook.sheetnames.keys())
            count = 1
            max_length = 31
            new_sheet_name = sheet_name[:max_length]

            while new_sheet_name in existing_names:
                suffix = f" ({count})"
                truncated_name = sheet_name[:max_length - len(suffix)]
                new_sheet_name = f"{truncated_name}{suffix}"
                count += 1
            return workbook.add_worksheet(new_sheet_name)

        report = self.env['account.report'].browse(options['report_id'])
        # if there's hierarchy activated, batching doesn't work, so fallback to standard export
        if options.get('hierarchy'):
            return report.export_to_xlsx(options, response)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True,
            'strings_to_formulas': False,
        })
        report_options = report.get_options(previous_options={**options, 'export_mode': 'print'})
        sheet = add_worksheet_unique_name(workbook, report.name)
        total_lines = []
        y_offset = None
        for account in self._get_accounts_with_move_lines(options):
            skip_unaffected_earnings = account.account_type != 'equity_unaffected'
            batched_report_options = report_options | {'account_ids': account.ids, 'skip_unaffected_earnings': skip_unaffected_earnings}
            lines = report._filter_out_folded_children(
                report.with_context(no_format=True, skip_tax_declaration_lines=True)
                ._get_lines(batched_report_options)
            )
            if len(lines) <= 1:
                continue
            if y_offset is None:
                y_offset = report._inject_columns_and_headers_in_sheet(workbook, sheet, options, lines)
            if y_offset + len(lines[:-1]) >= sheet.xls_rowmax:
                sheet = add_worksheet_unique_name(workbook, report.name)
                y_offset = report._inject_columns_and_headers_in_sheet(workbook, sheet, options, lines)
            report._inject_lines_into_xlsx_sheet(workbook, sheet, lines[:-1], options, y_offset)
            y_offset += len(lines[:-1])
            total_lines.append(lines[-1])

        if total_lines:
            # Tax Declaration lines
            journal_options = report._get_options_journals(report_options)
            if self._should_add_tax_declaration_lines(report_options, journal_options):
                tax_declaration_lines = self.with_context(no_format=True)._tax_declaration_lines(report, report_options, journal_options[0]['type'])
                report._inject_lines_into_xlsx_sheet(workbook, sheet, tax_declaration_lines, options, y_offset, x_offset=1)
                y_offset += len(tax_declaration_lines)

            final_total_line = total_lines[0]
            for col_index, col in enumerate(final_total_line['columns']):
                if col['expression_label'] not in ('debit', 'credit', 'balance'):
                    continue
                for total_line in total_lines[1:]:
                    col['no_format'] += total_line['columns'][col_index]['no_format']
                    col['name'] = (col['name'] or 0.0) + (total_line['columns'][col_index]['name'] or 0.0)
            report._inject_lines_into_xlsx_sheet(workbook, sheet, [final_total_line], options, y_offset, x_offset=1)

        report._add_options_xlsx_sheet(workbook, [report_options])

        workbook.close()
        output.seek(0)
        generated_file = output.read()
        output.close()

        return {
            'file_name': report.get_default_report_filename(options, 'xlsx'),
            'file_content': generated_file,
            'file_type': 'xlsx',
        }

    def _get_accounts_with_move_lines(self, options):
        report = self.env['account.report'].browse(options['report_id'])

        date_from = options['date']['date_from']
        if not options.get('general_ledger_strict_range'):
            parsed_date_from = fields.Date.from_string(date_from)
            current_fiscalyear_dates = self.env.company.compute_fiscalyear_dates(parsed_date_from)
            date_from = current_fiscalyear_dates['date_from']

        domain = self.env['account.account']._check_company_domain(report.get_report_company_ids(options))
        query_obj = self.env['account.account']._search(domain)
        query_str, query_params = query_obj.select()

        tables, where_clause, where_params = report._query_get(options, 'from_beginning')

        query = f"""
            {query_str}
            AND (
                account_account.account_type = 'equity_unaffected'
                OR EXISTS (
                    SELECT 1
                    FROM {tables}
                    WHERE {where_clause}
                    AND account_move_line.account_id = account_account.id
                    AND (
                        COALESCE(account_account.include_initial_balance, FALSE)
                        OR account_move_line.date >= %s
                    )
                )
            )
        """

        self.env.cr.execute(query, [*query_params, *where_params, date_from])
        account_ids = tuple(res[0] for res in self.env.cr.fetchall())
        return self.env['account.account'].search([('id', 'in', account_ids)])

    def generate_csv_export(self, options):
        if len(options['column_groups']) > 1:
            raise UserError(_("CSV export only works with one column group"))

        report = self.env['account.report'].browse(options['report_id'])
        return {
            'file_content': self._generate_csv_lazy_export(options),
            'file_type': 'csv',
            'file_name': report.get_default_report_filename(options, 'csv')
        }

    def _generate_csv_lazy_export(self, options):
        with self.pool.cursor() as new_cr:
            self.env.flush_all()
            handler = self.with_env(self.env(cr=new_cr))
            decimal_places_per_cur_id = {
                currency.id: currency.decimal_places
                for currency in handler.env['res.currency'].with_context(active_test=False).search([])
            }
            company_currency_id = handler.env.company.currency_id.id

            def csv_format_account_line(account_line):
                cells = list(handler.env['account.account']._split_code_name(account_line['name']))

                for col in account_line['columns']:
                    cell = col['name']
                    if col['figure_type'] == 'monetary' and isinstance(cell, float):
                        currency_id = col['currency'] if col['currency'] else company_currency_id
                        cell = float_repr(cell, decimal_places_per_cur_id[currency_id])
                    cells.append(cell)

                return csv_format(cells)

            def csv_format_aml_res(aml_res):
                cells = [aml_res.get('move_name', '')]
                for col in options['columns']:
                    cell = aml_res.get(col['expression_label'], '')

                    if col['figure_type'] == 'monetary' and isinstance(cell, float):
                        if col['expression_label'] == 'amount_currency' and aml_res.get('currency_id'):
                            currency_id = aml_res['currency_id']
                            cell = float_repr(cell, decimal_places_per_cur_id[currency_id]) if currency_id != company_currency_id else ''
                        else:
                            cell = float_repr(cell, decimal_places_per_cur_id[company_currency_id])

                    cells.append(cell)
                return csv_format(cells, indent=1)

            def csv_format(cells, indent=0):
                with io.StringIO() as buf:
                    writer = csv.writer(buf, delimiter=',', lineterminator='\n')
                    writer.writerow([''] * indent + cells)
                    return buf.getvalue().encode()

            yield csv_format([_("Code"), _("Name")] + [col['name'] for col in options['columns']])
            report = handler.env['account.report'].browse(options['report_id'])
            agg_lines_options = options | {'export_mode': 'print', 'unfolded_lines': [], 'unfold_all': False}
            agg_lines = report.with_context(no_format=True)._get_lines(agg_lines_options)

            accounts = []
            account_lines = []
            for agg_line in agg_lines:
                line_id = agg_line['id']
                model, account_id = report._get_model_info_from_id(line_id)
                if model == 'account.account':
                    accounts.append(account_id)
                    account_lines.append(agg_line)

            initial_balances = handler._get_initial_balance_values(report, accounts, options)
            accounts_currencies = {
                account.id: account.currency_id.id or company_currency_id
                for account in handler.env['account.account'].browse(accounts)
            }

            aml_query, aml_params = handler.with_context(general_ledger_csv_export=True)._get_query_amls(report, options, accounts)
            handler.env.cr.execute(aml_query, aml_params)
            account_id = None
            progress = 0
            initial_balance_vals = {}
            account_lines_iter = iter(account_lines)
            while aml_result := handler.env.cr.dictfetchone():
                while account_id is None or account_id != aml_result['account_id']:
                    account_line = next(account_lines_iter)
                    yield csv_format_account_line(account_line)
                    _model, account_id = report._get_model_info_from_id(account_line['id'])
                    if initial_balance_vals := next(iter(initial_balances.get(account_id)[1].values())):
                        initial_balance_vals['currency_id'] = accounts_currencies[account_id]
                        progress = initial_balance_vals['balance']
                    else:
                        progress = 0

                if initial_balance_vals:
                    yield csv_format_aml_res(initial_balance_vals | {'move_name': _("Initial Balance")})
                    initial_balance_vals = {}
                if aml_result['ref']:
                    aml_result['communication'] = f"{aml_result['ref']} - {aml_result['name']}"
                else:
                    aml_result['communication'] = aml_result['name']
                progress = aml_result['balance'] = (progress + aml_result['balance'])
                yield csv_format_aml_res(aml_result)

            for account_line in account_lines_iter:
                yield csv_format_account_line(account_line)

            total_line = agg_lines[-1]
            yield csv_format_account_line(total_line)
