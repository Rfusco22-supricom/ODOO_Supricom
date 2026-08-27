# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime

class HrBcvInterestRate(models.Model):
    _name = 'hr.bcv.interest.rate'
    _description = 'Historial de Tasa de Interés BCV'
    _order = 'year desc, month desc, id desc'

    def _default_year(self):
        return str(fields.Date.context_today(self).year)

    def _default_month(self):
        return str(fields.Date.context_today(self).month).zfill(2)

    year = fields.Char(string='Año', required=True, default=_default_year, size=4)
    month = fields.Selection([
        ('01', 'Enero'),
        ('02', 'Febrero'),
        ('03', 'Marzo'),
        ('04', 'Abril'),
        ('05', 'Mayo'),
        ('06', 'Junio'),
        ('07', 'Julio'),
        ('08', 'Agosto'),
        ('09', 'Septiembre'),
        ('10', 'Octubre'),
        ('11', 'Noviembre'),
        ('12', 'Diciembre')
    ], string='Mes', required=True, default=_default_month)
    rate = fields.Float(string='Tasa de Interés', required=True, digits=(16, 4))
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company, required=True)

    _sql_constraints = [
        ('year_month_company_unique', 'unique (year, month, company_id)', 'Ya existe una tasa para este mes y año en esta compañía.'),
    ]
    
    @api.depends('year', 'month')
    def name_get(self):
        result = []
        for record in self:
            name = f"{dict(record._fields['month'].selection).get(record.month, '')} {record.year}"
            result.append((record.id, name))
        return result
