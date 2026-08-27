# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    def write(self, vals):
        if self.env.user.has_group('supricom_restrictions_by_user.group_supricom_restricted'):
            for record in self:
                if record.date and record.date < fields.Date.today():
                    raise UserError(_("No tiene permisos para modificar cierres de días pasados."))
                if any(line.date and line.date < fields.Date.today() for line in record.line_ids):
                    raise UserError(_("No tiene permisos para modificar cierres de días pasados."))
        return super(AccountBankStatement, self).write(vals)

    def unlink(self):
        if self.env.user.has_group('supricom_restrictions_by_user.group_supricom_restricted'):
            for record in self:
                if record.date and record.date < fields.Date.today():
                    raise UserError(_("No tiene permisos para eliminar cierres de días pasados."))
                if any(line.date and line.date < fields.Date.today() for line in record.line_ids):
                    raise UserError(_("No tiene permisos para eliminar cierres de días pasados."))
        return super(AccountBankStatement, self).unlink()


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def write(self, vals):
        if self.env.user.has_group('supricom_restrictions_by_user.group_supricom_restricted'):
            for record in self:
                if record.date and record.date < fields.Date.today():
                    raise UserError(_("No tiene permisos para modificar movimientos de días pasados."))
        return super(AccountBankStatementLine, self).write(vals)

    def unlink(self):
        if self.env.user.has_group('supricom_restrictions_by_user.group_supricom_restricted'):
            for record in self:
                if record.date and record.date < fields.Date.today():
                    raise UserError(_("No tiene permisos para eliminar movimientos de días pasados."))
        return super(AccountBankStatementLine, self).unlink()
