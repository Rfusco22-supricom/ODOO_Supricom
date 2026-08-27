import json
from datetime import datetime, timedelta

from babel.dates import format_datetime, format_date
from odoo import models, api, _, fields
from odoo.osv import expression
from odoo.release import version
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo.tools.misc import formatLang, format_date as odoo_format_date, get_lang
import random

import ast


class account_journal(models.Model):
    _inherit = "account.journal"


    def get_journal_dashboard_datas(self):
        currency = self.currency_id or self.company_id.currency_id
        number_to_reconcile = number_to_check = last_balance = 0
        has_at_least_one_statement = False
        bank_account_balance = nb_lines_bank_account_balance = 0
        outstanding_pay_account_balance = nb_lines_outstanding_pay_account_balance = 0
        title = ''
        number_draft = number_waiting = number_late = to_check_balance = 0
        sum_draft = sum_waiting = sum_late = 0.0
        currency_id_dif = self.company_id.currency_id_dif

        if self.type in ('bank', 'cash'):
            last_statement = self._get_last_bank_statement(
                domain=[('move_id.state', 'in', ['posted', 'confirm'])])
            last_balance = last_statement.balance_end
            has_at_least_one_statement = bool(last_statement)
            bank_account_balance, nb_lines_bank_account_balance = self._get_journal_bank_account_balance(
                domain=[('parent_state', '=', 'posted')])
            outstanding_pay_account_balance, nb_lines_outstanding_pay_account_balance = self._get_journal_outstanding_payments_account_balance(
                domain=[('parent_state', '=', 'posted')])

            self._cr.execute('''
                SELECT COUNT(st_line.id)
                FROM account_bank_statement_line st_line
                JOIN account_move st_line_move ON st_line_move.id = st_line.move_id
                WHERE st_line_move.journal_id IN %s
                AND NOT st_line.is_reconciled
                AND st_line_move.to_check IS NOT TRUE
                AND st_line_move.state = 'posted'
            ''', [tuple(self.ids)])
            number_to_reconcile = self.env.cr.fetchone()[0]

            to_check_ids = self.to_check_ids()
            number_to_check = len(to_check_ids)
            to_check_balance = sum([r.amount for r in to_check_ids])
        # TODO need to check if all invoices are in the same currency than the journal!!!!
        elif self.type in ['sale', 'purchase']:
            title = _('Bills to pay') if self.type == 'purchase' else _('Invoices owed to you')
            self.env['account.move'].flush_model()

            (query, query_args) = self._get_open_bills_to_pay_query()
            self.env.cr.execute(query, query_args)
            query_results_to_pay = self.env.cr.dictfetchall()

            (query, query_args) = self._get_draft_bills_query()
            self.env.cr.execute(query, query_args)
            query_results_drafts = self.env.cr.dictfetchall()

            today = fields.Date.context_today(self)
            query = '''
                SELECT
                    (CASE WHEN move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * amount_residual_usd AS amount_total,
                    currency_id_dif AS currency,
                    move_type,
                    invoice_date,
                    company_id
                FROM account_move move
                WHERE journal_id = %s
                AND date <= %s
                AND state = 'posted'
                AND payment_state in ('not_paid', 'partial')
                AND move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt');
            '''

            self.env.cr.execute(query, (self.id, today))
            late_query_results = self.env.cr.dictfetchall()
            curr_cache = {}
            (number_waiting, sum_waiting) = self._count_results_and_sum_amounts(query_results_to_pay, currency_id_dif, curr_cache=curr_cache)
            (number_draft, sum_draft) = self._count_results_and_sum_amounts(query_results_drafts, currency_id_dif, curr_cache=curr_cache)
            (number_late, sum_late) = self._count_results_and_sum_amounts(late_query_results, currency_id_dif, curr_cache=curr_cache)
            read = self.env['account.move'].read_group([('journal_id', '=', self.id), ('to_check', '=', True)], ['amount_total'], 'journal_id', lazy=False)
            if read:
                number_to_check = read[0]['__count']
                to_check_balance = read[0]['amount_total']
        elif self.type == 'general':
            read = self.env['account.move'].read_group([('journal_id', '=', self.id), ('to_check', '=', True)], ['amount_total'], 'journal_id', lazy=False)
            if read:
                number_to_check = read[0]['__count']
                to_check_balance = read[0]['amount_total']

        is_sample_data = self.kanban_dashboard_graph and any \
            (data.get('is_sample_data', False) for data in json.loads(self.kanban_dashboard_graph))

        return {
            'number_to_check': number_to_check,
            'to_check_balance': formatLang(self.env, to_check_balance, currency_obj=currency),
            'number_to_reconcile': number_to_reconcile,
            'account_balance': formatLang(self.env, currency.round(bank_account_balance), currency_obj=currency),
            'has_at_least_one_statement': has_at_least_one_statement,
            'nb_lines_bank_account_balance': nb_lines_bank_account_balance,
            'outstanding_pay_account_balance': formatLang(self.env, currency.round(outstanding_pay_account_balance), currency_obj=currency),
            'nb_lines_outstanding_pay_account_balance': nb_lines_outstanding_pay_account_balance,
            'last_balance': formatLang(self.env, currency.round(last_balance) + 0.0, currency_obj=currency),
            'number_draft': number_draft,
            'number_waiting': number_waiting,
            'number_late': number_late,
            'sum_draft': formatLang(self.env, currency_id_dif.round(sum_draft * currency_id_dif.inverse_rate) + 0.0, currency_obj=self.company_id.currency_id),
            'sum_draft_usd': formatLang(self.env, currency_id_dif.round(sum_draft) + 0.0, currency_obj=currency_id_dif),
            'sum_waiting': formatLang(self.env, currency_id_dif.round(sum_waiting * currency_id_dif.inverse_rate) + 0.0, currency_obj=self.company_id.currency_id),
            'sum_waiting_usd': formatLang(self.env, currency_id_dif.round(sum_waiting) + 0.0, currency_obj=currency_id_dif),
            'sum_late': formatLang(self.env, currency_id_dif.round(sum_late * currency_id_dif.inverse_rate) + 0.0, currency_obj=self.company_id.currency_id),
            'sum_late_usd': formatLang(self.env, currency_id_dif.round(sum_late) + 0.0, currency_obj=currency_id_dif),
            'currency_id': currency.id,
            'bank_statements_source': self.bank_statements_source,
            'title': title,
            'is_sample_data': is_sample_data,
            'company_count': len(self.env.companies)
        }

    # def _get_open_bills_to_pay_query(self):
    #     for item in self :
    #         """
    #         Returns a tuple containing the SQL query used to gather the open bills
    #         data as its first element, and the arguments dictionary to use to run
    #         it as its second.
    #         """
    #         return ('''
    #             SELECT
    #                 (CASE WHEN move.move_type IN ('out_refund', 'in_refund') THEN -1 ELSE 1 END) * move.amount_residual_usd AS amount_total,
    #                 move.currency_id_dif AS currency,
    #                 move.move_type,
    #                 move.invoice_date,
    #                 move.company_id
    #             FROM account_move move
    #             WHERE move.journal_id = %(journal_id)s
    #             AND move.state = 'posted'
    #             AND move.payment_state in ('not_paid', 'partial')
    #             AND move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt');
    #         ''', {'journal_id': item.id})

    def _get_bar_graph_select_query(self):
        """
        Returns a tuple containing the base SELECT SQL query used to gather
        the bar graph's data as its first element, and the arguments dictionary
        for it as its second.
        """
        currency_id_dif = self.env.company.currency_id_dif
        sign = '' if self.type == 'sale' else '-'
        return ('''
            SELECT
                ''' + sign + ''' + SUM(move.amount_residual_usd * %(inverse_rate)s) AS total,
                MIN(invoice_date_due) AS aggr_date
            FROM account_move move
            WHERE move.journal_id = %(journal_id)s
            AND move.state = 'posted'
            AND move.payment_state in ('not_paid', 'partial')
            AND move.move_type IN %(invoice_types)s
        ''', {
            'invoice_types': tuple(self.env['account.move'].get_invoice_types(True)),
            'journal_id': self.id,
            'inverse_rate': currency_id_dif.inverse_rate
        })