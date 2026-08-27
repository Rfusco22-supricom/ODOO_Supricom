# -*- coding: utf-8 -*-
import uuid
import json
import logging
import traceback
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api
from ..tools import date_delta_seconds
_logger = logging.getLogger(__name__)


class ChatWorkQueue(models.Model):
    _name = 'acrux.chat.work.queue'
    _description = 'Work Queue'
    _rec_name = 'ttype'
    _order = 'id'

    name = fields.Char('Name Unique', default=lambda s: str(uuid.uuid1()), required=True,
                       readonly=True, copy=False)
    number = fields.Char('Number')
    data = fields.Text('Data')
    trace_log = fields.Text('Log')
    connector_id = fields.Many2one('acrux.chat.connector', 'Connector', required=True,
                                   ondelete='cascade')
    res_id = fields.Integer('Resource ID for model')
    ttype = fields.Selection([('delete_me', 'To Delete'),
                              ('error', 'Error'),
                              ('processing', 'Processing'),
                              ('in_message', 'IN Message'),
                              ('in_event', 'IN Event'),
                              ('in_update', 'IN Update')],
                             string='Type', required=True)

    _sql_constraints = [
        ('work_name_uniq', 'unique (name, connector_id)', 'Key must be unique.')
    ]

    @api.autovacuum
    def _gc_delete_me(self):
        self.sudo().search([('ttype', '=', 'delete_me')]).unlink()
        self.sudo().search([('write_date', '<', datetime.now() + relativedelta(weeks=-1))]).unlink()

    @api.model
    def _cron_process_queue(self, connector_ids=None):
        if connector_ids is None:
            connector_ids = self.env['acrux.chat.connector'].sudo().search([]).ids
        for connector_id in connector_ids:
            key = 'lock_%s' % connector_id
            exec_fn = True
            try:
                self.env.cr.execute("SELECT id, write_date FROM acrux_chat_work_queue WHERE name='%s' limit 1" % key)
                res = self.env.cr.fetchone()
                if res and res[0] > 0:
                    if date_delta_seconds(res[1]) > 120:
                        self.env.cr.execute("DELETE FROM acrux_chat_work_queue WHERE id=%s", [res[0]])
                        self.env.cr.commit()
                    else:
                        exec_fn = False
                if exec_fn:
                    self.create({'name': key, 'ttype': 'processing', 'connector_id': connector_id})
                    self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()
                exec_fn = False
            if exec_fn:
                try:
                    self._process_queue([('connector_id', '=', connector_id)])
                except Exception as e:
                    _logger.error(e)
                self.env.cr.execute("DELETE FROM acrux_chat_work_queue WHERE name=%s", [key])
                self.env.cr.commit()

    @api.model
    def _process_queue(self, domain):
        max_count = 0
        while True:
            max_count += 1
            if max_count > 100:
                _logger.warning('Error max_count limit.')
                break
            job_domain = [('ttype', 'in', ['in_message', 'in_event', 'in_update'])] + domain
            job = self.search(job_domain, limit=1)
            if not job:
                break
            ctx = {
                'tz': job.connector_id.tz,
                'lang': job.connector_id.company_id.partner_id.lang,
                'allowed_company_ids': [job.connector_id.company_id.id],
                'from_webhook': True
            }
            job = job.with_context(ctx)
            connector_id = job.connector_id
            Conversation = self.env['acrux.chat.conversation'].sudo().with_context(ctx)
            data = json.loads(job.data)
            message_id = parse_data = False
            try:
                if job.ttype == 'in_message':
                    parse_data = Conversation.parse_message_receive(connector_id, data)
                    message_id = Conversation.new_message(parse_data)

                elif job.ttype == 'in_event':
                    parse_data = Conversation.parse_event_receive(connector_id, data)
                    Conversation.new_webhook_event(connector_id, parse_data)

                elif job.ttype == 'in_update':
                    parse_data = Conversation.parse_contact_receive(connector_id, data)
                    Conversation.contact_update(connector_id, parse_data)
                job.ttype = 'delete_me'
                self.env.cr.commit()
                job.job_postcommit(message_id, parse_data)
            except Exception as e:
                job.env.cr.rollback()
                _logger.error(f'chatroom - {job.id}, generic error')
                _logger.error(e)
                job.ttype = 'error'
                job.trace_log = traceback.format_exc()
            self.env.cr.commit()

    def job_postcommit(self, message_id, parse_data):
        pass
